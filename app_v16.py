from datetime import datetime, timedelta
import re
import requests

import app_v13 as spb
import app_v10 as ui
import app_v05 as core

REGULAR_START = datetime(2026, 9, 5, tzinfo=core.MOSCOW)


def fetch_khl(api_base, league, wanted_name):
    params = {"locale": "ru", "application": "khl_web"}
    headers = {"User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)"}
    r = requests.get(f"{api_base}/teams_v2.json", params=params, headers=headers, timeout=25)
    r.raise_for_status()
    raw = core.unwrap_list(r.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw]
    team = next((x for x in teams if core.team_name(x).casefold() == wanted_name.casefold()), None)
    if not team:
        raise ValueError(f"команда {wanted_name} не найдена")

    now = datetime.now(core.MOSCOW)
    result = {}

    def collect(start, end, direction):
        base_query = {
            **params,
            "q[start_at_gt_time_from_unixtime]": int(start.timestamp()),
            "q[start_at_lt_time_from_unixtime]": int(end.timestamp()),
            "q[team_a_or_team_b_in][]": str(team["id"]),
            "order_direction": direction,
        }
        seen = set()
        for page in range(1, 12):
            resp = requests.get(f"{api_base}/events_v2.json", params={**base_query, "page": page}, headers=headers, timeout=25)
            resp.raise_for_status()
            items = core.unwrap_list(resp.json(), ("data", "events", "items"))
            if not items:
                break
            new = 0
            for item in items:
                e = item.get("event", item) if isinstance(item, dict) else item
                if not isinstance(e, dict) or e.get("type_id") not in (None, 24):
                    continue
                eid = str(e.get("id") or e.get("khl_id") or "")
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                raw_time = e.get("start_at") or e.get("event_start_at")
                if raw_time is None:
                    continue
                raw_time = int(raw_time) if isinstance(raw_time, str) and raw_time.isdigit() else raw_time
                if isinstance(raw_time, (int, float)):
                    ts = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
                    dt = datetime.fromtimestamp(ts, core.MOSCOW)
                else:
                    dt = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00")).astimezone(core.MOSCOW)
                if wanted_name == "СКА" and dt < REGULAR_START:
                    continue
                hs, aw = core.parse_score(e.get("score"))
                state = str(e.get("game_state_key") or "").casefold()
                if state == "finished" or (dt < now - timedelta(hours=4) and hs is not None and aw is not None and (hs or aw)):
                    status = "finished"
                elif state == "in_progress":
                    status = "live"
                else:
                    status = "scheduled"
                    hs = aw = None
                scores = e.get("scores") or {}
                decision = "SO" if isinstance(scores, dict) and scores.get("bullitt") else "OT" if isinstance(scores, dict) and scores.get("overtime") else None
                khl_id = e.get("khl_id")
                result[eid] = core.Game(
                    "khl_api", eid, league,
                    core.team_name(e.get("team_a") or {}), core.team_name(e.get("team_b") or {}),
                    dt, status, hs, aw, decision,
                    core.compact(e.get("location") or "") or None,
                    f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None,
                )
                new += 1
            if new == 0:
                break

    collect(REGULAR_START, now + timedelta(hours=4), "desc")
    collect(now - timedelta(hours=4), now + timedelta(days=260), "asc")
    games = sorted(result.values(), key=lambda g: g.start_at)
    finished = [g for g in games if g.status == "finished"]
    print("[verify] SKA v16: " + "; ".join(f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}" for g in finished[-10:]), flush=True)
    if not games:
        raise ValueError("KHL API не вернул матчи")
    return games


core.fetch_khl = fetch_khl
core.fetch_spbhl = spb.fetch_spbhl_v13
core.app.version = "0.16.0"


def render_page():
    page = ui.render_page_v10()
    return re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.16", page, count=1)


core.render_page = render_page
app = core.app
