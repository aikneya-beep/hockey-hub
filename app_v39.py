from __future__ import annotations

import app_v38 as prev
import app_v33 as playoff_ui
import app_v19 as feature
import app_v05 as core
from league_live_v39 import (
    MHL_CALENDAR,
    VHL_TEAM_CALENDAR,
    cached_team_games,
    overlay_mhl_live,
)
from vhl_online_v39 import overlay_vhl_live

core.app.version = "0.39.0"

# Use the stable schedule parser that v0.38 wrapped, but do not perform the
# second SKA-site request for per-match links: v0.39 points users at the league
# live/video services instead. This also cuts the number of fragile club-site
# requests in half.
_base_fetch_ska_site = prev._old_fetch_ska_site


def fetch_ska_site_v39(url: str, wanted_name: str, league: str):
    try:
        games = _base_fetch_ska_site(url, wanted_name, league)
    except Exception as exc:
        games = cached_team_games(wanted_name, league)
        if not games:
            raise
        print(
            f"[schedule] {wanted_name}: club site unavailable, keep cached schedule: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

    if league == "МХЛ":
        # Default to the official league calendar; when today's official text
        # center exposes a concrete live/video page, overlay_mhl_live replaces it.
        for game in games:
            game.source_url = MHL_CALENDAR
        overlay_mhl_live(games, wanted_name)
    elif league == "ВХЛ":
        # Future/non-live matches point at the official VHL team calendar. During
        # a live game the official online center replaces this with the concrete
        # text/live match page.
        for game in games:
            game.source_url = VHL_TEAM_CALENDAR
        overlay_vhl_live(games, wanted_name)
    return games


core.fetch_ska_site = fetch_ska_site_v39

# Version skin only; all v0.37 series-card behaviour remains, but the corrected
# postseason detector now keeps those cards hidden during the regular season.
_old_team_page = feature.render_team_page


def render_team_page_v39(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.38", "v0.39")


feature.render_team_page = render_team_page_v39

_old_home = core.render_page


def render_page_v39() -> str:
    return _old_home().replace("v0.38", "v0.39", 1)


core.render_page = render_page_v39

_old_playoffs = playoff_ui.render_playoffs_page


def render_playoffs_page_v39() -> str:
    return _old_playoffs().replace("v0.38", "v0.39")


playoff_ui.render_playoffs_page = render_playoffs_page_v39

app = core.app
