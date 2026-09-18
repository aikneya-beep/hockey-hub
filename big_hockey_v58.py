from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import html

from bs4 import BeautifulSoup

import big_hockey_v57 as ska
import nhl_source_v58 as nhl
import app_v05 as core
import home_v44


VERSION = "0.58"
MSK = ZoneInfo("Europe/Moscow")

TEAM_NAMES = {
    "ANA":"Anaheim","BOS":"Boston","BUF":"Buffalo","CAR":"Carolina","CBJ":"Columbus",
    "CGY":"Calgary","CHI":"Chicago","COL":"Colorado","DAL":"Dallas","DET":"Detroit",
    "EDM":"Edmonton","FLA":"Florida","LAK":"Los Angeles","MIN":"Minnesota","MTL":"Montreal",
    "NJD":"New Jersey","NSH":"Nashville","NYI":"NY Islanders","NYR":"NY Rangers","OTT":"Ottawa",
    "PHI":"Philadelphia","PIT":"Pittsburgh","SEA":"Seattle","SJS":"San Jose","STL":"St. Louis",
    "TBL":"Tampa Bay","TOR":"Toronto","UTA":"Utah","VAN":"Vancouver","VGK":"Vegas",
    "WPG":"Winnipeg","WSH":"Washington",
}


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _season_label(season_id: int | None) -> str:
    if not season_id:
        return "—"
    text = str(season_id)
    return f"{text[:4]}/{text[-2:]}"


def _name(value) -> str:
    if isinstance(value, dict):
        return value.get("default") or value.get("en") or next(iter(value.values()), "")
    return str(value or "")


def _game_start(game: dict) -> datetime | None:
    raw = game.get("startTimeUTC")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _game_team(game: dict, side: str) -> str:
    block = game.get(side) or {}
    return (block.get("abbrev") or "").upper()


def _game_score(game: dict, side: str):
    return (game.get(side) or {}).get("score")


def _game_venue(game: dict) -> str:
    return _name(game.get("venue"))


def _format_game(game: dict) -> dict:
    start = _game_start(game)
    local = start.astimezone(MSK) if start else None
    home = _game_team(game, "homeTeam")
    away = _game_team(game, "awayTeam")
    hs = _game_score(game, "homeTeam")
    aws = _game_score(game, "awayTeam")
    state = game.get("gameState") or ""
    return {
        "id": game.get("id") or f"{home}-{away}-{game.get('startTimeUTC')}",
        "home": home,
        "away": away,
        "home_name": TEAM_NAMES.get(home, home),
        "away_name": TEAM_NAMES.get(away, away),
        "start": local,
        "state": state,
        "score": f"{hs}:{aws}" if hs is not None and aws is not None else "",
        "venue": _game_venue(game),
    }


def _next_games(data: dict, limit: int = 6) -> list[dict]:
    seen = set()
    games = []
    for team, ctx in (data.get("teams") or {}).items():
        game = (ctx or {}).get("next")
        if not game:
            continue
        formatted = _format_game(game)
        if formatted["id"] in seen:
            continue
        seen.add(formatted["id"])
        games.append(formatted)
    games.sort(key=lambda x: x["start"] or datetime.max.replace(tzinfo=MSK))
    return games[:limit]


def _game_cards(data: dict) -> str:
    games = _next_games(data)
    if not games:
        return '<div class="nhl-empty">Ближайшие матчи пока не пришли из расписания NHL.</div>'

    cards = []
    for g in games:
        when = g["start"].strftime("%d.%m · %H:%M МСК") if g["start"] else "время уточняется"
        live = g["state"] in {"LIVE","CRIT"}
        cards.append(f'''<article class="nhl-game{" live" if live else ""}">
          <div class="nhl-game-top"><span>{when}</span>{'<b>LIVE</b>' if live else ''}</div>
          <h3>{_esc(g["away"])} <span>—</span> {_esc(g["home"])}</h3>
          <p>{_esc(g["away_name"])} · {_esc(g["home_name"])}</p>
          {f'<strong class="score-value">{_esc(g["score"])}</strong>' if g["score"] else ''}
          {f'<em>{_esc(g["venue"])}</em>' if g["venue"] else ''}
        </article>''')
    return "".join(cards)


def _stat_line(player: dict) -> str:
    if player.get("kind") == "goalie":
        save = player.get("save_pct")
        save_text = f"{float(save):.3f}" if isinstance(save, (int,float)) else "—"
        return f'{player.get("gp") or 0} И · {player.get("wins") or 0} В · SV% {save_text}'
    return f'{player.get("gp") or 0} И · {player.get("goals") or 0}+{player.get("assists") or 0} · {player.get("points") or 0} О'


def _next_for_player(player: dict, data: dict) -> str:
    team = player.get("team") or ""
    game = ((data.get("teams") or {}).get(team) or {}).get("next")
    if not game:
        return "ближайший матч пока не загружен"
    g = _format_game(game)
    opponent = g["away"] if g["home"] == team else g["home"]
    when = g["start"].strftime("%d.%m · %H:%M") if g["start"] else "время уточняется"
    return f"{when} · {opponent}"


def _player_card(player: dict, data: dict) -> str:
    team = player.get("team") or "—"
    pos = player.get("position") or ""
    return f'''<article class="nhl-player">
      <div class="nhl-player-top"><span>{_esc(team)} · {_esc(pos)}</span><em>{_esc(TEAM_NAMES.get(team, team))}</em></div>
      <h3>{_esc(player.get("name"))}</h3>
      <div class="nhl-player-stat">{_esc(_stat_line(player))}</div>
      <div class="nhl-player-next">{_esc(_next_for_player(player,data))}</div>
    </article>'''


def _leaders(data: dict) -> str:
    skaters = [p for p in data.get("players") or [] if p.get("kind") == "skater"]
    goalies = [p for p in data.get("players") or [] if p.get("kind") == "goalie"]
    top = sorted(skaters, key=lambda p: (-(p.get("points") or 0), -(p.get("goals") or 0), p.get("name") or ""))[:6]
    goalie_top = sorted(goalies, key=lambda p: (-(p.get("wins") or 0), -(p.get("save_pct") or 0), p.get("name") or ""))[:4]

    skater_rows = "".join(
        f'''<div class="leader-row"><span>{i}</span><div><b>{_esc(p.get("name"))}</b><em>{_esc(p.get("team"))} · {_esc(p.get("position"))}</em></div><strong>{p.get("points") or 0}</strong><small>очк.</small></div>'''
        for i,p in enumerate(top,1)
    ) or '<div class="nhl-empty">Статистика полевых игроков пока недоступна.</div>'

    goalie_rows = "".join(
        f'''<div class="leader-row goalie"><span>{i}</span><div><b>{_esc(p.get("name"))}</b><em>{_esc(p.get("team"))}</em></div><strong>{p.get("wins") or 0}</strong><small>поб.</small></div>'''
        for i,p in enumerate(goalie_top,1)
    ) or '<div class="nhl-empty">Вратари пока не загрузились.</div>'

    return f'''<div class="nhl-leader-columns"><div><h3>Полевые</h3>{skater_rows}</div><div><h3>Вратари</h3>{goalie_rows}</div></div>'''


def _roster(data: dict) -> str:
    players = data.get("players") or []
    if not players:
        errors = "; ".join(data.get("errors") or [])
        return f'<div class="nhl-empty">Ростеры NHL сейчас не загрузились.{f" {_esc(errors[:200])}" if errors else ""}</div>'

    skaters = [p for p in players if p.get("kind") == "skater"]
    goalies = [p for p in players if p.get("kind") == "goalie"]
    ordered = skaters + goalies
    cards = "".join(_player_card(p,data) for p in ordered)
    return cards


def _nhl_panel(data: dict) -> str:
    players = data.get("players") or []
    teams = sorted({p.get("team") for p in players if p.get("team")})
    skaters = [p for p in players if p.get("kind") == "skater"]
    goalies = [p for p in players if p.get("kind") == "goalie"]
    stat_season = _season_label(data.get("season_id"))
    current_season = _season_label(data.get("current_season_id"))
    mode = "текущий сезон" if data.get("is_current") else f"статистика {stat_season} · расписание {current_season}"

    return f'''<section class="big-mode-panel nhl-panel" data-mode-panel="nhl">
      <header class="nhl-head">
        <div><div class="nhl-kicker">NHL · НАШИ</div><h2>Россияне в НХЛ</h2><p>Текущие ростеры клубов + официальный контекст NHL. До старта регулярки статистика берётся из последнего завершённого сезона.</p></div>
        <div class="nhl-season"><b>{_esc(mode)}</b><span>{len(players)} игроков · {len(teams)} клубов</span></div>
      </header>

      <div class="nhl-summary">
        <article><span>В РОСТЕРАХ</span><strong>{len(players)}</strong><em>российских игроков</em></article>
        <article><span>ПОЛЕВЫХ</span><strong>{len(skaters)}</strong><em>в текущих ростерах</em></article>
        <article><span>ВРАТАРЕЙ</span><strong>{len(goalies)}</strong><em>в текущих ростерах</em></article>
        <article><span>КЛУБОВ</span><strong>{len(teams)}</strong><em>с российскими игроками</em></article>
      </div>

      <div class="nhl-top-grid">
        <article class="big-card nhl-games-card"><div class="card-head"><h3>Ближайшие матчи наших</h3><span>время · МСК</span></div><div class="nhl-games-grid">{_game_cards(data)}</div></article>
        <article class="big-card nhl-leaders-card"><div class="card-head"><h3>Лидеры</h3><span>{_esc(stat_season)}</span></div>{_leaders(data)}</article>
      </div>

      <article class="big-card nhl-roster-card">
        <div class="card-head"><h3>Все россияне в текущих ростерах</h3><span>{len(players)} игроков</span></div>
        <div class="nhl-roster-grid">{_roster(data)}</div>
      </article>
    </section>'''


def render_big_hockey_v58() -> str:
    page = ska.render_big_hockey_v57()
    soup = BeautifulSoup(page, "html.parser")

    data = nhl.load_russians(datetime.now(timezone.utc))

    tabs = soup.select_one(".big-tabs")
    if tabs:
        replacement = BeautifulSoup('''<div class="big-tabs">
          <button class="big-mode active" type="button" data-mode="ska">СКА-система</button>
          <button class="big-mode" type="button" data-mode="nhl">НХЛ: Наши</button>
          <span class="soon">Международный</span><span class="soon">Новости</span><span class="soon">История</span>
        </div>''', "html.parser")
        tabs.replace_with(replacement)

    system = soup.select_one(".system-grid")
    footer = soup.select_one(".big-footer")
    if system and footer:
        wrapper = soup.new_tag("section")
        wrapper["class"] = ["big-mode-panel","active"]
        wrapper["data-mode-panel"] = "ska"
        system.insert_before(wrapper)
        wrapper.append(system.extract())
        for panel in list(soup.select(".team-detail")):
            wrapper.append(panel.extract())
        footer.insert_before(BeautifulSoup(_nhl_panel(data), "html.parser"))

    hero_p = soup.select_one(".big-hero p")
    if hero_p:
        hero_p.string = "СКА-система и НХЛ: два внешних хоккейных мира, за которыми я слежу постоянно."

    hero_side = soup.select_one(".big-hero-side")
    if hero_side:
        hero_side.clear()
        hero_side.append(BeautifulSoup("<b>СКА-СИСТЕМА / NHL: НАШИ</b>матчи · таблицы · игроки · контекст", "html.parser"))

    if footer:
        spans = footer.find_all("span")
        if spans:
            spans[-1].string = f"v{VERSION}"

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.58 · NHL: Наши */
.big-tabs button.big-mode{padding:9px 13px;background:#0d141d;border:1px solid #273548;border-radius:10px;color:#77869a;font:inherit;font-size:11px;white-space:nowrap;cursor:pointer}
.big-tabs button.big-mode.active{background:linear-gradient(90deg,#b81f3a,#355fe3);border-color:transparent;color:#fff}
.big-mode-panel{display:none}.big-mode-panel.active{display:block}
.nhl-panel{margin-top:2px}.nhl-head{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end;padding:22px 20px;border:1px solid #293647;border-radius:17px;background:radial-gradient(circle at 90% 10%,rgba(65,108,255,.10),transparent 35%),linear-gradient(145deg,#101721,#0b1118)}
.nhl-kicker{color:#6885c7;font-size:8px;letter-spacing:.12em}.nhl-head h2{font-size:30px;margin:7px 0}.nhl-head p{color:#8c99aa;font-size:10px;line-height:1.55;max-width:720px;margin:0}.nhl-season{text-align:right}.nhl-season b{display:block;color:#c5d0dc;font-size:10px}.nhl-season span{display:block;color:#65768b;font-size:8px;margin-top:5px}
.nhl-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}.nhl-summary article{padding:14px 15px;border:1px solid #283646;border-radius:13px;background:#0c1219}.nhl-summary span{display:block;color:#66778c;font-size:8px;letter-spacing:.08em}.nhl-summary strong{display:block;font-size:26px;margin-top:8px}.nhl-summary em{display:block;color:#667587;font-size:8px;font-style:normal;margin-top:5px}
.nhl-top-grid{display:grid;grid-template-columns:1.25fr .75fr;gap:14px}.nhl-games-card,.nhl-leaders-card,.nhl-roster-card{padding-bottom:14px}.nhl-games-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;padding:0 14px}.nhl-game{position:relative;min-height:132px;padding:12px;border:1px solid #263543;border-radius:11px;background:#090f16}.nhl-game.live{border-color:#a43b4d}.nhl-game-top{display:flex;justify-content:space-between;color:#6a7a8d;font-size:7px}.nhl-game-top b{color:#ef526a}.nhl-game h3{font-size:14px;margin:18px 0 5px}.nhl-game h3 span{color:#506073}.nhl-game p{color:#6c7a8c;font-size:8px;margin:0}.nhl-game strong{position:absolute;right:11px;bottom:12px;font-size:13px}.nhl-game em{position:absolute;left:12px;bottom:10px;color:#526173;font-size:7px;font-style:normal}
.nhl-leader-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 14px}.nhl-leader-columns h3{font-size:9px;color:#738499;text-transform:uppercase;letter-spacing:.08em;margin:0 0 7px}.leader-row{display:grid;grid-template-columns:18px 1fr auto 25px;gap:6px;align-items:center;padding:8px 0;border-top:1px solid #202b37}.leader-row>span{color:#52657a;font-size:8px}.leader-row b{display:block;font-size:9px}.leader-row em{display:block;color:#607186;font-size:7px;font-style:normal;margin-top:3px}.leader-row strong{font-size:12px}.leader-row small{color:#627287;font-size:7px}
.nhl-roster-card{margin-top:14px}.nhl-roster-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:0 14px}.nhl-player{padding:12px;border:1px solid #253340;border-radius:11px;background:linear-gradient(180deg,#0d141c,#090e14)}.nhl-player-top{display:flex;justify-content:space-between;gap:8px;color:#6a7b8e;font-size:7px}.nhl-player-top em{font-style:normal;text-align:right}.nhl-player h3{font-size:12px;margin:10px 0 8px;min-height:30px}.nhl-player-stat{color:#b8c3cf;font-size:9px}.nhl-player-next{color:#617286;font-size:7px;margin-top:10px;border-top:1px solid #1e2934;padding-top:8px}.nhl-empty{padding:16px;color:#718095;font-size:9px}
@media(max-width:1050px){.nhl-top-grid{grid-template-columns:1fr}.nhl-roster-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.nhl-head{grid-template-columns:1fr}.nhl-season{text-align:left}.nhl-summary{grid-template-columns:1fr 1fr}.nhl-roster-grid{grid-template-columns:1fr 1fr}}@media(max-width:520px){.nhl-games-grid,.nhl-leader-columns,.nhl-roster-grid{grid-template-columns:1fr}}
""")

    script = soup.new_tag("script")
    script.string = r"""
(()=>{
  const buttons=[...document.querySelectorAll('.big-mode[data-mode]')];
  const panels=[...document.querySelectorAll('.big-mode-panel[data-mode-panel]')];
  function activate(mode, updateHash=true){
    if(!panels.some(p=>p.dataset.modePanel===mode)) mode='ska';
    buttons.forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
    panels.forEach(p=>p.classList.toggle('active',p.dataset.modePanel===mode));
    if(updateHash){
      try{history.replaceState(null,'',mode==='ska'?location.pathname:'#'+mode)}catch(e){}
    }
  }
  buttons.forEach(b=>b.addEventListener('click',()=>activate(b.dataset.mode)));
  const initial=location.hash==='#nhl'?'nhl':'ska';
  activate(initial,false);
})();
"""
    soup.body.append(script)

    return str(soup)


home_v44.render_big_hockey_v44 = render_big_hockey_v58
core.app.version = "0.58.0"
app = core.app


def _startup_smoke_v58() -> None:
    page = render_big_hockey_v58()
    required = ("СКА-система", "НХЛ: Наши", "Россияне в НХЛ", "Все россияне в текущих ростерах")
    missing = [x for x in required if x not in page]
    if missing:
        raise RuntimeError(f"v0.58 smoke missing: {missing}")
    print(f"[v58-smoke] big-hockey: OK chars={len(page)}", flush=True)


_startup_smoke_v58()
