from __future__ import annotations

from fastapi.responses import HTMLResponse

import app_v33 as prev
import app_v19 as feature
import app_v05 as core
from persistence import HockeyStorage

core.app.version = "0.34.0"
STORE = HockeyStorage.from_env()


# Keep the proven collectors and UI as the source of truth for now. After each
# successful refresh, mirror the exact normalized game objects into PostgreSQL.
_old_refresh_all = core.refresh_all


def refresh_all_v34() -> None:
    _old_refresh_all()
    with core.LOCK:
        games = list(core.GAMES.values())
    STORE.mirror(core.TEAMS, games)


core.refresh_all = refresh_all_v34

# Best-effort initial mirror. With no DATABASE_URL this is an intentional no-op.
with core.LOCK:
    _initial_games = list(core.GAMES.values())
STORE.mirror(core.TEAMS, _initial_games)


@core.app.get("/api/v1/storage")
def api_storage():
    status = STORE.status()
    return {
        **status,
        "mode": "postgres_mirror" if status["enabled"] else "in_memory_only",
        "reads_from": "in_memory",
        "migration_phase": "mirror_and_verify",
    }


# Version wrappers only; v0.34 intentionally makes no visual redesign.
_old_team_page = feature.render_team_page


def render_team_page_v34(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.33", "v0.34")


feature.render_team_page = render_team_page_v34


def render_page_v34() -> str:
    return prev.render_page_v33().replace("v0.33", "v0.34", 1)


core.render_page = render_page_v34

_old_playoffs_page = prev.render_playoffs_page


def render_playoffs_page_v34() -> str:
    return _old_playoffs_page().replace("v0.33", "v0.34")


# v0.33's FastAPI endpoint resolves this name dynamically in its own module.
prev.render_playoffs_page = render_playoffs_page_v34

app = core.app
