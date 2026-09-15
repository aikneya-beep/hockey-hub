from __future__ import annotations

import app_v35 as prev
import app_v33 as playoff_ui
import app_v19 as feature
import app_v05 as core
from postseason_adapters import calendar_label

core.app.version = "0.36.0"

# Keep the visible postseason hints generated from the same season plans that
# drive stage detection, so UI text and backend logic cannot drift apart.
for _team in core.TEAMS:
    playoff_ui.PLAYOFF_CALENDAR[_team.key] = calendar_label(_team.key)

_old_team_page = feature.render_team_page


def render_team_page_v36(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.35", "v0.36")


feature.render_team_page = render_team_page_v36

_old_home = core.render_page


def render_page_v36() -> str:
    return _old_home().replace("v0.35", "v0.36", 1)


core.render_page = render_page_v36

_old_playoffs = playoff_ui.render_playoffs_page


def render_playoffs_page_v36() -> str:
    return _old_playoffs().replace("v0.35", "v0.36")


playoff_ui.render_playoffs_page = render_playoffs_page_v36

app = core.app
