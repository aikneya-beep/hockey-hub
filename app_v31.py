from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import app_v28 as results
import app_v27 as api
import app_v23 as stable
import app_v19 as feature
import app_v05 as core

core.app.version = "0.31.0"
core.fetch_khl = results.fetch_khl_v28


def _official_west_standings() -> dict:
    teams = api._get_teams()
    team_by_id = {str(t.get("id")): t for t in teams if t.get("id") is not None}
    ska = next((t for t in teams if core.team_name(t).casefold() == "ска"), None)
    if not ska:
        raise ValueError("KHL API: нет СКА в teams_v2")
    conference = ska.get("conference")
    west_ids = {
        str(t.get("id"))
        for t in teams
        if t.get("id") is not None and (not conference or t.get("conference") == conference)
    }
    if str(ska.get("id")) not in west_ids:
        raise ValueError("KHL API: СКА не попал в Западную конференцию")

    events = api._events({
        "q[start_at_gt_time_from_unixtime]": int((feature.REGULAR_START - timedelta(hours=1)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int(datetime.now(core.MOSCOW).timestamp()),
        "order_direction": "asc",
    }, 100)

    # KHL tie-break fields: regulation wins, OT wins, shootout wins, goal diff, goals for.
    stat = defaultdict(lambda: {
        "gp": 0, "rw": 0, "otw": 0, "sow": 0,
        "sol": 0, "otl": 0, "rl": 0,
        "gf": 0, "ga": 0, "pts": 0,
    })
    used_games = 0

    for e in events:
        if e.get("not_regular") is True:
            continue
        if str(e.get("game_state_key") or "").casefold() != "finished":
            continue
        ta = e.get("team_a") or {}
        tb = e.get("team_b") or {}
        aid = str(ta.get("id") or "")
        bid = str(tb.get("id") or "")
        if aid not in team_by_id or bid not in team_by_id:
            continue
        # A Western team's games against BOTH conferences count in Western standings.
        if aid not in west_ids and bid not in west_ids:
            continue
        hs, aw = core.parse_score(e.get("score"))
        if hs is None or aw is None or hs == aw:
            continue

        scores = e.get("scores") or {}
        is_so = isinstance(scores, dict) and bool(scores.get("bullitt"))
        is_ot = (not is_so) and isinstance(scores, dict) and bool(scores.get("overtime"))
        winner_id = aid if hs > aw else bid
        loser_id = bid if hs > aw else aid
        used_games += 1

        # Update each Western participant independently; the opponent may be Eastern.
        for tid, gf, ga, won in (
            (aid, hs, aw, aid == winner_id),
            (bid, aw, hs, bid == winner_id),
        ):
            if tid not in west_ids:
                continue
            s = stat[tid]
            s["gp"] += 1
            s["gf"] += gf
            s["ga"] += ga
            if won:
                s["pts"] += 2
                if is_so:
                    s["sow"] += 1
                elif is_ot:
                    s["otw"] += 1
                else:
                    s["rw"] += 1
            else:
                if is_so:
                    s["sol"] += 1
                    s["pts"] += 1
                elif is_ot:
                    s["otl"] += 1
                    s["pts"] += 1
                else:
                    s["rl"] += 1

    sortable = []
    for tid in west_ids:
        t = team_by_id.get(tid) or {}
        name = core.team_name(t)
        if not name:
            continue
        s = stat[tid]
        sortable.append((tid, name, s))

    # Article 14 KHL sporting regulations: points -> regulation wins -> OT wins
    # -> shootout wins -> goal differential -> goals scored.
    sortable.sort(key=lambda x: (
        -x[2]["pts"],
        -x[2]["rw"],
        -x[2]["otw"],
        -x[2]["sow"],
        -(x[2]["gf"] - x[2]["ga"]),
        -x[2]["gf"],
        x[1],
    ))

    rows = []
    for pos, (_tid, name, s) in enumerate(sortable, 1):
        wins = s["rw"] + s["otw"] + s["sow"]
        losses = s["rl"] + s["otl"] + s["sol"]
        rows.append([
            str(pos), name, str(s["gp"]), str(wins), str(losses),
            f"{s['gf']}:{s['ga']}", str(s["pts"]),
        ])

    ska_row = next((r for r in rows if r[1] == "СКА"), None)
    if not ska_row or used_games == 0:
        raise ValueError("KHL API: не удалось посчитать таблицу Запада")

    # Useful verification of the actual tie-break state around SKA.
    top = []
    for _tid, name, s in sortable[:5]:
        top.append(
            f"{name}: pts={s['pts']} rw={s['rw']} otw={s['otw']} sow={s['sow']} {s['gf']}:{s['ga']}"
        )
    print(
        f"[verify] KHL v31 official standings games={used_games} SKA={'/'.join(ska_row)} top=" + " | ".join(top),
        flush=True,
    )
    return {
        "title": "Западная конференция",
        "headers": ["М", "Команда", "И", "В", "П", "Ш", "О"],
        "rows": rows,
        "source": "https://www.khl.ru/standings/",
        "note": "рассчитано автоматически по официальным матчам КХЛ",
    }


def khl_standings_v31() -> dict:
    try:
        return _official_west_standings()
    except Exception as exc:
        print(f"[standings] official KHL calculation failed: {type(exc).__name__}: {exc}", flush=True)
        snapshot = dict(stable._KHL_SNAPSHOT)
        snapshot["note"] = "аварийная резервная копия на 15.09.2026"
        return snapshot


feature._fetch_khl_standings = khl_standings_v31
feature.STANDINGS_CACHE.pop("ska", None)

_old_team_page = feature.render_team_page


def render_team_page_v31(team_key: str) -> str:
    # v0.30 was diagnostic only; user-facing stable lineage is v0.29.
    page = _old_team_page(team_key)
    for old in ("v0.30", "v0.29", "v0.28"):
        page = page.replace(old, "v0.31")
    return page


feature.render_team_page = render_team_page_v31


def render_page_v31() -> str:
    return stable.render_page_v23().replace("v0.23", "v0.31", 1)


core.render_page = render_page_v31
app = core.app
