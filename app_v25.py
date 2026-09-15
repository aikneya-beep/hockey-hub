from __future__ import annotations

import app_v24 as prev
import app_v19 as khlbase
import app_v05 as core

# Render is blocked by api.sofascore.com (403), while Sofascore also exposes
# the same JSON routes through its main web host.
prev.SOFA_BASE = "https://www.sofascore.com/api/v1"
prev._SOFA_CACHE.clear()
khlbase.STANDINGS_CACHE.pop("ska", None)

core.app.version = "0.25.0"
core.fetch_khl = prev.fetch_khl_v24
khlbase._fetch_khl_standings = prev.sofa_khl_standings_v24

_old_team_page = khlbase.render_team_page


def render_team_page_v25(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.24", "v0.25")


khlbase.render_team_page = render_team_page_v25


def render_page_v25() -> str:
    return prev.render_page_v24().replace("v0.24", "v0.25", 1)


core.render_page = render_page_v25
app = core.app
