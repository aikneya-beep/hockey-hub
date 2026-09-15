from __future__ import annotations

from datetime import datetime, timedelta
import html
import re

import app_v21 as prev
import app_v19 as feature
import app_v05 as core

core.app.version = "0.22.0"


def _norm(value: str) -> str:
    return core.compact(str(value)).casefold().replace("–", "-").replace("—", "-")


def _compact_table(table: dict, team_key: str) -> dict:
    """Keep the useful standings columns; hide SPbHL head-to-head matrix columns."""
    headers = list(table.get("headers") or [])
    rows = [list(r) for r in table.get("rows") or []]
    if team_key == "eskulap" and headers:
        keep = [i for i, h in enumerate(headers) if not re.fullmatch(r"\d+", core.compact(str(h)))]
        if keep and len(keep) < len(headers):
            headers = [headers[i] for i in keep]
            rows = [[row[i] if i < len(row) else "" for i in keep] for row in rows]
        headers = ["Команда" if core.compact(str(h)) == "Команды" else h for h in headers]
    return {**table, "headers": headers, "rows": rows}


def _render_standings_exact(table: dict, target: str) -> str:
    if not table.get("rows"):
        return (
            '<div class="notice">Таблица сейчас не загрузилась. '
            f'<a href="{html.escape(table.get("source") or "#")}" target="_blank" rel="noopener">Открыть источник ↗</a></div>'
        )

    headers = list(table.get("headers") or [])
    rows = list(table.get("rows") or [])
    head = "".join(f"<th>{html.escape(str(x))}</th>" for x in headers)

    team_idx = 1 if len(headers) > 1 else 0
    for i, h in enumerate(headers):
        if _norm(h) in {"команда", "команды", "клуб"}:
            team_idx = i
            break

    body = []
    for row in rows:
        team_cell = row[team_idx] if team_idx < len(row) else ""
        cls = "me" if _norm(team_cell) == _norm(target) else ""
        cells = "".join(f"<td>{html.escape(str(x))}</td>" for x in row)
        body.append(f'<tr class="{cls}">{cells}</tr>')

    source = html.escape(table.get("source") or "#")
    return (
        f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
        f'<div class="table-source"><a href="{source}" target="_blank" rel="noopener">Источник таблицы ↗</a></div>'
    )


def _team_game_row(g: core.Game, target: str, played: bool) -> str:
    score = "—"
    if played and g.home_score is not None and g.away_score is not None:
        score = f"{g.home_score}:{g.away_score}"
    decision = "Б" if g.decision == "SO" else "ОТ" if g.decision == "OT" else ""
    source = (
        f'<a class="src" href="{html.escape(g.source_url)}" target="_blank" rel="noopener" title="Источник">↗</a>'
        if g.source_url else ""
    )

    def tn(name: str) -> str:
        cls = " fav" if _norm(name) == _norm(target) else ""
        return f'<div class="team-name{cls}">{html.escape(name)}</div>'

    reveal = (
        '<button type="button" class="score-mask" onclick="revealTeamScore(this);event.stopPropagation()">показать<br>счёт</button>'
        if played else ""
    )
    return f'''<div class="tgame {'played' if played else ''}">
      <div class="tdate"><b>{g.start_at.strftime('%d.%m')}</b><span>{g.start_at.strftime('%H:%M')}</span></div>
      <div class="tpair">{tn(g.home_team)}{tn(g.away_team)}</div>
      <div class="tscore"><b class="score-sensitive">{score}</b>{reveal}<span>{html.escape(decision)} {source}</span></div>
    </div>'''


def render_team_page_v22(team_key: str) -> str:
    meta = feature.TEAM_META.get(team_key)
    if not meta:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Команда не найдена")

    name = meta["name"]
    now = datetime.now(core.MOSCOW)
    games = feature._team_games(name)

    # The SKA team page is about the current KHL regular season. Do not let old
    # pre-season records left in GAMES leak back into the results block.
    if team_key == "ska":
        games = [g for g in games if g.start_at >= feature.REGULAR_START]

    upcoming = sorted(
        [g for g in games if g.status != "finished" and g.start_at >= now - timedelta(hours=4)],
        key=lambda g: g.start_at,
    )[:6]
    results = sorted(
        [g for g in games if g.status == "finished" and g.start_at <= now],
        key=lambda g: g.start_at,
        reverse=True,
    )[:6]

    table = _compact_table(feature._fetch_standings(team_key), team_key)
    standings_html = _render_standings_exact(table, name)
    next_html = "".join(_team_game_row(g, name, False) for g in upcoming) or '<div class="notice">Ближайших матчей пока нет.</div>'
    last_html = "".join(_team_game_row(g, name, True) for g in results) or '<div class="notice">Результатов пока нет.</div>'
    title = html.escape(table.get("title") or "Турнирная таблица")

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} · Мой хоккей</title><meta name="theme-color" content="#0b0d11">
<script>try{{if(localStorage.getItem('hockeyHubNoSpoilers')==='1')document.documentElement.classList.add('spoiler-mode')}}catch(e){{}}</script>
<style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}a{{color:inherit}}button{{font:inherit}}.wrap{{max-width:980px;margin:auto;padding:24px 20px 80px}}
.topbar{{display:flex;justify-content:space-between;align-items:center;gap:14px}}.back{{color:#96a0b0;text-decoration:none;font-size:13px}}.spoiler-toggle{{background:#151922;color:#b3bdcb;border:1px solid #2b3340;border-radius:11px;padding:9px 13px;font-weight:700;cursor:pointer}}.spoiler-toggle.active{{color:#f5f7fa;border-color:#697588;background:#1b202a}}.spoiler-dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#596273;margin-right:7px;vertical-align:1px}}.spoiler-toggle.active .spoiler-dot{{background:#8bd49c}}
.head{{margin:16px 0 20px;padding-bottom:20px;border-bottom:1px solid #262b35}}.eyebrow{{font-size:12px;color:#8993a4;letter-spacing:.12em}}h1{{font-size:42px;margin:6px 0 4px;line-height:1}}.league{{color:#a8b0bd}}h2{{font-size:15px;text-transform:uppercase;letter-spacing:.07em;color:#a7afbc;margin:28px 0 10px}}
.panel{{background:#12161d;border:1px solid #252a33;border-radius:15px;overflow:hidden}}.tgame{{display:grid;grid-template-columns:78px minmax(0,1fr) 90px;gap:12px;align-items:center;min-height:72px;padding:10px 14px;border-bottom:1px solid #252a33}}.tgame:last-child{{border-bottom:0}}.tdate b,.tdate span{{display:block}}.tdate b{{font-size:16px}}.tdate span{{font-size:11px;color:#7f8999;margin-top:3px}}.tpair{{display:grid;gap:4px;font-size:16px}}.team-name.fav{{font-weight:800;color:#fff}}.tscore{{text-align:right}}.tscore b{{font-size:18px}}.tscore span{{display:block;color:#7f8999;font-size:10px;margin-top:4px}}.src{{text-decoration:none;color:#9ba5b4}}.notice{{padding:18px;color:#8993a4}}
.table-scroll{{overflow-x:auto;border:1px solid #252a33;border-radius:15px;background:#12161d}}table{{width:100%;border-collapse:collapse;min-width:620px}}th,td{{padding:10px 11px;border-bottom:1px solid #252a33;text-align:center;font-size:12px;white-space:nowrap}}th{{color:#8993a4;font-weight:600}}td:nth-child(2),th:nth-child(2){{text-align:left}}tr.me{{background:#202632}}tr.me td{{font-weight:800;color:#fff}}.table-source{{margin-top:7px;text-align:right;color:#798392;font-size:11px}}.table-source a{{text-decoration:none}}
.score-mask{{display:none;background:transparent;color:#9aa5b5;border:0;padding:0;font-size:10px;line-height:1.15;text-align:right;cursor:pointer;font-weight:650}}.spoiler-mode .tgame.played:not(.revealed) .score-sensitive{{display:none}}.spoiler-mode .tgame.played:not(.revealed) .score-mask{{display:inline-block}}
@media(max-width:600px){{.wrap{{padding:18px 14px 60px}}h1{{font-size:36px}}.topbar{{align-items:flex-start}}.spoiler-toggle{{font-size:12px;padding:8px 10px}}.tgame{{grid-template-columns:64px minmax(0,1fr) 72px;gap:8px;padding:9px 11px}}table{{min-width:560px}}}}
</style></head><body><main class="wrap">
<div class="topbar"><a class="back" href="/">← Все матчи</a><button type="button" id="spoilerToggle" class="spoiler-toggle"><span class="spoiler-dot"></span><span class="spoiler-label">Не спойлерить</span></button></div>
<header class="head"><div class="eyebrow">{html.escape(meta['league'])} · КАРТОЧКА КОМАНДЫ</div><h1>{html.escape(name)}</h1><div class="league">Мой хоккей · v0.22</div></header>
<h2>{title}</h2>{standings_html}
<h2>Ближайшие матчи</h2><div class="panel">{next_html}</div>
<h2>Последние результаты</h2><div class="panel">{last_html}</div>
</main><script>
(function(){{
 const key='hockeyHubNoSpoilers',root=document.documentElement,toggle=document.getElementById('spoilerToggle'),label=toggle.querySelector('.spoiler-label');
 function sync(){{const active=root.classList.contains('spoiler-mode');toggle.classList.toggle('active',active);toggle.setAttribute('aria-pressed',active?'true':'false');label.textContent=active?'Не спойлерить: вкл':'Не спойлерить';}}
 toggle.addEventListener('click',()=>{{root.classList.toggle('spoiler-mode');try{{localStorage.setItem(key,root.classList.contains('spoiler-mode')?'1':'0')}}catch(e){{}};document.querySelectorAll('.tgame.revealed').forEach(el=>el.classList.remove('revealed'));sync();}});
 window.revealTeamScore=function(button){{button.closest('.tgame').classList.add('revealed')}};
 document.querySelectorAll('.tgame.played').forEach(el=>el.addEventListener('click',()=>{{if(root.classList.contains('spoiler-mode'))el.classList.add('revealed')}}));
 sync();
}})();
</script></body></html>'''


feature.render_team_page = render_team_page_v22


def render_page_v22() -> str:
    return prev.render_page_v21().replace("v0.21", "v0.22", 1)


core.render_page = render_page_v22
app = core.app
