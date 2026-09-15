from __future__ import annotations

from datetime import datetime, timedelta
from threading import Thread
import time

import app_v39
import app_v19 as feature
import app_v05 as core

LIVE_SECONDS = 75
FULL_SECONDS = 1800


def _active(now=None):
    now = now or datetime.now(core.MOSCOW)
    with core.LOCK:
        return any(
            g.league in {"КХЛ", "ВХЛ", "МХЛ"}
            and g.status != "finished"
            and g.start_at - timedelta(minutes=20) <= now <= g.start_at + timedelta(hours=5)
            for g in core.GAMES.values()
        )


def refresh_live():
    now = datetime.now(core.MOSCOW)
    if not _active(now):
        return
    for team in core.TEAMS:
        if team.league not in {"КХЛ", "ВХЛ", "МХЛ"}:
            continue
        with core.LOCK:
            relevant = [g for g in core.GAMES.values() if team.name in (g.home_team, g.away_team)]
        if not any(g.status != "finished" and g.start_at - timedelta(minutes=20) <= now <= g.start_at + timedelta(hours=5) for g in relevant):
            continue
        try:
            games = core.fetch_team(team)
            with core.LOCK:
                for game in games:
                    core.GAMES[(game.source, game.source_game_id)] = game
            print(f"[live-fast] {team.name}: OK {len(games)}", flush=True)
        except Exception as exc:
            print(f"[live-fast] {team.name}: {type(exc).__name__}: {exc}", flush=True)


def refresh_loop_v40():
    core.refresh_all()
    last_full = time.monotonic()
    while True:
        time.sleep(LIVE_SECONDS)
        refresh_live()
        if time.monotonic() - last_full >= FULL_SECONDS:
            core.refresh_all()
            last_full = time.monotonic()


core.refresh_loop = refresh_loop_v40
core.app.version = "0.40.0"


def _reload(page: str) -> str:
    if not _active():
        return page
    script = f"<script>setTimeout(()=>location.reload(),{(LIVE_SECONDS + 5) * 1000})</script>"
    return page.replace("</body>", script + "</body>", 1)


_old_home = core.render_page
core.render_page = lambda: _reload(_old_home().replace("v0.39", "v0.40", 1))

_old_team = feature.render_team_page
feature.render_team_page = lambda team_key: _reload(_old_team(team_key).replace("v0.39", "v0.40"))


@core.app.get("/live-status")
def live_status():
    return {"enabled": _active(), "interval_seconds": LIVE_SECONDS}


app = core.app
