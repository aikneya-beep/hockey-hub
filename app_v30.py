from __future__ import annotations

from datetime import datetime, timedelta
from threading import Thread
import time

import app_v29 as stable
import app_v27 as api
import app_v19 as feature
import app_v05 as core

core.app.version = "0.30.0"
core.fetch_khl = stable.prev.fetch_khl_v28
feature._fetch_khl_standings = stable.khl_standings_v29
feature.STANDINGS_CACHE.pop("ska", None)


def _inspect_khl_scores() -> None:
    time.sleep(5)
    try:
        events = api._events({
            "q[start_at_gt_time_from_unixtime]": int((feature.REGULAR_START - timedelta(hours=1)).timestamp()),
            "q[start_at_lt_time_from_unixtime]": int(datetime.now(core.MOSCOW).timestamp()),
            "order_direction": "asc",
        }, 50)
        for e in events:
            if str(e.get("game_state_key") or "").casefold() != "finished":
                continue
            ta = core.team_name(e.get("team_a") or {})
            tb = core.team_name(e.get("team_b") or {})
            if "СКА" not in (ta, tb):
                continue
            dt = feature._dt(e.get("start_at") or e.get("event_start_at"))
            print(
                "[khl-scoremeta] "
                + f"{dt:%d.%m} {ta}-{tb} score={e.get('score')!r} "
                + f"scores={e.get('scores')!r} overtime={e.get('overtime')!r} bullitt={e.get('bullitt')!r} "
                + f"result_type={e.get('result_type')!r} game_type={e.get('game_type')!r} "
                + f"type_id={e.get('type_id')!r} keys={[k for k in e.keys() if 'time' in k.lower() or 'period' in k.lower() or 'score' in k.lower() or 'bull' in k.lower() or 'over' in k.lower()]}",
                flush=True,
            )
    except Exception as exc:
        print(f"[khl-scoremeta] ERROR {type(exc).__name__}: {exc}", flush=True)


@core.app.on_event("startup")
def run_scoremeta_probe() -> None:
    Thread(target=_inspect_khl_scores, daemon=True).start()

_old_team_page = feature.render_team_page


def render_team_page_v30(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.29", "v0.30")


feature.render_team_page = render_team_page_v30


def render_page_v30() -> str:
    return stable.render_page_v29().replace("v0.29", "v0.30", 1)


core.render_page = render_page_v30
app = core.app
