from __future__ import annotations

import app_v40
import personal_hockey_v42  # registers /my-hockey, POST form and APIs
import app_v19 as feature
import app_v05 as core

core.app.version = "0.42.0"

_old_home = core.render_page


def render_page_v42() -> str:
    page = _old_home().replace("v0.40", "v0.42", 1)
    if 'href="/my-hockey"' not in page:
        page = page.replace(
            "</nav>",
            '<a class="personal-main" href="/my-hockey">Мой прогресс</a></nav>',
            1,
        )
    css = '.personal-main{align-self:center;color:#d6deea;text-decoration:none;font-size:12px;padding:8px 10px;border:1px solid #42516a;border-radius:9px;background:#151b24}.personal-main:hover{border-color:#7186aa}'
    page = page.replace("</style>", css + "</style>", 1)
    return page


core.render_page = render_page_v42

_old_team = feature.render_team_page


def render_team_page_v42(team_key: str) -> str:
    page = _old_team(team_key).replace("v0.40", "v0.42")
    if 'href="/my-hockey"' not in page:
        page = page.replace(
            '<button type="button" id="spoilerToggle"',
            '<a class="personal-team" href="/my-hockey">Мой прогресс</a><button type="button" id="spoilerToggle"',
            1,
        )
    css = '.personal-team{color:#c9d4e4;text-decoration:none;font-size:12px;margin-right:10px;white-space:nowrap}'
    page = page.replace("</style>", css + "</style>", 1)
    return page


feature.render_team_page = render_team_page_v42
app = core.app
