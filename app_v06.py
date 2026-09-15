from __future__ import annotations

from datetime import datetime, timedelta
import re

import requests

import app_v05 as base


def fetch_khl_paginated(api_base: str, league: str, wanted_name: str) -> list[base.Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {
        "User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    response = requests.get(f"{api_base}/teams_v2.json", params=params, headers=headers, timeout=25)
    response.raise_for_status()
    raw_teams = base.unwrap_list(response.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    wanted = next((x for x in teams if base.team_name(x).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((x for x in teams if wanted_name.casefold() in base.team_name(x).casefold()), None)
    if wanted is None or wanted.get("id") is None:
        raise ValueError(f"команда {wanted_name} не найдена в KHL API")

    now = datetime.now(base.MOSCOW)
    common_query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(days=60)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": str(wanted["id"]),
        "order_direction": "asc",
    }

    games_by_id: dict[str, base.Game] = {}
    seen_raw_ids: set[str] = set()

    for page in range(1, 11):
        query = {**common_query, "page": page}
        response = requests.get(f"{api_base}/events_v2.json", params=query, headers=headers, timeout=25)
        response.raise_for_status()
        raw_events = base.unwrap_list(response.json(), ("data", "events", "items"))
        if not raw_events:
            break
        events = [x.get("event", x) if isinstance(x, dict) else x for x in raw_events]
        new_on_page = 0

        for event in events:
            if not isinstance(event, dict) or event.get("type_id") not in (None, 24):
                continue
            event_id = event.get("id") or event.get("khl_id")
            raw_time = event.get("start_at") or event.get("event_start_at")
            if event_id is None or raw_time is None:
                continue
            event_key = str(event_id)
            if event_key in seen_raw_ids:
                continue
            seen_raw_ids.add(event_key)
            new_on_page += 1

            if isinstance(raw_time, str) and raw_time.isdigit():
                raw_time = int(raw_time)
            if isinstance(raw_time, (int, float)):
                timestamp = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
                start_at = datetime.fromtimestamp(timestamp, base.MOSCOW)
            else:
                start_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                start_at = start_at.replace(tzinfo=base.MOSCOW) if start_at.tzinfo is None else start_at.astimezone(base.MOSCOW)

            home_score, away_score = base.parse_score(event.get("score"))
            state = str(event.get("game_state_key") or "").lower()
            status = "finished" if state == "finished" else "live" if state == "in_progress" else "scheduled"
            scores = event.get("scores") or {}
            decision = "SO" if isinstance(scores, dict) and scores.get("bullitt") else "OT" if isinstance(scores, dict) and scores.get("overtime") else None
            khl_id = event.get("khl_id")
            source_url = f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None

            games_by_id[event_key] = base.Game(
                "khl_api",
                event_key,
                league,
                base.team_name(event.get("team_a") or {}),
                base.team_name(event.get("team_b") or {}),
                start_at,
                status,
                home_score,
                away_score,
                decision,
                base.compact(event.get("location") or "") or None,
                source_url,
            )

        # Некоторые версии API на странице за пределами выдачи повторяют последнюю страницу.
        if new_on_page == 0:
            break

    games = sorted(games_by_id.values(), key=lambda game: game.start_at)
    if not games:
        raise ValueError(f"KHL API не вернул матчи {wanted_name}")
    return games


base.fetch_khl = fetch_khl_paginated
base.app.version = "0.6.0"
app = base.app
