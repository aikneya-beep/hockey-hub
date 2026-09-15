from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import time

import requests

import app_v23 as stable
import app_v19 as feature
import app_v05 as core

core.app.version = "0.27.0"
KHL_BASE = "https://khl.api.webcaster.pro/api/khl_mobile"
PARAMS = {"locale": "ru", "application": "khl_web"}
HEADERS = {"User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)", "Accept-Language": "ru-RU,ru;q=0.9"}


def _get_teams() -> list[dict]:
    r = requests.get(f"{KHL_BASE}/teams_v2.json", params=PARAMS, headers=HEADERS, timeout=15)
    r.raise_for_status()
    raw = core.unwrap_list(r.json(), ("data", "teams", "items"))
    return [x.get("team", x) if isinstance(x, dict) else x for x in raw if isinstance(x, dict)]


def _events(query: dict, max_pages: int = 100) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        r = requests.get(
            f"{KHL_BASE}/events_v2.json",
            params={**PARAMS, **query, "page": page},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        items = core.unwrap_list(r.json(), ("data", "events", "items"))
        if not items:
            break
        for wrapped in items:
            event = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
            if isinstance(event, dict):
                out.append(event)
    return out


def _ska_id(teams: list[dict]) -> str:
    team = next((t for t in teams if core.team_name(t).casefold() == "ска"), None)
    if not team or team.get("id") is None:
        raise ValueError("KHL API: СКА не найден")
    return str(team["id"])


def fetch_khl_v27(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    if wanted_name != "СКА":
        return feature.fetch_khl_v19(api_base, league, wanted_name)

    teams = _get_teams()
    tid = _ska_id(teams)
    now = datetime.now(core.MOSCOW)
    start = int((feature.REGULAR_START - timedelta(hours=1)).timestamp())
    now_ts = int(now.timestamp())
    future_end = int((now + timedelta(days=260)).timestamp())

    # History is a dedicated team query ending at 'now'. This is the combination
    # the KHL backend reliably returns for completed games.
    past_query = {
        "q[start_at_gt_time_from_unixtime]": start,
        "q[start_at_lt_time_from_unixtime]": now_ts,
        "q[team_a_or_team_b_in][]": tid,
        "order_direction": "asc",
    }
    # A small overlap lets a just-finished game move from upcoming/live to history
    # without disappearing between refreshes.
    future_query = {
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(hours=6)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": future_end,
        "q[team_a_or_team_b_in][]": tid,
        "order_direction": "asc",
    }

    by_id: dict[str, core.Game] = {}
    for event in _events(past_query, 12) + _events(future_query, 20):
        if event.get("not_regular") is True:
            continue
        game = feature._event_game(event, league, now)
        if game is None or game.start_at < feature.REGULAR_START:
            continue
        current = by_id.get(game.source_game_id)
        # Prefer finished/live records over a scheduled copy from an overlapping query.
        priority = {"scheduled": 0, "live": 1, "finished": 2}
        if current is None or priority.get(game.status, 0) >= priority.get(current.status, 0):
            by_id[game.source_game_id] = game

    games = sorted(by_id.values(), key=lambda g: g.start_at)
    finished = [g for g in games if g.status == "finished"]
    if not games:
        raise ValueError("KHL API не вернул матчи СКА")
    print(
        f"[verify] SKA v27 official games={len(games)} finished={len(finished)}: "
        + "; ".join(f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}" for g in finished[-10:]),
        flush=True,
    )
    return games


core.fetch_khl = fetch_khl_v27


def _computed_west_standings() -> dict:
    teams = _get_teams()
    ska = next((t for t in teams if core.team_name(t).casefold() == "ска"), None)
    if not ska:
        raise ValueError("KHL API: нет метаданных СКА")
    conference = ska.get("conference")
    west = [t for t in teams if not conference or t.get("conference") == conference]
    ids = {str(t.get("id")): core.team_name(t) for t in west if t.get("id") is not None}
    if "СКА" not in ids.values():
        raise ValueError("KHL API: СКА не попал в Западную конференцию")

    now = datetime.now(core.MOSCOW)
    query = {
        "q[start_at_gt_time_from_unixtime]": int((feature.REGULAR_START - timedelta(hours=1)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int(now.timestamp()),
        "order_direction": "asc",
    }
    events = _events(query, 100)

    # gp, wins, losses, gf, ga, pts, regulation wins, OT wins, SO wins
    stat = defaultdict(lambda: {"gp": 0, "w": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0, "rw": 0, "otw": 0, "sow": 0})
    used = 0
    for e in events:
        if e.get("not_regular") is True:
            continue
        state = str(e.get("game_state_key") or "").casefold()
        if state != "finished":
            continue
        ta = e.get("team_a") or {}
        tb = e.get("team_b") or {}
        aid = str(ta.get("id") or "")
        bid = str(tb.get("id") or "")
        if aid not in ids or bid not in ids:
            continue
        hs, aw = core.parse_score(e.get("score"))
        if hs is None or aw is None or hs == aw:
            continue
        used += 1
        a = stat[aid]
        b = stat[bid]
        a["gp"] += 1; b["gp"] += 1
        a["gf"] += hs; a["ga"] += aw
        b["gf"] += aw; b["ga"] += hs
        winner, loser = (a, b) if hs > aw else (b, a)
        winner["w"] += 1; loser["l"] += 1
        winner["pts"] += 2

        scores = e.get("scores") or {}
        is_so = isinstance(scores, dict) and bool(scores.get("bullitt"))
        is_ot = isinstance(scores, dict) and bool(scores.get("overtime"))
        if is_so:
            winner["sow"] += 1
            loser["pts"] += 1
        elif is_ot:
            winner["otw"] += 1
            loser["pts"] += 1
        else:
            winner["rw"] += 1

    rows = []
    sortable = []
    for tid, name in ids.items():
        s = stat[tid]
        sortable.append((tid, name, s))

    # KHL tie-break starts with regulation wins, then overtime/shootout wins;
    # goal difference and goals scored are sufficient for the remaining visible ties here.
    sortable.sort(key=lambda x: (
        -x[2]["pts"], -x[2]["rw"], -x[2]["otw"], -x[2]["sow"],
        -(x[2]["gf"] - x[2]["ga"]), -x[2]["gf"], x[1]
    ))
    for pos, (_tid, name, s) in enumerate(sortable, 1):
        rows.append([
            str(pos), name, str(s["gp"]), str(s["w"]), str(s["l"]),
            f"{s['gf']}:{s['ga']}", str(s["pts"]),
        ])

    if not rows or used == 0:
        raise ValueError("KHL API: не удалось посчитать таблицу по матчам")
    print(f"[verify] KHL computed standings games={used} SKA=" + next(("/".join(r) for r in rows if r[1] == "СКА"), "?"), flush=True)
    return {
        "title": "Западная конференция",
        "headers": ["М", "Команда", "И", "В", "П", "Ш", "О"],
        "rows": rows,
        "source": "https://www.khl.ru/standings/",
        "note": "рассчитано автоматически по официальным матчам КХЛ",
    }


# Keep the existing tables_v2 parser as the fast path, but never depend on it.
_fast_table = feature._fetch_khl_standings


def khl_standings_v27() -> dict:
    try:
        data = _fast_table()
        data["note"] = "данные КХЛ"
        return data
    except Exception as exc:
        print(f"[standings] tables_v2 unavailable, compute from games: {type(exc).__name__}: {exc}", flush=True)
    try:
        return _computed_west_standings()
    except Exception as exc:
        print(f"[standings] computed KHL table failed: {type(exc).__name__}: {exc}", flush=True)
        snapshot = dict(stable._KHL_SNAPSHOT)
        snapshot["note"] = "аварийная резервная копия на 15.09.2026"
        return snapshot


feature._fetch_khl_standings = khl_standings_v27
feature.STANDINGS_CACHE.pop("ska", None)

_old_team_page = feature.render_team_page


def render_team_page_v27(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.23", "v0.27")


feature.render_team_page = render_team_page_v27


def render_page_v27() -> str:
    return stable.render_page_v23().replace("v0.23", "v0.27", 1)


core.render_page = render_page_v27
app = core.app
