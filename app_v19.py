from __future__ import annotations

from datetime import datetime, timedelta
import html
import re
import time

import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

import app_v10 as ui
import app_v13 as spb
import app_v05 as core


REGULAR_START = datetime(2026, 9, 5, tzinfo=core.MOSCOW)
KHL_BASE = "https://khl.api.webcaster.pro/api/khl_mobile"

TEAM_META = {
    "ska": {
        "name": "СКА",
        "league": "КХЛ",
        "table_url": f"{KHL_BASE}/tables_v2.json",
        "source_label": "КХЛ",
    },
    "ska_vmf": {
        "name": "СКА-ВМФ",
        "league": "ВХЛ",
        "table_url": "https://vmf.ska.ru/championship/table/",
        "source_label": "СКА-ВМФ",
    },
    "ska_1946": {
        "name": "СКА-1946",
        "league": "МХЛ",
        "table_url": "https://1946.ska.ru/championship/table/",
        "source_label": "СКА-1946",
    },
    "academy": {
        "name": "Академия СКА",
        "league": "МХЛ",
        "table_url": "https://junior.ska.ru/championship/table/",
        "source_label": "Академия СКА",
    },
    "eskulap": {
        "name": "Эскулап",
        "league": "СПбХЛ",
        "table_url": "https://spbhl.ru/Standings.aspx?TournamentID=6533",
        "source_label": "СПбХЛ",
    },
}

STANDINGS_CACHE: dict[str, tuple[float, dict]] = {}


def _dt(raw):
    if isinstance(raw, str) and raw.isdigit():
        raw = int(raw)
    if isinstance(raw, (int, float)):
        ts = raw / 1000 if raw > 10_000_000_000 else raw
        return datetime.fromtimestamp(ts, core.MOSCOW)
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return value.replace(tzinfo=core.MOSCOW) if value.tzinfo is None else value.astimezone(core.MOSCOW)


def _event_game(event: dict, league: str, now: datetime) -> core.Game | None:
    if not isinstance(event, dict) or event.get("type_id") not in (None, 24):
        return None
    eid = event.get("id") or event.get("khl_id")
    raw_time = event.get("start_at") or event.get("event_start_at")
    if eid is None or raw_time is None:
        return None
    start_at = _dt(raw_time)
    home = core.team_name(event.get("team_a") or {})
    away = core.team_name(event.get("team_b") or {})
    hs, aw = core.parse_score(event.get("score"))
    state = str(event.get("game_state_key") or "").casefold()
    if state == "finished" or (start_at < now - timedelta(hours=4) and hs is not None and aw is not None and (hs or aw)):
        status = "finished"
    elif state == "in_progress":
        status = "live"
    else:
        status = "scheduled"
        hs = aw = None
    scores = event.get("scores") or {}
    decision = (
        "SO" if isinstance(scores, dict) and scores.get("bullitt")
        else "OT" if isinstance(scores, dict) and scores.get("overtime")
        else None
    )
    khl_id = event.get("khl_id")
    return core.Game(
        "khl_api",
        str(eid),
        league,
        home,
        away,
        start_at,
        status,
        hs,
        aw,
        decision,
        core.compact(event.get("location") or "") or None,
        f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None,
    )


def fetch_khl_v19(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {"User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)", "Accept-Language": "ru-RU,ru;q=0.9"}
    now = datetime.now(core.MOSCOW)

    teams_resp = requests.get(f"{api_base}/teams_v2.json", params=params, headers=headers, timeout=25)
    teams_resp.raise_for_status()
    raw_teams = core.unwrap_list(teams_resp.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    wanted = next((x for x in teams if core.team_name(x).casefold() == wanted_name.casefold()), None)
    if not wanted:
        raise ValueError(f"команда {wanted_name} не найдена")
    wanted_id = str(wanted.get("id"))

    by_id: dict[str, core.Game] = {}

    # Future/current schedule: team filter is fast and reliable.
    future_query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(hours=4)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": wanted_id,
        "order_direction": "asc",
    }
    for page in range(1, 15):
        resp = requests.get(f"{api_base}/events_v2.json", params={**future_query, "page": page}, headers=headers, timeout=25)
        resp.raise_for_status()
        items = core.unwrap_list(resp.json(), ("data", "events", "items"))
        if not items:
            break
        added = 0
        for wrapped in items:
            event = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
            game = _event_game(event, league, now)
            if game is None:
                continue
            if wanted_name == "СКА" and game.start_at < REGULAR_START:
                continue
            by_id[game.source_game_id] = game
            added += 1
        if not added:
            break

    # Recent history: do NOT use the team query. The KHL endpoint currently
    # drops older games for that filter; fetching league events and filtering
    # locally gives us the actual finished matches.
    history_query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int(max(REGULAR_START, now - timedelta(days=45)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int(now.timestamp()),
        "order_direction": "desc",
    }
    for page in range(1, 12):
        resp = requests.get(f"{api_base}/events_v2.json", params={**history_query, "page": page}, headers=headers, timeout=25)
        resp.raise_for_status()
        items = core.unwrap_list(resp.json(), ("data", "events", "items"))
        if not items:
            break
        oldest = None
        for wrapped in items:
            event = wrapped.get("event", wrapped) if isinstance(wrapped, dict) else wrapped
            if not isinstance(event, dict):
                continue
            raw_time = event.get("start_at") or event.get("event_start_at")
            if raw_time is None:
                continue
            event_dt = _dt(raw_time)
            oldest = event_dt if oldest is None or event_dt < oldest else oldest
            ta = event.get("team_a") or {}
            tb = event.get("team_b") or {}
            ids = {str(ta.get("id") or ""), str(tb.get("id") or "")}
            names = {core.team_name(ta).casefold(), core.team_name(tb).casefold()}
            if wanted_id not in ids and wanted_name.casefold() not in names:
                continue
            game = _event_game(event, league, now)
            if game is not None and game.start_at >= REGULAR_START:
                by_id[game.source_game_id] = game
        if oldest and oldest <= REGULAR_START:
            break

    games = sorted(by_id.values(), key=lambda g: g.start_at)
    finished = [g for g in games if g.status == "finished"]
    print(
        f"[verify] SKA v19 games={len(games)} finished={len(finished)}: "
        + "; ".join(f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}" for g in finished[-10:]),
        flush=True,
    )
    if not games:
        raise ValueError(f"KHL API не вернул матчи {wanted_name}")
    return games


def _safe_num(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fetch_khl_standings() -> dict:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {"User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)"}
    tr = requests.get(f"{KHL_BASE}/teams_v2.json", params=params, headers=headers, timeout=25)
    tr.raise_for_status()
    raw_teams = core.unwrap_list(tr.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    team_map = {str(t.get("id")): t for t in teams if isinstance(t, dict) and t.get("id") is not None}
    ska = next((t for t in teams if core.team_name(t).casefold() == "ска"), None)
    conference = (ska or {}).get("conference")

    resp = requests.get(f"{KHL_BASE}/tables_v2.json", params=params, headers=headers, timeout=25)
    resp.raise_for_status()
    payload = resp.json()
    tables = payload if isinstance(payload, list) else payload.get("tables") or payload.get("data") or []
    if isinstance(tables, dict):
        tables = tables.get("tables") or [tables]

    regular_rows = []
    for table in tables if isinstance(tables, list) else []:
        if not isinstance(table, dict):
            continue
        stages = table.get("stages") or []
        for stage in stages if isinstance(stages, list) else []:
            if not isinstance(stage, dict):
                continue
            rows = stage.get("regular") or []
            if not isinstance(rows, list) or not rows:
                continue
            candidate = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tid = str(row.get("id") or row.get("team_id") or "")
                t = team_map.get(tid, {})
                if conference and t.get("conference") and t.get("conference") != conference:
                    continue
                name = core.team_name(t) if t else core.compact(row.get("name") or row.get("team_name") or tid)
                gp = _safe_num(row.get("gp"), _safe_num(row.get("w")) + _safe_num(row.get("otw")) + _safe_num(row.get("sow")) + _safe_num(row.get("sol")) + _safe_num(row.get("otl")) + _safe_num(row.get("l")))
                wins = _safe_num(row.get("w")) + _safe_num(row.get("otw")) + _safe_num(row.get("sow"))
                losses = _safe_num(row.get("l")) + _safe_num(row.get("otl")) + _safe_num(row.get("sol"))
                gf = _safe_num(row.get("gf"))
                ga = _safe_num(row.get("ga"))
                pts = _safe_num(row.get("pts"), wins * 2 + _safe_num(row.get("otl")) + _safe_num(row.get("sol")))
                candidate.append(["", name, str(gp), str(wins), str(losses), f"{gf}:{ga}", str(pts)])
            if any(r[1] == "СКА" for r in candidate):
                regular_rows = candidate
                break
        if regular_rows:
            break
    if not regular_rows:
        raise ValueError("tables_v2 не дал таблицу СКА")
    regular_rows.sort(key=lambda r: (-_safe_num(r[-1]), -(_safe_num(r[-2].split(":")[0]) - _safe_num(r[-2].split(":")[1])), r[1]))
    for idx, row in enumerate(regular_rows, 1):
        row[0] = str(idx)
    return {
        "title": conference or "Западная конференция",
        "headers": ["М", "Команда", "И", "В", "П", "Ш", "О"],
        "rows": regular_rows,
        "source": "https://www.khl.ru/",
    }


def _table_from_html(url: str, target: str) -> dict:
    resp = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub", "Accept-Language": "ru-RU,ru;q=0.9"})
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    best = None
    for table in soup.find_all("table"):
        parsed = []
        for tr in table.find_all("tr"):
            cells = [core.compact(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            cells = [c for c in cells if c]
            if cells:
                parsed.append(cells)
        if not parsed or target not in " ".join(" ".join(r) for r in parsed):
            continue
        score = len(parsed)
        if best is None or score > len(best):
            best = parsed
    if not best:
        raise ValueError(f"таблица {target} не найдена в HTML")

    # First row is normally a header. If it is clearly data, create neutral labels.
    first = best[0]
    has_header = any(x in {"Команда", "Клуб", "И", "О", "М"} for x in first)
    headers = first if has_header else ["" for _ in first]
    rows = best[1:] if has_header else best
    width = max(len(headers), *(len(r) for r in rows))
    if not any(headers):
        headers = ["" for _ in range(width)]
    headers += [""] * (width - len(headers))
    rows = [r + [""] * (width - len(r)) for r in rows]
    return {"title": "Турнирная таблица", "headers": headers, "rows": rows, "source": url}


def _fetch_standings(team_key: str) -> dict:
    cached = STANDINGS_CACHE.get(team_key)
    if cached and time.time() - cached[0] < 900:
        return cached[1]
    meta = TEAM_META[team_key]
    try:
        data = _fetch_khl_standings() if team_key == "ska" else _table_from_html(meta["table_url"], meta["name"])
    except Exception as exc:
        print(f"[standings] {meta['name']}: {type(exc).__name__}: {exc}", flush=True)
        data = {"title": "Турнирное положение", "headers": [], "rows": [], "source": meta["table_url"], "error": str(exc)}
    STANDINGS_CACHE[team_key] = (time.time(), data)
    return data


def _team_games(name: str) -> list[core.Game]:
    with core.LOCK:
        games = [g for g in core.GAMES.values() if name in (g.home_team, g.away_team)]
    # Deduplicate by real-world matchup/date, preferring a finished record with scores.
    best: dict[tuple, core.Game] = {}
    for g in games:
        key = (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold())
        old = best.get(key)
        rank = (g.status == "finished", g.home_score is not None, g.source != "spbhl_seed")
        old_rank = (old.status == "finished", old.home_score is not None, old.source != "spbhl_seed") if old else (-1, -1, -1)
        if old is None or rank > old_rank:
            best[key] = g
    return sorted(best.values(), key=lambda g: g.start_at)


def _game_row(g: core.Game) -> str:
    played = g.status == "finished"
    score = f"{g.home_score}:{g.away_score}" if played and g.home_score is not None and g.away_score is not None else "—"
    decision = " Б" if g.decision == "SO" else " ОТ" if g.decision == "OT" else ""
    url = f'<a class="src" href="{html.escape(g.source_url)}" target="_blank" rel="noopener">↗</a>' if g.source_url else ""
    return f'''<div class="tgame {'played' if played else ''}">
      <div class="tdate"><b>{g.start_at.strftime('%d.%m')}</b><span>{g.start_at.strftime('%H:%M')}</span></div>
      <div class="tpair"><div>{html.escape(g.home_team)}</div><div>{html.escape(g.away_team)}</div></div>
      <div class="tscore"><b class="score-sensitive">{score}</b><span>{decision.strip()} {url}</span></div>
    </div>'''


def _render_standings(table: dict, target: str) -> str:
    if not table.get("rows"):
        return f'''<div class="notice">Таблица сейчас не загрузилась. <a href="{html.escape(table.get('source') or '#')}" target="_blank" rel="noopener">Открыть источник ↗</a></div>'''
    headers = table.get("headers") or []
    head = "".join(f"<th>{html.escape(str(x))}</th>" for x in headers)
    body = []
    for row in table["rows"]:
        text = " ".join(row)
        cls = " me" if target in text else ""
        body.append("<tr class=\"%s\">%s</tr>" % (cls.strip(), "".join(f"<td>{html.escape(str(x))}</td>" for x in row)))
    return f'''<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>
    <div class="table-source"><a href="{html.escape(table.get('source') or '#')}" target="_blank" rel="noopener">Источник таблицы ↗</a></div>'''


def render_team_page(team_key: str) -> str:
    meta = TEAM_META.get(team_key)
    if not meta:
        raise HTTPException(status_code=404, detail="Команда не найдена")
    name = meta["name"]
    now = datetime.now(core.MOSCOW)
    games = _team_games(name)
    next_games = [g for g in games if g.start_at >= now - timedelta(hours=3) and g.status != "finished"][:6]
    last_games = [g for g in games if g.status == "finished" and g.start_at < now]
    last_games = list(reversed(last_games[-6:]))
    table = _fetch_standings(team_key)

    next_html = "".join(_game_row(g) for g in next_games) or '<div class="notice">Ближайших матчей пока нет.</div>'
    last_html = "".join(_game_row(g) for g in last_games) or '<div class="notice">Результатов пока нет.</div>'
    standings_html = _render_standings(table, name)

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} · Мой хоккей</title><meta name="theme-color" content="#0b0d11">
<script>try{{if(localStorage.getItem('hockeyHubNoSpoilers')==='1')document.documentElement.classList.add('spoiler-mode')}}catch(e){{}}</script>
<style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}a{{color:inherit}}.wrap{{max-width:980px;margin:auto;padding:28px 20px 80px}}.back{{color:#96a0b0;text-decoration:none;font-size:13px}}.head{{margin:16px 0 28px;padding-bottom:22px;border-bottom:1px solid #262b35}}.eyebrow{{font-size:12px;color:#8993a4;letter-spacing:.12em}}h1{{font-size:42px;margin:6px 0 4px;line-height:1}}.league{{color:#a8b0bd}}h2{{font-size:15px;text-transform:uppercase;letter-spacing:.07em;color:#a7afbc;margin:30px 0 10px}}.panel{{background:#12161d;border:1px solid #252a33;border-radius:15px;overflow:hidden}}.tgame{{display:grid;grid-template-columns:78px minmax(0,1fr) 80px;gap:12px;align-items:center;min-height:72px;padding:10px 14px;border-bottom:1px solid #252a33}}.tgame:last-child{{border-bottom:0}}.tdate b,.tdate span{{display:block}}.tdate b{{font-size:16px}}.tdate span{{font-size:11px;color:#7f8999;margin-top:3px}}.tpair{{display:grid;gap:4px;font-size:16px}}.tscore{{text-align:right}}.tscore b{{font-size:18px}}.tscore span{{display:block;color:#7f8999;font-size:10px;margin-top:4px}}.src{{text-decoration:none;color:#9ba5b4}}.notice{{padding:18px;color:#8993a4}}.table-scroll{{overflow-x:auto;border:1px solid #252a33;border-radius:15px;background:#12161d}}table{{width:100%;border-collapse:collapse;min-width:620px}}th,td{{padding:10px 11px;border-bottom:1px solid #252a33;text-align:center;font-size:12px;white-space:nowrap}}th{{color:#8993a4;font-weight:600}}td:nth-child(2),th:nth-child(2){{text-align:left}}tr.me{{background:#202632}}tr.me td{{font-weight:750;color:#fff}}.table-source{{margin-top:7px;text-align:right;color:#798392;font-size:11px}}.table-source a{{text-decoration:none}}.spoiler-mode .tgame.played:not(.revealed) .score-sensitive{{font-size:0}}.spoiler-mode .tgame.played:not(.revealed) .score-sensitive:after{{content:'показать';font-size:10px;color:#9aa5b5;font-weight:600;cursor:pointer}}@media(max-width:600px){{.wrap{{padding:20px 14px 60px}}h1{{font-size:36px}}.tgame{{grid-template-columns:64px minmax(0,1fr) 66px;gap:8px;padding:9px 11px}}}}
</style></head><body><main class="wrap"><a class="back" href="/">← Все матчи</a><header class="head"><div class="eyebrow">{html.escape(meta['league'])} · КАРТОЧКА КОМАНДЫ</div><h1>{html.escape(name)}</h1><div class="league">Мой хоккей · v0.19</div></header>
<h2>Ближайшие матчи</h2><div class="panel">{next_html}</div>
<h2>Последние результаты</h2><div class="panel">{last_html}</div>
<h2>{html.escape(table.get('title') or 'Турнирная таблица')}</h2>{standings_html}
</main><script>document.querySelectorAll('.tgame.played').forEach(el=>el.addEventListener('click',()=>el.classList.add('revealed')));</script></body></html>'''


core.fetch_khl = fetch_khl_v19
core.fetch_spbhl = spb.fetch_spbhl_v13
core.app.version = "0.19.0"


def render_page_v19() -> str:
    page = ui.render_page_v10()
    page = re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.19", page, count=1)
    page = page.replace("</style>", ".team-page-link{margin-left:7px;color:#8c97a7;text-decoration:none;font-size:15px;line-height:1}.team-page-link:hover{color:#fff}\n</style>", 1)
    for team in core.TEAMS:
        needle = f"<b>{html.escape(team.name)}</b>"
        replacement = needle + f'<a class="team-page-link" href="/team/{team.key}" title="Открыть карточку команды" onclick="event.stopPropagation()">›</a>'
        page = page.replace(needle, replacement, 1)
    return page


core.render_page = render_page_v19


@core.app.get("/team/{team_key}", response_class=HTMLResponse)
def team_page(team_key: str):
    return render_team_page(team_key)


app = core.app
