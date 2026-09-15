from __future__ import annotations

from datetime import datetime, timedelta

import app_v27 as prev
import app_v19 as feature
import app_v23 as stable
import app_v05 as core

core.app.version = "0.28.0"


def _game_from_event(event: dict, league: str, now: datetime) -> core.Game | None:
    # Completed KHL events use a different type_id from scheduled events in the
    # mobile backend, so type_id is not a reliable match discriminator.
    if not isinstance(event, dict):
        return None
    eid = event.get("id") or event.get("khl_id")
    raw_time = event.get("start_at") or event.get("event_start_at")
    ta = event.get("team_a") or {}
    tb = event.get("team_b") or {}
    home = core.team_name(ta)
    away = core.team_name(tb)
    if eid is None or raw_time is None or not home or not away:
        return None

    start_at = feature._dt(raw_time)
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
        hs = aw = None

    scores = event.get("scores") or {}
    decision = (
        "SO" if isinstance(scores, dict) and scores.get("bullitt")
        else "OT" if isinstance(scores, dict) and scores.get("overtime")
        else None
    )
    khl_id = event.get("khl_id") or event.get("id")
    return core.Game(
        "khl_api",
        str(eid),
        league,
        home,
        away,
        start_at,
        status,
        hs,
        aw,
        decision,
        core.compact(event.get("location") or "") or None,
        f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None,
    )


def fetch_khl_v28(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    if wanted_name != "СКА":
        return feature.fetch_khl_v19(api_base, league, wanted_name)

    teams = prev._get_teams()
    tid = prev._ska_id(teams)
    now = datetime.now(core.MOSCOW)
    start = int((feature.REGULAR_START - timedelta(hours=1)).timestamp())

    past = prev._events({
        "q[start_at_gt_time_from_unixtime]": start,
        "q[start_at_lt_time_from_unixtime]": int(now.timestamp()),
        "q[team_a_or_team_b_in][]": tid,
        "order_direction": "asc",
    }, 12)
    future = prev._events({
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(hours=6)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": tid,
        "order_direction": "asc",
    }, 20)

    by_id: dict[str, core.Game] = {}
    priority = {"scheduled": 0, "live": 1, "finished": 2}
    for event in past + future:
        if event.get("not_regular") is True:
            continue
        game = _game_from_event(event, league, now)
        if game is None or game.start_at < feature.REGULAR_START:
            continue
        current = by_id.get(game.source_game_id)
        if current is None or priority.get(game.status, 0) >= priority.get(current.status, 0):
            by_id[game.source_game_id] = game

    games = sorted(by_id.values(), key=lambda g: g.start_at)
    finished = [g for g in games if g.status == "finished"]
    if not games:
        raise ValueError("KHL API не вернул матчи СКА")
    print(
        f"[verify] SKA v28 official games={len(games)} finished={len(finished)}: "
        + "; ".join(f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}" for g in finished[-10:]),
        flush=True,
    )
    return games


core.fetch_khl = fetch_khl_v28

# Reuse v27's official-table strategy: tables_v2 first, standings calculated
# from official completed games second, dated snapshot only as last resort.
feature._fetch_khl_standings = prev.khl_standings_v27
feature.STANDINGS_CACHE.pop("ska", None)

_old_team_page = feature.render_team_page


def render_team_page_v28(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.27", "v0.28")


feature.render_team_page = render_team_page_v28


def render_page_v28() -> str:
    return stable.render_page_v23().replace("v0.23", "v0.28", 1)


core.render_page = render_page_v28
app = core.app
