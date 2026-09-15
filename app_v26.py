from __future__ import annotations

from datetime import datetime, timedelta
from threading import Thread
import time

import requests

import app_v23 as stable
import app_v20 as seeded
import app_v19 as khlbase
import app_v05 as core

core.app.version = "0.26.0"
KHL_BASE = "https://khl.api.webcaster.pro/api/khl_mobile"
PARAMS = {"locale": "ru", "application": "khl_web"}
HEADERS = {"User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)", "Accept-Language": "ru-RU,ru;q=0.9"}


def _ska_id() -> str:
    r = requests.get(f"{KHL_BASE}/teams_v2.json", params=PARAMS, headers=HEADERS, timeout=20)
    r.raise_for_status()
    raw = core.unwrap_list(r.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw]
    team = next(t for t in teams if core.team_name(t).casefold() == "ска")
    return str(team["id"])


def _probe(label: str, extra: dict, pages: int = 4) -> None:
    seen = []
    for page in range(1, pages + 1):
        try:
            r = requests.get(
                f"{KHL_BASE}/events_v2.json",
                params={**PARAMS, **extra, "page": page},
                headers=HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            items = core.unwrap_list(r.json(), ("data", "events", "items"))
        except Exception as exc:
            print(f"[khl-probe] {label} page={page} ERROR {type(exc).__name__}: {exc}", flush=True)
            break
        if not items:
            break
        for wrapped in items:
            e = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
            if not isinstance(e, dict):
                continue
            raw_time = e.get("start_at") or e.get("event_start_at")
            if raw_time is None:
                continue
            try:
                dt = khlbase._dt(raw_time)
            except Exception:
                continue
            ta = core.team_name(e.get("team_a") or {})
            tb = core.team_name(e.get("team_b") or {})
            if "СКА" not in (ta, tb) and "team" not in label:
                continue
            seen.append((dt, ta, tb, e.get("score"), e.get("game_state_key"), e.get("id")))
    seen.sort(key=lambda x: x[0])
    tail = "; ".join(f"{x[0]:%d.%m %H:%M} {x[1]}-{x[2]} {x[3]!r} {x[4]!r}" for x in seen[-12:])
    print(f"[khl-probe] {label} n={len(seen)} :: {tail}", flush=True)


def _diagnose() -> None:
    time.sleep(5)
    try:
        tid = _ska_id()
        now = datetime.now(core.MOSCOW)
        start = int((khlbase.REGULAR_START - timedelta(hours=1)).timestamp())
        end = int(now.timestamp())
        print(f"[khl-probe] SKA_ID={tid} start={start} end={end}", flush=True)
        common = {
            "q[start_at_gt_time_from_unixtime]": start,
            "q[start_at_lt_time_from_unixtime]": end,
        }
        _probe("team-window-asc", {**common, "q[team_a_or_team_b_in][]": tid, "order_direction": "asc"}, 8)
        _probe("team-window-desc", {**common, "q[team_a_or_team_b_in][]": tid, "order_direction": "desc"}, 8)
        _probe("team-no-window-desc", {"q[team_a_or_team_b_in][]": tid, "order_direction": "desc"}, 12)
        _probe("league-window-desc", {**common, "order_direction": "desc"}, 20)
    except Exception as exc:
        print(f"[khl-probe] FATAL {type(exc).__name__}: {exc}", flush=True)


@core.app.on_event("startup")
def run_khl_probe() -> None:
    Thread(target=_diagnose, daemon=True).start()

# Keep the last stable behavior while diagnostics run.
core.fetch_khl = seeded.fetch_khl_v20


def render_page_v26() -> str:
    return stable.render_page_v23().replace("v0.23", "v0.26", 1)


core.render_page = render_page_v26
app = core.app
