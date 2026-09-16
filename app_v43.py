from __future__ import annotations

from datetime import datetime, timedelta

import app_v42
import app_v40 as live_base
import app_v19 as feature
import app_v05 as core

core.app.version = "0.43.0"

LIVE_LEAGUES = {"КХЛ", "ВХЛ", "МХЛ", "СПбХЛ"}
SPBHL_LIVE_WINDOW = timedelta(hours=3, minutes=30)


# SPbHL publishes the running score in the ordinary team schedule. The legacy
# parser treated any numeric score as a finished result, which is wrong while
# the game is still in progress. Until the source exposes an explicit final
# state in our parser, game time is the safest live-state guard.
_base_fetch_spbhl = core.fetch_spbhl


def fetch_spbhl_v43(url: str):
    games = _base_fetch_spbhl(url)
    now = datetime.now(core.MOSCOW)
    for game in games:
        if game.start_at <= now <= game.start_at + SPBHL_LIVE_WINDOW:
            game.status = "live"
        elif now > game.start_at + SPBHL_LIVE_WINDOW and game.home_score is not None and game.away_score is not None:
            game.status = "finished"
    return games


core.fetch_spbhl = fetch_spbhl_v43


def _active_v43(now=None):
    now = now or datetime.now(core.MOSCOW)
    with core.LOCK:
        return any(
            g.league in LIVE_LEAGUES
            and g.status != "finished"
            and g.start_at - timedelta(minutes=20) <= now <= g.start_at + timedelta(hours=5)
            for g in core.GAMES.values()
        )


def refresh_live_v43():
    now = datetime.now(core.MOSCOW)
    if not _active_v43(now):
        return

    for team in core.TEAMS:
        if team.league not in LIVE_LEAGUES:
            continue
        with core.LOCK:
            relevant = [g for g in core.GAMES.values() if team.name in (g.home_team, g.away_team)]
        if not any(
            g.status != "finished"
            and g.start_at - timedelta(minutes=20) <= now <= g.start_at + timedelta(hours=5)
            for g in relevant
        ):
            continue

        try:
            games = core.fetch_team(team)
            with core.LOCK:
                for game in games:
                    core.GAMES[(game.source, game.source_game_id)] = game
            print(f"[live-fast] {team.name}: OK {len(games)}", flush=True)
        except Exception as exc:
            print(f"[live-fast] {team.name}: {type(exc).__name__}: {exc}", flush=True)


# v0.40's refresh loop and page auto-reloader resolve these globals dynamically,
# so patching them here extends the existing live machinery without starting a
# second background thread.
live_base._active = _active_v43
live_base.refresh_live = refresh_live_v43


_old_home = core.render_page


def render_page_v43() -> str:
    return _old_home().replace("v0.42", "v0.43", 1)


core.render_page = render_page_v43

_old_team = feature.render_team_page


def render_team_page_v43(team_key: str) -> str:
    return _old_team(team_key).replace("v0.42", "v0.43")


feature.render_team_page = render_team_page_v43
app = core.app
