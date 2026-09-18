from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import html

import personal_v56
import app_v05 as core
import app_v19 as feature
import app_v32 as standings_logic
import home_v44
from design_system_v46 import COMMON_CSS, topbar
from playoff_monitor import build_snapshot


VERSION = "0.57.2"
personal_v56.VERSION = VERSION


TRACKED = [
    ("ska", "СКА", "КХЛ"),
    ("ska_vmf", "СКА-ВМФ", "ВХЛ"),
    ("ska_1946", "СКА-1946", "МХЛ"),
    ("academy", "Академия СКА", "МХЛ"),
]


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _team_games(name: str):
    return feature._team_games(name)


def _finished(games):
    return sorted(
        [g for g in games if g.status == "finished" and g.home_score is not None and g.away_score is not None],
        key=lambda g: g.start_at,
        reverse=True,
    )


def _next_game(games, now: datetime):
    live = [g for g in games if g.status == "live"]
    if live:
        return sorted(live, key=lambda g: g.start_at)[0]
    future = [g for g in games if g.status != "finished" and g.start_at >= now]
    return sorted(future, key=lambda g: g.start_at)[0] if future else None


def _opponent(game, team_name: str) -> str:
    return game.away_team if game.home_team == team_name else game.home_team


def _result(game, team_name: str) -> str:
    if game.home_score is None or game.away_score is None:
        return "?"
    if game.home_score == game.away_score:
        return "Н"
    won = (
        (game.home_team == team_name and game.home_score > game.away_score)
        or (game.away_team == team_name and game.away_score > game.home_score)
    )
    return "В" if won else "П"


def _form_html(games, team_name: str, limit: int = 5) -> str:
    rows = _finished(games)[:limit]
    if not rows:
        return '<span class="form-empty">—</span>'
    bits = []
    for g in reversed(rows):
        result = _result(g, team_name)
        cls = "win" if result == "В" else "draw" if result == "Н" else "loss"
        bits.append(f'<span class="form-chip {cls}" title="{g.start_at:%d.%m}">{result}</span>')
    return "".join(bits)


def _score(game) -> str:
    if game.home_score is None or game.away_score is None:
        return "—:—"
    suffix = " Б" if game.decision == "SO" else " ОТ" if game.decision == "OT" else ""
    return f"{game.home_score}:{game.away_score}{suffix}"


def _game_source(game) -> str:
    if not game or not game.source_url:
        return ""
    return f'<a href="{_esc(game.source_url)}" target="_blank" rel="noopener">источник ↗</a>'


def _next_card(game, team_name: str) -> str:
    if game is None:
        return '''<article class="next-card empty-next">
          <span>БЛИЖАЙШИЙ МАТЧ</span><h3>Пока не загружен</h3>
          <p>Следующий матч появится после обновления источника.</p>
        </article>'''
    live = game.status == "live"
    when = "LIVE" if live else game.start_at.strftime("%d.%m · %H:%M")
    where = _esc(game.arena) if game.arena else "арена не указана"
    opponent = _opponent(game, team_name)
    side = "дома" if game.home_team == team_name else "в гостях"
    return f'''<article class="next-card{" live" if live else ""}">
      <div class="next-top"><span>БЛИЖАЙШИЙ МАТЧ</span><b>{when}</b></div>
      <h3>{_esc(opponent)}</h3>
      <p>{side} · {where}</p>
      {f'<strong class="score-value">{_score(game)}</strong>' if live else ''}
      {_game_source(game)}
    </article>'''


def _recent_rows(games, team_name: str, limit: int = 5) -> str:
    rows = []
    for g in _finished(games)[:limit]:
        result = _result(g, team_name)
        cls = "win" if result == "В" else "draw" if result == "Н" else "loss"
        rows.append(f'''<div class="recent-row">
          <time>{g.start_at:%d.%m}</time>
          <span class="result-badge {cls}">{result}</span>
          <div><b>{_esc(g.home_team)} — {_esc(g.away_team)}</b>{f'<em>{_esc(g.arena)}</em>' if g.arena else ''}</div>
          <strong class="score-value">{_score(g)}</strong>
          {_game_source(g)}
        </div>''')
    return "".join(rows) if rows else '<div class="empty-block">Завершённых матчей пока нет.</div>'


def _standings_columns(table: dict) -> list[int]:
    headers = list(table.get("headers") or [])
    if not headers:
        return []
    norm = [standings_logic._norm(x) for x in headers]
    team_idx = standings_logic._team_index(headers)
    indices = [0, team_idx]

    def first(candidates):
        for i, value in enumerate(norm):
            if value in candidates:
                return i
        return None

    games_idx = first({"и", "иг", "игры", "игр", "gp"})
    points_idx = first({"о", "очки", "очк", "pts"})
    goals_idx = first({"ш", "шайбы", "голы", "гз:гп"})

    for idx in (games_idx, goals_idx, points_idx):
        if idx is not None and idx not in indices:
            indices.append(idx)
    if len(indices) < 3 and len(headers) > 2:
        candidate = len(headers) - 1
        if candidate not in indices:
            indices.append(candidate)
    return indices[:5]


def _compact_standings(table: dict, team_name: str) -> str:
    rows = list(table.get("rows") or [])
    headers = list(table.get("headers") or [])
    if not rows:
        source = table.get("source")
        return f'''<div class="empty-block">Таблица сейчас не загрузилась.
          {f'<a href="{_esc(source)}" target="_blank" rel="noopener">Открыть источник ↗</a>' if source else ''}
        </div>'''

    pos = standings_logic._position(table, team_name)
    if pos:
        start = max(0, pos - 3)
        end = min(len(rows), start + 5)
        start = max(0, end - 5)
        window = rows[start:end]
        positions = range(start + 1, end + 1)
    else:
        window = rows[:5]
        positions = range(1, len(window) + 1)

    cols = _standings_columns(table)
    team_idx = standings_logic._team_index(headers)
    zones = table.get("zones") or {}

    if cols:
        head = "".join(f"<th>{_esc(headers[i])}</th>" for i in cols)
    else:
        head = "<th>М</th><th>Команда</th>"

    body = []
    for actual_pos, row in zip(positions, window):
        is_me = team_idx < len(row) and standings_logic._norm(row[team_idx]) == standings_logic._norm(team_name)
        zone = zones.get(actual_pos)
        classes = ["me"] if is_me else []
        if zone:
            classes.append(f"zone-{zone}")
        if cols:
            cells = "".join(f"<td>{_esc(row[i] if i < len(row) else '')}</td>" for i in cols)
        else:
            team = row[team_idx] if team_idx < len(row) else ""
            cells = f"<td>{actual_pos}</td><td>{_esc(team)}</td>"
        body.append(f'<tr class="{" ".join(classes)}">{cells}</tr>')

    source = table.get("source") or ""
    title = table.get("title") or "Турнирная таблица"
    return f'''<div class="standings-title"><b>{_esc(title)}</b><span>рядом с нашей позицией</span></div>
      <div class="mini-table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>
      {f'<a class="source-link" href="{_esc(source)}" target="_blank" rel="noopener">источник таблицы ↗</a>' if source else ''}'''


def _stage_class(snapshot) -> str:
    value = str(getattr(snapshot.stage_kind, "value", snapshot.stage_kind))
    if "playoff" in value:
        return "playoff"
    if "play_in" in value:
        return "playin"
    return "regular"


def _load_table(team_key: str) -> dict:
    try:
        return feature._fetch_standings(team_key)
    except Exception as exc:
        meta = feature.TEAM_META[team_key]
        return {
            "title": "Турнирная таблица",
            "headers": [],
            "rows": [],
            "source": meta.get("table_url"),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _contexts():
    now = datetime.now(core.MOSCOW)
    games_by_key = {key: _team_games(name) for key, name, _league in TRACKED}
    tables: dict[str, dict] = {}

    # First uncached visit should not wait for four sources sequentially.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_load_table, key): key for key, _name, _league in TRACKED}
        for future in as_completed(futures):
            key = futures[future]
            try:
                tables[key] = future.result()
            except Exception as exc:
                tables[key] = {"headers": [], "rows": [], "error": str(exc)}

    out = []
    for key, name, league in TRACKED:
        games = games_by_key[key]
        table = tables.get(key) or {}
        snapshot = build_snapshot(key, name, league, table, games, now)
        out.append({
            "key": key,
            "name": name,
            "league": league,
            "games": games,
            "table": table,
            "snapshot": snapshot,
            "next": _next_game(games, now),
            "finished": _finished(games),
        })
    return out, now


def _overview_tile(ctx: dict, active: bool = False) -> str:
    snap = ctx["snapshot"]
    game = ctx["next"]
    position = f"{snap.position}-е место" if snap.position else "место не определено"
    next_text = "нет ближайшего матча"
    if game:
        next_text = ("LIVE · " if game.status == "live" else f"{game.start_at:%d.%m · %H:%M} · ") + _opponent(game, ctx["name"])
    return f'''<button class="system-team{" active" if active else ""}" type="button" data-team="{ctx["key"]}">
      <div class="system-team-top"><span>{ctx["league"]}</span><em>{_esc(snap.stage_name)}</em></div>
      <h2>{_esc(ctx["name"])}</h2>
      <div class="position">{_esc(position)}</div>
      <div class="team-form">{_form_html(ctx["games"], ctx["name"])}</div>
      <div class="team-next">{_esc(next_text)}</div>
    </button>'''


def _detail_panel(ctx: dict, active: bool = False) -> str:
    snap = ctx["snapshot"]
    stage_cls = _stage_class(snap)
    series_html = ""
    if snap.series:
        series_html = f'''<div class="series-line"><span>СЕРИЯ</span><b>{_esc(snap.series.team_a)} — {_esc(snap.series.team_b)}</b><strong class="score-value">{_esc(snap.series.score_text)}</strong></div>'''
    return f'''<section class="team-detail{" active" if active else ""}" data-panel="{ctx["key"]}">
      <header class="team-detail-head">
        <div><div class="team-league">{ctx["league"]} · СКА-СИСТЕМА</div><h2>{_esc(ctx["name"])}</h2></div>
        <div class="stage-block"><span class="stage-pill {stage_cls}">{_esc(snap.stage_name)}</span><a href="/team/{ctx["key"]}">полная карточка команды →</a></div>
      </header>
      <div class="qualification">{_esc(snap.summary or "Положение определяется по текущей таблице.")}</div>
      {series_html}
      <div class="detail-grid">
        <div class="detail-main">
          {_next_card(ctx["next"], ctx["name"])}
          <article class="big-card recent-card"><div class="card-head"><h3>Последние матчи</h3><span>форма {_form_html(ctx["games"],ctx["name"])}</span></div>{_recent_rows(ctx["games"],ctx["name"])}</article>
        </div>
        <aside class="detail-side">
          <article class="big-card standing-card"><div class="card-head"><h3>Турнирное положение</h3><span>{f"{snap.position}-е место" if snap.position else "—"}</span></div>{_compact_standings(ctx["table"],ctx["name"])}</article>
          <article class="big-card season-card"><div class="card-head"><h3>Сезон</h3><span>2026/27</span></div><dl><div><dt>Этап</dt><dd>{_esc(snap.stage_name)}</dd></div><div><dt>Лига</dt><dd>{ctx["league"]}</dd></div><div><dt>Матчей в ленте</dt><dd>{len(ctx["games"])}</dd></div></dl></article>
        </aside>
      </div>
    </section>'''


def render_big_hockey_v57() -> str:
    contexts, now = _contexts()
    tiles = "".join(_overview_tile(ctx, i == 0) for i, ctx in enumerate(contexts))
    panels = "".join(_detail_panel(ctx, i == 0) for i, ctx in enumerate(contexts))

    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Большой хоккей · Hockey Hub</title><meta name="theme-color" content="#07090c"><style>
{COMMON_CSS}
:root{{--big-red:#ef3654;--big-blue:#416cff;--big-panel:#0d141d}}
body{{background:radial-gradient(circle at 18% 0%,rgba(239,54,84,.075),transparent 28%),radial-gradient(circle at 82% 0%,rgba(65,108,255,.10),transparent 30%),#07090c}}
.hub-topbar{{grid-template-columns:auto 1fr auto}}.spoiler-btn{{border:1px solid #2b3747;background:#101721;color:#dbe2eb;border-radius:10px;padding:9px 11px;font-size:11px;cursor:pointer}}.spoiler-btn.on{{border-color:#586c87;color:#fff}}
.big-hero{{display:grid;grid-template-columns:1fr auto;gap:26px;align-items:end;padding:38px 0 26px;border-bottom:1px solid var(--hub-line-soft)}}.big-hero .hub-eyebrow{{color:#e8556c}}.big-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.big-hero p{{margin:0;color:#929dad;font-size:15px;max-width:760px}}.big-hero-side{{text-align:right;color:#68788d;font-size:9px;letter-spacing:.11em;text-transform:uppercase}}.big-hero-side b{{display:block;color:#d5dce5;font-size:12px;margin-bottom:5px}}
.big-tabs{{display:flex;gap:8px;padding:18px 0;overflow:auto}}.big-tabs span{{padding:9px 13px;background:#0d141d;border:1px solid #273548;border-radius:10px;color:#77869a;font-size:11px;white-space:nowrap}}.big-tabs .active{{background:linear-gradient(90deg,#b81f3a,#355fe3);border-color:transparent;color:#fff}}.big-tabs .soon{{opacity:.55}}
.system-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}}.system-team{{text-align:left;min-height:184px;padding:15px;border:1px solid #293749;border-radius:15px;background:linear-gradient(180deg,#101721,#0b1119);color:inherit;cursor:pointer;position:relative;overflow:hidden}}.system-team:before{{content:"";position:absolute;inset:0 auto 0 0;width:2px;background:linear-gradient(var(--big-red),var(--big-blue));opacity:.32}}.system-team:hover,.system-team.active{{border-color:#43556d;background:linear-gradient(180deg,#131c29,#0c121b)}}.system-team.active:before{{opacity:1;width:3px}}.system-team-top{{display:flex;justify-content:space-between;gap:8px;color:#708095;font-size:8px;text-transform:uppercase}}.system-team-top em{{font-style:normal;color:#8d9bad;max-width:60%;text-align:right}}.system-team h2{{font-size:17px;margin:10px 0 5px}}.position{{color:#c4ced9;font-size:10px}}.team-form{{display:flex;gap:4px;margin:14px 0 11px}}.form-chip{{display:grid;place-items:center;width:23px;height:23px;border-radius:7px;font-size:7px;font-weight:800;border:1px solid #2d3743}}.form-chip.win{{color:#8fc7a4;border-color:#315342;background:#0c1712}}.form-chip.loss{{color:#d4939c;border-color:#56353b;background:#171013}}.form-chip.draw{{color:#cbb77c;border-color:#564c31}}.form-empty{{color:#657589}}.team-next{{color:#738398;font-size:9px;line-height:1.4}}
.team-detail{{display:none}}.team-detail.active{{display:block}}.team-detail-head{{display:flex;justify-content:space-between;gap:18px;align-items:end;padding:19px 20px;background:linear-gradient(130deg,rgba(239,54,84,.05),transparent 35%),linear-gradient(230deg,rgba(65,108,255,.07),transparent 38%),#0d131b;border:1px solid #293647;border-radius:17px 17px 0 0}}.team-league{{font-size:8px;color:#6d7d91;letter-spacing:.1em}}.team-detail-head h2{{font-size:28px;margin:5px 0 0}}.stage-block{{display:flex;align-items:center;gap:12px}}.stage-block a{{color:#78889d;font-size:9px;text-decoration:none}}.stage-pill{{padding:6px 9px;border-radius:999px;border:1px solid #384759;color:#b6c3d0;font-size:8px}}.stage-pill.playoff{{border-color:#8d3143;color:#f08a9a}}.stage-pill.playin{{border-color:#806936;color:#d6bd7d}}.qualification{{padding:11px 20px;border-left:1px solid #293647;border-right:1px solid #293647;background:#0b1118;color:#9ba9b9;font-size:10px;line-height:1.5}}.series-line{{display:grid;grid-template-columns:60px 1fr auto;gap:10px;padding:11px 20px;border:1px solid #60313d;background:#160e13;align-items:center}}.series-line span{{font-size:8px;color:#c46a79}}.series-line b{{font-size:11px}}.series-line strong{{font-size:17px}}
.detail-grid{{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(310px,.65fr);gap:14px;margin-top:14px}}.detail-main,.detail-side{{display:grid;gap:14px;align-content:start}}.big-card,.next-card{{border:1px solid #283646;border-radius:15px;background:linear-gradient(180deg,#101721,#0b1118)}}.next-card{{min-height:190px;padding:18px;position:relative;background:radial-gradient(circle at 90% 20%,rgba(65,108,255,.13),transparent 38%),linear-gradient(145deg,#111925,#0b1119)}}.next-card.live{{border-color:#b5354b}}.next-top{{display:flex;justify-content:space-between;color:#718197;font-size:8px}}.next-top b{{color:#eb536b;letter-spacing:.08em}}.next-card h3{{font-size:25px;margin:29px 0 7px}}.next-card p{{color:#77869a;font-size:10px;margin:0}}.next-card>strong{{position:absolute;right:18px;bottom:45px;font-size:22px}}.next-card>a{{position:absolute;right:18px;bottom:17px;color:#7d8da2;font-size:8px;text-decoration:none}}.empty-next h3{{color:#8b97a7}}
.card-head{{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:15px 16px 11px}}.card-head h3{{margin:0;font-size:13px}}.card-head>span{{color:#718096;font-size:8px;display:flex;gap:4px;align-items:center}}.recent-card{{padding-bottom:5px}}.recent-row{{display:grid;grid-template-columns:42px 28px 1fr auto 54px;gap:9px;align-items:center;margin:0 15px;border-top:1px solid #202c39;padding:10px 0}}.recent-row time{{color:#65758a;font-size:8px}}.result-badge{{display:grid;place-items:center;width:25px;height:23px;border-radius:6px;border:1px solid #34404d;font-size:7px}}.result-badge.win{{color:#8fc7a4;border-color:#315342}}.result-badge.loss{{color:#d4939c;border-color:#56353b}}.recent-row b{{display:block;font-size:10px}}.recent-row em{{display:block;color:#637185;font-size:7px;font-style:normal;margin-top:3px}}.recent-row>strong{{font-size:11px}}.recent-row>a{{color:#68788b;text-decoration:none;font-size:7px;text-align:right}}
.standing-card{{padding-bottom:14px}}.standings-title{{display:flex;justify-content:space-between;gap:10px;padding:0 15px 9px;color:#738398;font-size:8px}}.standings-title b{{color:#aeb9c6;font-size:9px}}.mini-table-wrap{{overflow:auto;margin:0 14px;border:1px solid #222e3b;border-radius:10px}}.mini-table-wrap table{{width:100%;border-collapse:collapse;min-width:350px}}.mini-table-wrap th,.mini-table-wrap td{{padding:8px 7px;border-bottom:1px solid #202b37;text-align:center;font-size:8px;white-space:nowrap}}.mini-table-wrap th{{color:#68788c;font-weight:600}}.mini-table-wrap th:nth-child(2),.mini-table-wrap td:nth-child(2){{text-align:left}}.mini-table-wrap tr.me{{background:#172334;box-shadow:inset 2px 0 #5c8ac5}}.mini-table-wrap tr.zone-direct:not(.me){{background:rgba(67,132,83,.04)}}.mini-table-wrap tr.zone-playin:not(.me){{background:rgba(170,132,52,.05)}}.source-link{{display:block;text-align:right;margin:8px 15px 0;color:#647489;font-size:7px;text-decoration:none}}.empty-block{{padding:16px;color:#718095;font-size:9px}}.empty-block a{{display:block;margin-top:7px}}
.season-card{{padding-bottom:14px}}.season-card dl{{margin:0 15px}}.season-card dl>div{{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-top:1px solid #202b37}}.season-card dt{{color:#68778a;font-size:8px}}.season-card dd{{margin:0;color:#bec7d2;font-size:9px;text-align:right}}
.big-footer{{display:flex;justify-content:space-between;margin-top:22px;padding-top:15px;border-top:1px solid #1f2935;color:#58677b;font-size:8px;text-transform:uppercase;letter-spacing:.06em}}
body.hide-scores .score-value{{filter:none!important;position:relative;display:inline-block;width:3.4em;overflow:hidden;white-space:nowrap;color:transparent!important;text-shadow:none!important;user-select:none}}
body.hide-scores .score-value:after{{content:"—:—";position:absolute;inset:0;color:#cbd3dd;text-align:center}}
@media(max-width:920px){{.system-grid{{grid-template-columns:1fr 1fr}}.detail-grid{{grid-template-columns:1fr}}}}
@media(max-width:760px){{.hub-topbar{{grid-template-columns:auto auto}}.hub-nav{{grid-column:1/-1;order:3}}.spoiler-btn{{justify-self:end}}.big-hero{{grid-template-columns:1fr}}.big-hero-side{{text-align:left}}.team-detail-head{{align-items:flex-start;flex-direction:column}}}}
@media(max-width:560px){{.system-grid{{grid-template-columns:1fr}}.recent-row{{grid-template-columns:38px 26px 1fr auto}}.recent-row>a{{display:none}}.stage-block{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><main class="hub-shell">
{topbar("big").replace("</header>", '<button class="spoiler-btn" id="spoilerToggle" type="button">◉ Не спойлерить</button></header>')}
<section class="big-hero"><div><div class="hub-eyebrow">ВНЕШНИЙ ХОККЕЙНЫЙ МИР</div><h1>Большой хоккей</h1><p>СКА-система целиком: четыре команды, три лиги, один текущий контекст.</p></div><div class="big-hero-side"><b>СКА / ВМФ / 1946 / АКАДЕМИЯ</b>матчи · таблицы · форма · постсезон</div></section>
<div class="big-tabs"><span class="active">СКА-система</span><span class="soon">НХЛ · следующий этап</span><span class="soon">Международный</span><span class="soon">Новости</span><span class="soon">История</span></div>
<section class="system-grid">{tiles}</section>
{panels}
<footer class="big-footer"><span>Hockey Hub · Большой хоккей</span><span>v{VERSION}</span></footer>
</main><script>
const buttons=[...document.querySelectorAll('[data-team]')];
const panels=[...document.querySelectorAll('[data-panel]')];
buttons.forEach(btn=>btn.addEventListener('click',()=>{{
  const key=btn.dataset.team;
  buttons.forEach(x=>x.classList.toggle('active',x===btn));
  panels.forEach(x=>x.classList.toggle('active',x.dataset.panel===key));
}}));
const spoiler=document.getElementById('spoilerToggle');
const spoilerKey='hockeyHubSpoilersHidden';
function applySpoiler(){{
  let hidden=false;try{{hidden=localStorage.getItem(spoilerKey)==='1'}}catch(e){{}}
  document.body.classList.toggle('hide-scores',hidden);
  spoiler.classList.toggle('on',hidden);
  spoiler.textContent=hidden?'◉ Показать счёт':'◉ Не спойлерить';
}}
spoiler.addEventListener('click',()=>{{
  const hidden=!document.body.classList.contains('hide-scores');
  document.body.classList.toggle('hide-scores',hidden);
  spoiler.classList.toggle('on',hidden);
  spoiler.textContent=hidden?'◉ Показать счёт':'◉ Не спойлерить';
  try{{localStorage.setItem(spoilerKey,hidden?'1':'0')}}catch(e){{}}
}});
applySpoiler();
</script></body></html>'''
    return page


# The existing /big-hockey route resolves this module global dynamically.
home_v44.render_big_hockey_v44 = render_big_hockey_v57
core.app.version = "0.57.2"
app = core.app


def _startup_smoke_v57() -> None:
    page = render_big_hockey_v57()
    required = ("СКА", "СКА-ВМФ", "СКА-1946", "Академия СКА", "Турнирное положение")
    missing = [label for label in required if label not in page]
    if missing:
        raise RuntimeError(f"v0.57 big hockey smoke missing: {missing}")
    if "<html" not in page.lower():
        raise RuntimeError("v0.57 big hockey smoke: invalid html")
    print(f"[v57-smoke] big-hockey: OK chars={len(page)}", flush=True)


_startup_smoke_v57()
