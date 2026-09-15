from __future__ import annotations

from datetime import datetime

import app_v35 as prev
import app_v33 as playoff_ui
import app_v19 as feature
import app_v05 as core
from khl_schedule_v36 import fetch_khl_with_postseason
from playoff_monitor import build_snapshot
from postseason_adapters import PLANS, calendar_label
from postseason_sources import probe_playoff_page

core.app.version = "0.36.0"

# Unlike v0.28, keep KHL events marked `not_regular` in the tracked match feed.
# The standings calculator still excludes them, so playoff games cannot pollute
# the regular-season table.
core.fetch_khl = fetch_khl_with_postseason

# Keep the visible postseason hints generated from the same season plans that
# drive stage detection, so UI text and backend logic cannot drift apart.
for _team in core.TEAMS:
    playoff_ui.PLAYOFF_CALENDAR[_team.key] = calendar_label(_team.key)

# Source-specific postseason probe for the SKA family sites. The probe is used
# only when the official playoff window has actually started; before that, the
# calendar/qualification model remains authoritative and cannot jump early.
def _snapshots_v36():
    now = datetime.now(core.MOSCOW)
    with core.LOCK:
        games = list(core.GAMES.values())
    out = []
    for team in core.TEAMS:
        try:
            table = feature._fetch_standings(team.key)
            plan = PLANS.get(team.key)
            if plan and plan.playoff_start and now.date() >= plan.playoff_start and team.key in {"ska_vmf", "ska_1946", "academy"}:
                probe = probe_playoff_page(team.key, team.name)
                if probe.get("active"):
                    table = dict(table)
                    table["postseason_stage"] = "playoff"
                    table["source"] = probe.get("url") or table.get("source")
                    table["title"] = f"Плей-офф {team.league}"
                    print(f"[verify] postseason source {team.key}: active {probe.get('url')}", flush=True)
            snap = build_snapshot(team.key, team.name, team.league, table, games, now)
            out.append((team, table, snap, None))
        except Exception as exc:
            out.append((team, {}, None, f"{type(exc).__name__}: {exc}"))
    return out


playoff_ui._snapshots = _snapshots_v36

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
