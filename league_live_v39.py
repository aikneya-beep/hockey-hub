from __future__ import annotations

from datetime import datetime, timedelta
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import app_v05 as core

HEADERS = {"User-Agent": "Mozilla/5.0 HockeyHub", "Accept-Language": "ru-RU,ru;q=0.9"}
MHL_TEXT_ROOT = "https://text.mhl.khl.ru/"
MHL_CALENDAR = "https://mhl.khl.ru/calendar/"
VHL_TEAM_CALENDAR = "https://www.vhlru.ru/calendar/1430/0/15529/"

_MHL_CACHE: tuple[float, list[dict]] | None = None
_VHL_CACHE: tuple[float, str] | None = None


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").replace("–", "-").replace("—", "-").split())


def _near_now(game: core.Game, now: datetime, before_minutes: int = 20, after_hours: int = 5) -> bool:
    return game.start_at - timedelta(minutes=before_minutes) <= now <= game.start_at + timedelta(hours=after_hours)


def cached_team_games(wanted_name: str, league: str) -> list[core.Game]:
    with core.LOCK:
        return sorted(
            [g for g in core.GAMES.values() if g.league == league and wanted_name in (g.home_team, g.away_team)],
            key=lambda g: g.start_at,
        )


def _mhl_detail_pages() -> list[dict]:
    global _MHL_CACHE
    now_ts = time.time()
    if _MHL_CACHE and now_ts - _MHL_CACHE[0] < 25:
        return _MHL_CACHE[1]

    response = requests.get(MHL_TEXT_ROOT, headers=HEADERS, timeout=8)
    response.raise_for_status()
    root = BeautifulSoup(response.text, "html.parser")
    detail_urls: list[str] = []
    for a in root.find_all("a", href=True):
        label = core.compact(a.get_text(" ", strip=True)).casefold()
        href = a.get("href") or ""
        if label == "просмотр" and re.search(r"\d+\.html(?:[?#].*)?$", href):
            absolute = urljoin(MHL_TEXT_ROOT, href)
            if absolute not in detail_urls:
                detail_urls.append(absolute)

    details: list[dict] = []
    # The text center normally exposes only today's games. Keep a conservative
    # cap so a malformed page can never fan out into hundreds of requests.
    for detail_url in detail_urls[:24]:
        try:
            r = requests.get(detail_url, headers=HEADERS, timeout=6)
            r.raise_for_status()
        except Exception:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        title = core.compact(soup.title.get_text(" ", strip=True) if soup.title else "")
        tokens = [core.compact(x) for x in soup.stripped_strings if core.compact(x)]
        text = " ".join(tokens)

        number_match = re.search(r"Игра\s+номер\s+(\d+)", f"{title} {text}", re.I)
        number = number_match.group(1) if number_match else None
        home_score = away_score = None
        state_text = ""
        if number:
            marker = f"#{number}"
            for i, token in enumerate(tokens):
                if token != marker:
                    continue
                window = tokens[i + 1 : i + 10]
                for j in range(max(0, len(window) - 2)):
                    if (
                        j + 2 < len(window)
                        and window[j].isdigit()
                        and window[j + 1] in {"-", "–", "—"}
                        and window[j + 2].isdigit()
                    ):
                        home_score = int(window[j])
                        away_score = int(window[j + 2])
                        state_text = window[j + 3] if j + 3 < len(window) else ""
                        break
                if home_score is not None:
                    break

        low = _norm(text)
        finished = any(x in low for x in ("матч завершен", "матч завершён", "окончание игры", "игра завершена"))
        video = None
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "")
            if "/media/video/" in href:
                video = urljoin(detail_url, href)
                break

        details.append({
            "detail_url": detail_url,
            "video_url": video,
            "title": title,
            "text": text,
            "score": (home_score, away_score),
            "state": state_text,
            "finished": finished,
        })

    _MHL_CACHE = (now_ts, details)
    return details


def overlay_mhl_live(games: list[core.Game], wanted_name: str) -> int:
    """Overlay official MHL text-center score/status/video onto the club schedule."""
    now = datetime.now(core.MOSCOW)
    for game in games:
        game.source_url = MHL_CALENDAR

    try:
        details = _mhl_detail_pages()
    except Exception as exc:
        print(f"[live] MHL {wanted_name}: text center unavailable: {type(exc).__name__}: {exc}", flush=True)
        details = []

    updated = 0
    for game in games:
        if game.start_at.date() != now.date():
            continue
        home = _norm(game.home_team)
        away = _norm(game.away_team)
        match = None
        for item in details:
            hay = _norm(f"{item['title']} {item['text']}")
            if home in hay and away in hay:
                match = item
                break
        if match:
            hs, aw = match["score"]
            if hs is not None and aw is not None:
                game.home_score = hs
                game.away_score = aw
                game.status = "finished" if match["finished"] else "live"
            elif _near_now(game, now):
                game.status = "live"
            game.source_url = match["video_url"] or match["detail_url"]
            updated += 1
            print(
                f"[live] MHL {wanted_name}: {game.status} {game.home_team} "
                f"{game.home_score}:{game.away_score} {game.away_team} source={game.source_url}",
                flush=True,
            )
        elif _near_now(game, now) and game.status == "scheduled":
            # Time-based fallback changes only the state, never invents a score.
            game.status = "live"
            print(f"[live] MHL {wanted_name}: time fallback for {game.home_team} — {game.away_team}", flush=True)
    return updated


def _vhl_calendar_html() -> str:
    global _VHL_CACHE
    now_ts = time.time()
    if _VHL_CACHE and now_ts - _VHL_CACHE[0] < 25:
        return _VHL_CACHE[1]
    r = requests.get(VHL_TEAM_CALENDAR, headers=HEADERS, timeout=8)
    r.raise_for_status()
    _VHL_CACHE = (now_ts, r.text)
    return r.text


def _small_context(anchor, aliases: tuple[str, ...]) -> str:
    node = anchor
    best = ""
    for _ in range(9):
        if node is None:
            break
        try:
            text = core.compact(node.get_text(" ", strip=True))
        except Exception:
            text = ""
        low = _norm(text)
        if text and any(_norm(alias) in low for alias in aliases):
            best = text
            # Prefer a compact score/match card over the whole page.
            if len(text) < 700:
                return text
        node = getattr(node, "parent", None)
    return best


def overlay_vhl_live(games: list[core.Game], wanted_name: str) -> int:
    """Use official VHL calendar/online center for live state and source links."""
    now = datetime.now(core.MOSCOW)
    for game in games:
        game.source_url = VHL_TEAM_CALENDAR

    try:
        soup = BeautifulSoup(_vhl_calendar_html(), "html.parser")
    except Exception as exc:
        print(f"[live] VHL {wanted_name}: calendar unavailable: {type(exc).__name__}: {exc}", flush=True)
        return 0

    live_candidates: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(VHL_TEAM_CALENDAR, a.get("href") or "")
        if "online.vhlru.ru" not in href:
            continue
        context = _small_context(a, (wanted_name, "ВМФ"))
        if context:
            live_candidates.append((href, context))

    updated = 0
    todays = [g for g in games if g.start_at.date() == now.date()]
    for game in todays:
        opponent = game.away_team if game.home_team == wanted_name else game.home_team
        chosen = None
        for href, context in live_candidates:
            low = _norm(context)
            if _norm(opponent) in low or "вмф" in low:
                chosen = (href, context)
                if _norm(opponent) in low:
                    break
        if chosen:
            href, context = chosen
            scores = re.findall(r"(?<!\d)(\d{1,2})\s*:\s*(\d{1,2})(?!\d)", context)
            if scores:
                hs, aw = map(int, scores[0])
                game.home_score = hs
                game.away_score = aw
            low = _norm(context)
            game.status = "finished" if any(x in low for x in ("завершен", "завершён", "окончен")) else "live"
            game.source_url = href
            updated += 1
            print(
                f"[live] VHL {wanted_name}: {game.status} {game.home_team} "
                f"{game.home_score}:{game.away_score} {game.away_team} source={href}",
                flush=True,
            )
        elif _near_now(game, now) and game.status == "scheduled":
            game.status = "live"
            print(f"[live] VHL {wanted_name}: time fallback for {game.home_team} — {game.away_team}", flush=True)
    return updated
