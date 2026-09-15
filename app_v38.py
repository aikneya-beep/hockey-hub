from __future__ import annotations

import app_v37 as prev
import app_v33 as playoff_ui
import app_v28 as khl_event_ui
import app_v19 as feature
import app_v05 as core
from source_links_v38 import enrich_ska_site_match_links, khl_match_url

core.app.version = "0.38.0"

# ---------------------------------------------------------------------------
# Canonical KHL match URLs
# ---------------------------------------------------------------------------
_old_khl_game_from_event = khl_event_ui._game_from_event


def _game_from_event_v38(event: dict, league: str, now):
    game = _old_khl_game_from_event(event, league, now)
    if game is None:
        return None
    canonical = khl_match_url(event)
    if canonical:
        game.source_url = canonical
    return game


khl_event_ui._game_from_event = _game_from_event_v38

# ---------------------------------------------------------------------------
# Per-match links for SKA-family VHL/MHL pages
# ---------------------------------------------------------------------------
_old_fetch_ska_site = core.fetch_ska_site


def fetch_ska_site_v38(url: str, wanted_name: str, league: str):
    games = _old_fetch_ska_site(url, wanted_name, league)
    enrich_ska_site_match_links(url, wanted_name, games)
    return games


core.fetch_ska_site = fetch_ska_site_v38

# Existing SPbHL parser already uses the concrete Match.aspx link from each row;
# no wrapper is needed there.

_old_team_page = feature.render_team_page


def render_team_page_v38(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.37", "v0.38")


feature.render_team_page = render_team_page_v38

_old_home = core.render_page


def render_page_v38() -> str:
    return _old_home().replace("v0.37", "v0.38", 1)


core.render_page = render_page_v38

_old_playoffs = playoff_ui.render_playoffs_page


def render_playoffs_page_v38() -> str:
    return _old_playoffs().replace("v0.37", "v0.38")


playoff_ui.render_playoffs_page = render_playoffs_page_v38

app = core.app
