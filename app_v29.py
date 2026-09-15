from __future__ import annotations

import app_v28 as prev
import app_v27 as calc
import app_v21 as raw
import app_v23 as stable
import app_v19 as feature
import app_v05 as core

core.app.version = "0.29.0"

# Results/schedule stay on the fully automatic official KHL flow from v0.28.
core.fetch_khl = prev.fetch_khl_v28


def khl_standings_v29() -> dict:
    # 1) Prefer the official ready-made KHL table when tables_v2 responds.
    try:
        data = raw._old_khl_table()
        data["note"] = "данные КХЛ"
        print("[verify] KHL standings v29 source=tables_v2 rows=" + str(len(data.get("rows") or [])), flush=True)
        return data
    except Exception as exc:
        print(f"[standings] raw tables_v2 unavailable: {type(exc).__name__}: {exc}", flush=True)

    # 2) If the table endpoint is flaky, calculate it from completed regular-season
    # games returned by the same KHL backend. No hard-coded standings involved.
    try:
        data = calc._computed_west_standings()
        print("[verify] KHL standings v29 source=official-games rows=" + str(len(data.get("rows") or [])), flush=True)
        return data
    except Exception as exc:
        print(f"[standings] official-games calculation failed: {type(exc).__name__}: {exc}", flush=True)

    # 3) Last-resort only: dated snapshot so the page remains useful during a
    # complete upstream outage. It is explicitly marked stale in the UI.
    snapshot = dict(stable._KHL_SNAPSHOT)
    snapshot["note"] = "аварийная резервная копия на 15.09.2026"
    print("[verify] KHL standings v29 source=emergency-snapshot rows=11", flush=True)
    return snapshot


feature._fetch_khl_standings = khl_standings_v29
feature.STANDINGS_CACHE.pop("ska", None)

_old_team_page = feature.render_team_page


def render_team_page_v29(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.28", "v0.29")


feature.render_team_page = render_team_page_v29


def render_page_v29() -> str:
    return prev.render_page_v28().replace("v0.28", "v0.29", 1)


core.render_page = render_page_v29
app = core.app
