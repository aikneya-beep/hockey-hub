from __future__ import annotations

from datetime import datetime, timedelta

import app_v27 as api
import app_v28 as v28
import app_v19 as feature
import app_v05 as core


def fetch_khl_with_postseason(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    """СКА schedule collector that keeps official non-regular events.

    KHL marks postseason games with `not_regular`. v0.28 intentionally skipped
    those events to protect the regular-season feed; that would make playoff
    monitoring blind in spring. We now keep them in the match feed and attach a
    lightweight stage hint, while standings continue to exclude them separately.
    """
    if wanted_name != "СКА":
        return feature.fetch_khl_v19(api_base, league, wanted_name)

    teams = api._get_teams()
    tid = api._ska_id(teams)
    now = datetime.now(core.MOSCOW)
    start = int((feature.REGULAR_START - timedelta(hours=1)).timestamp())

    past = api._events({
        "q[start_at_gt_time_from_unixtime]": start,
        "q[start_at_lt_time_from_unixtime]": int(now.timestamp()),
        "q[team_a_or_team_b_in][]": tid,
        "order_direction": "asc",
    }, 20)
    future = api._events({
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(hours=6)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=280)).timestamp()),
        "q[team_a_or_team_b_in][]": tid,
        "order_direction": "asc",
    }, 24)

    by_id: dict[str, core.Game] = {}
    priority = {"scheduled": 0, "live": 1, "finished": 2}
    for event in past + future:
        game = v28._game_from_event(event, league, now)
        if game is None or game.start_at < feature.REGULAR_START:
            continue
        # Dynamic attribute keeps compatibility with the historical Game
        # dataclass while giving postseason adapters an official source signal.
        game.stage_hint = "playoff" if event.get("not_regular") is True else "regular"
        current = by_id.get(game.source_game_id)
        if current is None or priority.get(game.status, 0) >= priority.get(current.status, 0):
            by_id[game.source_game_id] = game

    games = sorted(by_id.values(), key=lambda g: g.start_at)
    if not games:
        raise ValueError("KHL API не вернул матчи СКА")

    finished = [g for g in games if g.status == "finished"]
    postseason = [g for g in games if getattr(g, "stage_hint", None) == "playoff"]
    print(
        f"[verify] SKA v36 official games={len(games)} finished={len(finished)} postseason={len(postseason)}",
        flush=True,
    )
    return games
