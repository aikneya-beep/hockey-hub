from __future__ import annotations

from datetime import datetime, timedelta
import re

import requests
from bs4 import BeautifulSoup

import app_v12 as prev
import app_v10 as ui
import app_v05 as core

KHL_REGULAR_START = datetime(2026, 9, 5, 0, 0, tzinfo=core.MOSCOW)


def fetch_khl_v13(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {
        "User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    r = requests.get(f"{api_base}/teams_v2.json", params=params, headers=headers, timeout=25)
    r.raise_for_status()
    raw_teams = core.unwrap_list(r.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    wanted = next((x for x in teams if core.team_name(x).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((x for x in teams if wanted_name.casefold() in core.team_name(x).casefold()), None)
    if wanted is None or wanted.get("id") is None:
        raise ValueError(f"команда {wanted_name} не найдена в KHL API")

    now = datetime.now(core.MOSCOW)
    common_query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(days=90)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": str(wanted["id"]),
        "order_direction": "asc",
    }

    games: dict[str, core.Game] = {}
    seen: set[str] = set()
    raw_debug: list[str] = []

    for page in range(1, 15):
        r = requests.get(f"{api_base}/events_v2.json", params={**common_query, "page": page}, headers=headers, timeout=25)
        r.raise_for_status()
        raw_events = core.unwrap_list(r.json(), ("data", "events", "items"))
        if not raw_events:
            break
        events = [x.get("event", x) if isinstance(x, dict) else x for x in raw_events]
        added = 0
        for event in events:
            if not isinstance(event, dict) or event.get("type_id") not in (None, 24):
                continue
            event_id = event.get("id") or event.get("khl_id")
            raw_time = event.get("start_at") or event.get("event_start_at")
            if event_id is None or raw_time is None:
                continue
            key = str(event_id)
            if key in seen:
                continue
            seen.add(key)
            added += 1

            if isinstance(raw_time, str) and raw_time.isdigit():
                raw_time = int(raw_time)
            if isinstance(raw_time, (int, float)):
                ts = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
                start_at = datetime.fromtimestamp(ts, core.MOSCOW)
            else:
                start_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                start_at = start_at.replace(tzinfo=core.MOSCOW) if start_at.tzinfo is None else start_at.astimezone(core.MOSCOW)

            # Current-season league boundary. We intentionally do not use
            # `not_regular`: its semantics are undocumented for our use case.
            if league == "КХЛ" and wanted_name == "СКА" and start_at < KHL_REGULAR_START:
                continue

            home = core.team_name(event.get("team_a") or {})
            away = core.team_name(event.get("team_b") or {})
            home_score, away_score = core.parse_score(event.get("score"))
            state = str(event.get("game_state_key") or "").casefold()

            if KHL_REGULAR_START <= start_at <= now + timedelta(days=1):
                raw_debug.append(
                    f"{start_at:%d.%m %H:%M} {home}-{away} score={event.get('score')!r} "
                    f"state={state!r} not_regular={event.get('not_regular')!r} stage={event.get('stage_name')!r}"
                )

            if state == "finished":
                status = "finished"
            elif state == "in_progress":
                status = "live"
            elif start_at < now - timedelta(hours=4) and home_score is not None and away_score is not None and (home_score or away_score):
                status = "finished"
            else:
                status = "scheduled"

            if status == "scheduled":
                home_score = None
                away_score = None

            scores = event.get("scores") or {}
            decision = (
                "SO" if isinstance(scores, dict) and scores.get("bullitt")
                else "OT" if isinstance(scores, dict) and scores.get("overtime")
                else None
            )
            khl_id = event.get("khl_id")
            games[key] = core.Game(
                "khl_api", key, league, home, away, start_at, status,
                home_score, away_score, decision,
                core.compact(event.get("location") or "") or None,
                f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None,
            )
        if added == 0:
            break

    if raw_debug:
        print("[verify] KHL raw: " + " || ".join(raw_debug[-12:]), flush=True)
    result = sorted(games.values(), key=lambda g: g.start_at)
    if not result:
        raise ValueError(f"KHL API не вернул матчи {wanted_name}")
    return result


def fetch_spbhl_v13(url: str) -> list[core.Game]:
    response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")
    score_re = re.compile(r"(\d+)\s*:\s*(\d+)\s*([А-ЯA-Z]{0,3})")
    games: list[core.Game] = []

    for row in soup.find_all("tr"):
        text = core.compact(row.get_text(" ", strip=True))
        if "Эскулап" not in text:
            continue
        dm = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
        tm = re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", text)
        if not dm or not tm:
            continue
        link = next((a for a in row.find_all("a", href=True) if "Эскулап" in core.compact(a.get_text(" ", strip=True))), None)
        teams_text = core.compact(link.get_text(" ", strip=True)) if link else ""
        parts = re.split(r"\s+-\s+", teams_text, maxsplit=1)
        if len(parts) != 2:
            continue
        home, away = parts

        cells = row.find_all("td")
        teams_cell = link.find_parent("td") if link else None
        result_cell = teams_cell.find_next_sibling("td") if teams_cell else None
        result_text = core.compact(result_cell.get_text(" ", strip=True)) if result_cell else ""
        sm = score_re.search(result_text)
        hs = int(sm.group(1)) if sm else None
        aw = int(sm.group(2)) if sm else None
        suffix = sm.group(3).upper() if sm else ""
        decision = "SO" if suffix in {"ПБ", "Б", "SO"} else "OT" if suffix in {"ОТ", "OT"} else None

        number = core.compact(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else ""
        arena = core.compact(cells[5].get_text(" ", strip=True)) if len(cells) >= 6 else None
        date_text, time_text = dm.group(0), tm.group(0)
        start_at = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=core.MOSCOW)
        game_url = requests.compat.urljoin(url, link["href"]) if link else url
        game_id = number or core.make_id(date_text, time_text, home, away)
        games.append(core.Game(
            "spbhl", f"spbhl-{game_id}", "СПбХЛ", home, away, start_at,
            "finished" if sm else "scheduled", hs, aw, decision, arena or None, game_url,
        ))

    print(
        "[verify] Eskulap: " + "; ".join(
            f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}"
            for g in games if g.status == "finished"
        ),
        flush=True,
    )
    if not games:
        raise ValueError("не удалось распознать матчи Эскулапа")
    return games


core.fetch_khl = fetch_khl_v13
core.fetch_spbhl = fetch_spbhl_v13
core.app.version = "0.13.0"


def render_page_v13() -> str:
    page = ui.render_page_v10()
    return re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.13", page, count=1)


core.render_page = render_page_v13
app = core.app
