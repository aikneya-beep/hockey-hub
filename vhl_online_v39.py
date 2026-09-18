from __future__ import annotations

from datetime import datetime, timedelta
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import app_v05 as core

HEADERS = {"User-Agent": "Mozilla/5.0 HockeyHub", "Accept-Language": "ru-RU,ru;q=0.9"}
VHL_ONLINE_ROOT = "https://online.vhlru.ru/online/"
VHL_TEAM_CALENDAR = "https://www.vhlru.ru/calendar/1430/0/15529/"
LIVE_SOFT_LIMIT = timedelta(hours=3, minutes=30)


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").replace("–", "-").replace("—", "-").split())


def _near_now(game: core.Game, now: datetime) -> bool:
    return game.start_at - timedelta(minutes=20) <= now <= game.start_at + LIVE_SOFT_LIMIT


def _apply_time_fallback(game: core.Game, now: datetime) -> str | None:
    """Keep a match live only for a realistic hockey window.

    The team calendar may expose a numeric running score without a final marker.
    Inside the soft window that score is not trusted as final. After 3h30, a
    numeric score is accepted as finished so a stale online center cannot leave
    LIVE on screen for hours.
    """
    if _near_now(game, now):
        game.status = "live"
        return "live"
    if (
        now > game.start_at + LIVE_SOFT_LIMIT
        and game.home_score is not None
        and game.away_score is not None
    ):
        game.status = "finished"
        return "finished"
    return None


def _card_context(anchor) -> str:
    node = anchor
    best = ""
    for _ in range(8):
        if node is None:
            break
        try:
            text = core.compact(node.get_text(" ", strip=True))
        except Exception:
            text = ""
        if text and "ВМФ" in text:
            best = text
            if re.search(r"\d{1,2}\s*:\s*\d{1,2}", text) and len(text) < 500:
                return text
        node = getattr(node, "parent", None)
    return best


def overlay_vhl_live(games: list[core.Game], wanted_name: str) -> int:
    """Overlay SKA-VMF state from the official VHL online match center.

    Important: the ordinary VHL/team calendar can expose a running numeric
    score while the match is still in progress. A numeric score alone must
    therefore never be treated as a final result inside the live window.
    """
    now = datetime.now(core.MOSCOW)
    for game in games:
        game.source_url = VHL_TEAM_CALENDAR

    try:
        response = requests.get(VHL_ONLINE_ROOT, headers=HEADERS, timeout=8)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        print(f"[live] VHL {wanted_name}: online center unavailable: {type(exc).__name__}: {exc}", flush=True)
        for game in games:
            if game.start_at.date() == now.date():
                _apply_time_fallback(game, now)
        return 0

    candidates: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        if core.compact(a.get_text(" ", strip=True)).casefold() != "просмотр":
            continue
        context = _card_context(a)
        if "ВМФ" not in context:
            continue
        candidates.append((urljoin(VHL_ONLINE_ROOT, a.get("href") or ""), context))

    todays = [g for g in games if g.start_at.date() == now.date()]
    updated = 0
    for game in todays:
        if not candidates:
            # The club/team calendar may already contain a running score and
            # the legacy schedule parser labels any numeric score as finished.
            # Within the live window that is unsafe: keep the match live until
            # the official online center explicitly reports completion.
            state = _apply_time_fallback(game, now)
            if state == "finished":
                print(
                    f"[live] VHL {wanted_name}: soft-limit finish "
                    f"{game.home_team} {game.home_score}:{game.away_score} {game.away_team}",
                    flush=True,
                )
            continue

        opponent = game.away_team if game.home_team == wanted_name else game.home_team
        chosen = next((c for c in candidates if _norm(opponent) in _norm(c[1])), None)
        if chosen is None:
            # Never attach an arbitrary VМФ online card to today's match.
            # The online root can contain stale/adjacent cards and abbreviated
            # team names. In the live window the club schedule's running score
            # is useful, but without a confident opponent match it is not safe
            # to import completion state or a foreign match URL.
            state = _apply_time_fallback(game, now)
            if state:
                print(
                    f"[live] VHL {wanted_name}: {state}-window fallback "
                    f"{game.home_team} {game.home_score}:{game.away_score} {game.away_team}",
                    flush=True,
                )
            continue
        href, context = chosen
        score_match = re.search(r"(?<!\d)(\d{1,2})\s*:\s*(\d{1,2})(?!\d)", context)
        if score_match:
            game.home_score = int(score_match.group(1))
            game.away_score = int(score_match.group(2))
        low = _norm(context)
        explicit_finished = any(x in low for x in ("матч завершен", "матч завершён", "окончен"))
        if explicit_finished:
            game.status = "finished"
        elif now > game.start_at + LIVE_SOFT_LIMIT and game.home_score is not None and game.away_score is not None:
            game.status = "finished"
        else:
            game.status = "live"
        game.source_url = href
        updated += 1
        print(
            f"[live] VHL {wanted_name}: {game.status} {game.home_team} "
            f"{game.home_score}:{game.away_score} {game.away_team} source={href}",
            flush=True,
        )
    return updated
