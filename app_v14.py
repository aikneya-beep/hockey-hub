from __future__ import annotations

from datetime import datetime
import re

import requests

import app_v13 as prev
import app_v10 as ui
import app_v05 as core

KHL_REGULAR_START = datetime(2026, 9, 5, 0, 0, tzinfo=core.MOSCOW)


def _event_to_game(event: dict, league: str, now: datetime) -> core.Game | None:
    if not isinstance(event, dict) or event.get("type_id") not in (None, 24):
        return None
    event_id = event.get("id") or event.get("khl_id")
    raw_time = event.get("start_at") or event.get("event_start_at")
    if event_id is None or raw_time is None:
        return None
    if isinstance(raw_time, str) and raw_time.isdigit():
        raw_time = int(raw_time)
    if isinstance(raw_time, (int, float)):
        ts = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
        start_at = datetime.fromtimestamp(ts, core.MOSCOW)
    else:
        start_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        start_at = start_at.replace(tzinfo=core.MOSCOW) if start_at.tzinfo is None else start_at.astimezone(core.MOSCOW)

    if league == "КХЛ" and start_at < KHL_REGULAR_START:
        return None

    home_score, away_score = core.parse_score(event.get("score"))
    state = str(event.get("game_state_key") or "").casefold()
    if state == "finished":
        status = "finished"
    elif state == "in_progress":
        status = "live"
    elif start_at < now - core.timedelta(hours=4) and home_score is not None and away_score is not None and (home_score or away_score):
        status = "finished"
    else:
        status = "scheduled"
    if status == "scheduled":
        home_score = away_score = None

    scores = event.get("scores") or {}
    decision = (
        "SO" if isinstance(scores, dict) and scores.get("bullitt")
        else "OT" if isinstance(scores, dict) and scores.get("overtime")
        else None
    )
    khl_id = event.get("khl_id")
    return core.Game(
        "khl_api", str(event_id), league,
        core.team_name(event.get("team_a") or {}),
        core.team_name(event.get("team_b") or {}),
        start_at, status, home_score, away_score, decision,
        core.compact(event.get("location") or "") or None,
        f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None,
    )


def fetch_khl_v14(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    # Keep the working full future schedule from v0.13.
    future = prev.fetch_khl_v13(api_base, league, wanted_name)
    by_id = {g.source_game_id: g for g in future}

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

    detail = requests.get(
        f"{api_base}/team_v2.json",
        params={**params, "id": wanted["id"]},
        headers=headers,
        timeout=25,
    )
    detail.raise_for_status()
    payload = detail.json()
    team = payload.get("team", payload) if isinstance(payload, dict) else {}
    recent_raw = team.get("recent_events") or []
    now = datetime.now(core.MOSCOW)
    recent_games: list[core.Game] = []
    for wrapped in recent_raw:
        event = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
        game = _event_to_game(event, league, now)
        if game is None:
            continue
        # A recent-event payload is authoritative for status/score and should
        # replace a calendar item with the same event ID.
        by_id[game.source_game_id] = game
        recent_games.append(game)

    print(
        "[verify] SKA recent_events: " + "; ".join(
            f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team} [{g.status}]"
            for g in recent_games
        ),
        flush=True,
    )
    result = sorted(by_id.values(), key=lambda g: g.start_at)
    if not result:
        raise ValueError(f"KHL API не вернул матчи {wanted_name}")
    return result


core.fetch_khl = fetch_khl_v14
# Keep the verified SPbHL parser from v0.13.
core.fetch_spbhl = prev.fetch_spbhl_v13
core.app.version = "0.14.0"


def render_page_v14() -> str:
    page = ui.render_page_v10()
    return re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.14", page, count=1)


core.render_page = render_page_v14
app = core.app
