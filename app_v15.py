from __future__ import annotations

from datetime import datetime, timedelta
import re

import requests

import app_v13 as spb
import app_v10 as ui
import app_v05 as core


def _current_season(now: datetime) -> str:
    return f"{now.year}/{now.year + 1}" if now.month >= 7 else f"{now.year - 1}/{now.year}"


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

    hs, aw = core.parse_score(event.get("score"))
    state = str(event.get("game_state_key") or "").casefold()
    if state == "finished":
        status = "finished"
    elif state == "in_progress":
        status = "live"
    elif start_at < now - timedelta(hours=4) and hs is not None and aw is not None and (hs or aw):
        status = "finished"
    else:
        status = "scheduled"
    if status == "scheduled":
        hs = aw = None

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
        start_at, status, hs, aw, decision,
        core.compact(event.get("location") or "") or None,
        f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None,
    )


def fetch_khl_v15(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {
        "User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    now = datetime.now(core.MOSCOW)
    season = _current_season(now)

    # Resolve the exact regular-season stage instead of relying on API defaults.
    data_response = requests.get(f"{api_base}/data.json", params=params, headers=headers, timeout=25)
    data_response.raise_for_status()
    data = data_response.json()
    stages = data.get("stages_v2") or [] if isinstance(data, dict) else []
    stage = next(
        (
            s for s in stages
            if isinstance(s, dict)
            and str(s.get("type") or "").casefold() == "regular"
            and (str(s.get("season") or "") == season or season in str(s.get("title") or ""))
        ),
        None,
    )
    if stage is None:
        current_id = data.get("current_stage_id") if isinstance(data, dict) else None
        stage = next((s for s in stages if isinstance(s, dict) and s.get("id") == current_id), None)
    if stage is None or stage.get("id") is None:
        raise ValueError(f"не найден stage регулярного чемпионата {season}")
    stage_id = stage["id"]
    print(f"[verify] KHL stage: id={stage_id} title={stage.get('title')!r} season={stage.get('season')!r} type={stage.get('type')!r}", flush=True)

    team_response = requests.get(
        f"{api_base}/teams_v2.json",
        params={**params, "stage_id": stage_id},
        headers=headers,
        timeout=25,
    )
    team_response.raise_for_status()
    raw_teams = core.unwrap_list(team_response.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    wanted = next((x for x in teams if core.team_name(x).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((x for x in teams if wanted_name.casefold() in core.team_name(x).casefold()), None)
    if wanted is None or wanted.get("id") is None:
        raise ValueError(f"команда {wanted_name} не найдена в stage {stage_id}")

    common_query = {
        **params,
        "stage_id": stage_id,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(days=60)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": str(wanted["id"]),
        "order_direction": "asc",
    }

    by_id: dict[str, core.Game] = {}
    seen: set[str] = set()
    for page in range(1, 20):
        response = requests.get(
            f"{api_base}/events_v2.json",
            params={**common_query, "page": page},
            headers=headers,
            timeout=25,
        )
        response.raise_for_status()
        raw_events = core.unwrap_list(response.json(), ("data", "events", "items"))
        if not raw_events:
            break
        added = 0
        for wrapped in raw_events:
            event = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
            if not isinstance(event, dict):
                continue
            key = str(event.get("id") or event.get("khl_id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            game = _event_to_game(event, league, now)
            if game is not None:
                by_id[game.source_game_id] = game
                added += 1
        if added == 0:
            break

    # Team detail is an additional source for recently played events.
    detail = requests.get(
        f"{api_base}/team_v2.json",
        params={**params, "id": wanted["id"], "stage_id": stage_id},
        headers=headers,
        timeout=25,
    )
    detail.raise_for_status()
    payload = detail.json()
    team = payload.get("team", payload) if isinstance(payload, dict) else {}
    for wrapped in team.get("recent_events") or []:
        event = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
        game = _event_to_game(event, league, now)
        if game is not None:
            by_id[game.source_game_id] = game

    result = sorted(by_id.values(), key=lambda g: g.start_at)
    finished = [g for g in result if g.status == "finished"]
    print(
        f"[verify] SKA stage games={len(result)} finished={len(finished)}: " + "; ".join(
            f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}"
            for g in finished[-10:]
        ),
        flush=True,
    )
    if not result:
        raise ValueError(f"KHL API не вернул матчи {wanted_name} для stage {stage_id}")
    return result


core.fetch_khl = fetch_khl_v15
core.fetch_spbhl = spb.fetch_spbhl_v13
core.app.version = "0.15.0"


def render_page_v15() -> str:
    page = ui.render_page_v10()
    return re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.15", page, count=1)


core.render_page = render_page_v15
app = core.app
