from __future__ import annotations

from datetime import datetime, timedelta
import html

import app_v07 as prev

core = prev.core
core.app.version = "0.8.0"


def _normalize_label(value: str) -> str:
    return core.compact(value).casefold().replace("–", "-").replace("—", "-")


def _secondary_text(game: core.Game) -> str:
    decision = "Б" if game.decision == "SO" else "ОТ" if game.decision == "OT" else ""
    arena = core.compact(game.arena or "")

    # СПбХЛ иногда кладёт в поле, которое мы считали ареной, подпись вида
    # «Эскулап - Космос-В». Это дублирует названия команд и засоряет карточку.
    if arena:
        pair = f"{game.home_team} - {game.away_team}"
        if _normalize_label(arena) == _normalize_label(pair):
            arena = ""

    return " · ".join(x for x in (decision, arena) if x)


def _game_card(game: core.Game) -> str:
    hs = prev._score_for(game, game.home_score)
    aw = prev._score_for(game, game.away_score)
    status_text = "LIVE" if game.status == "live" else ""
    source = (
        f'<a class="source-link" href="{html.escape(game.source_url)}" target="_blank" rel="noopener" '
        f'aria-label="Открыть источник" title="Открыть источник">↗</a>'
        if game.source_url else ""
    )
    secondary = _secondary_text(game)
    secondary_html = f'<div class="secondary">{html.escape(secondary)}</div>' if secondary else ""
    live_html = f'<span class="live-label">{status_text}</span>' if status_text else ""

    revealable = game.status in {"finished", "live"} and (game.home_score is not None or game.away_score is not None)
    reveal_class = " revealable" if revealable else ""
    mask = (
        '<button type="button" class="score-mask" onclick="revealScore(this)" '
        'aria-label="Показать счёт"><span>показать<br>счёт</span></button>'
        if revealable else ""
    )

    return f'''<article class="match {game.status}{reveal_class}">
      <div class="clock"><time>{game.start_at.strftime('%H:%M')}</time><span>{html.escape(game.league)} {source}</span></div>
      <div class="match-teams">
        {prev._team_html(game.home_team)}
        {prev._team_html(game.away_team)}
        {secondary_html}
      </div>
      <div class="match-scores">
        <div class="score-pair"><strong>{hs}</strong><strong>{aw}</strong></div>
        {mask}
        {live_html}
      </div>
    </article>'''


def render_page_v08() -> str:
    prev.deduplicate_games()
    now = datetime.now(core.MOSCOW)
    today = now.date()
    with core.LOCK:
        games = list(core.GAMES.values())
        runs = dict(core.RUNS)

    games = [g for g in games if now - timedelta(days=7) <= g.start_at <= now + timedelta(days=120)]
    by_date: dict = {}
    for game in games:
        by_date.setdefault(game.start_at.date(), []).append(game)
    for day_games in by_date.values():
        day_games.sort(key=lambda x: x.start_at)

    pills = []
    for team in core.TEAMS:
        run = runs.get(team.key)
        if not run:
            state = '<span class="muted">обновление…</span>'
        elif run["ok"]:
            state = f'<span class="good">✓ {run["rows"]}</span>'
        else:
            state = f'<span class="bad" title="{html.escape(run["error"] or "")}">ошибка</span>'
        pills.append(f'<div class="pill"><b>{html.escape(team.name)}</b>{state}</div>')

    def day_section(day) -> str:
        label = "Сегодня" if day == today else "Завтра" if day == today + timedelta(days=1) else day.strftime("%d.%m.%Y")
        return f'<section class="day"><h2>{label}</h2><div class="match-list">{"".join(_game_card(g) for g in by_date[day])}</div></section>'

    future_dates = sorted(day for day in by_date if day >= today)
    recent_dates = sorted((day for day in by_date if day < today), reverse=True)
    upcoming_html = "".join(day_section(day) for day in future_dates)
    recent_html = ""
    if recent_dates:
        recent_html = '<div class="archive-title"><span>Последние результаты</span></div>' + "".join(day_section(day) for day in recent_dates)
    if not upcoming_html and not recent_html:
        upcoming_html = '<section class="empty">Пока нет матчей в выбранном окне.</section>'

    return f'''<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Мой хоккей</title><link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0b0d11"><meta name="apple-mobile-web-app-capable" content="yes">
<script>try{{if(localStorage.getItem('hockeyHubNoSpoilers')==='1')document.documentElement.classList.add('spoiler-mode')}}catch(e){{}}</script>
<style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}} body{{margin:0;background:#0b0d11;color:#f5f7fa}} a{{color:inherit}}
.wrap{{max-width:920px;margin:auto;padding:26px 20px 80px}}
.hero{{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;border-bottom:1px solid #262b35;padding-bottom:20px}}
.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}} h1{{font-size:40px;margin:7px 0 3px;line-height:1}}
.hero p{{margin:0;color:#a8b0bd;font-size:15px}}
.hero-actions{{display:flex;align-items:center;gap:8px}}
button{{border:0;border-radius:11px;padding:11px 15px;font-weight:750;cursor:pointer;white-space:nowrap}}
.refresh-button{{background:#f0f3f7;color:#11151b}}
.spoiler-toggle{{background:#151922;color:#b3bdcb;border:1px solid #2b3340}}
.spoiler-toggle.active{{color:#f5f7fa;border-color:#697588;background:#1b202a}}
.spoiler-dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#596273;margin-right:7px;vertical-align:1px}}
.spoiler-toggle.active .spoiler-dot{{background:#8bd49c}}
.sources{{display:flex;gap:8px;margin:16px 0 26px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}} .sources::-webkit-scrollbar{{display:none}}
.pill{{flex:0 0 auto;background:#151922;border:1px solid #252b36;border-radius:999px;padding:7px 11px;font-size:12px;white-space:nowrap}}
.pill b{{margin-right:7px}} .good{{color:#8bd49c}} .bad{{color:#ff8f8f}} .muted{{color:#818a99}}
.day{{margin-top:22px}} .day h2{{font-size:14px;color:#a7afbc;text-transform:uppercase;letter-spacing:.07em;margin:0 0 8px}}
.match-list{{border:1px solid #252a33;border-radius:14px;overflow:hidden;background:#12161d}}
.match{{display:grid;grid-template-columns:70px minmax(0,1fr) 72px;gap:12px;align-items:center;min-height:74px;padding:10px 14px;border-bottom:1px solid #242a33}}
.match:last-child{{border-bottom:0}} .match.live{{box-shadow:inset 3px 0 0 #f5f7fa}}
.clock{{align-self:start;padding-top:2px}} .clock time{{display:block;font-size:17px;font-weight:750;font-variant-numeric:tabular-nums}}
.clock span{{display:block;color:#7f8999;font-size:10px;margin-top:3px;white-space:nowrap}} .source-link{{color:#8f99aa;text-decoration:none;margin-left:2px}}
.match-teams{{min-width:0;display:grid;gap:3px}} .team-name{{font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#e8ebf0}}
.team-name.fav{{font-weight:750;color:#fff}} .secondary{{font-size:11px;color:#737d8c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}}
.match-scores{{display:grid;align-items:center;justify-items:end;align-self:center;min-width:0}}
.score-pair{{display:grid;gap:3px;text-align:right}} .score-pair strong{{font-size:17px;font-variant-numeric:tabular-nums}}
.score-mask{{display:none;background:transparent;color:#9aa5b5;border:0;padding:0;font-size:10px;line-height:1.15;text-align:right}}
.spoiler-mode .match.revealable:not(.revealed) .score-pair{{display:none}}
.spoiler-mode .match.revealable:not(.revealed) .score-mask{{display:block}}
.live-label{{font-size:9px;font-weight:800;letter-spacing:.05em;color:#f5f7fa;margin-top:2px}}
.archive-title{{display:flex;align-items:center;gap:12px;margin:38px 0 6px;color:#747e8d;font-size:12px;text-transform:uppercase;letter-spacing:.08em}}
.archive-title:after{{content:"";height:1px;background:#252a33;flex:1}} .empty{{color:#8993a4;padding:30px 0}}
@media(max-width:700px){{.hero{{align-items:flex-start;flex-direction:column}}.hero-actions{{width:100%}}.hero-actions form{{flex:1}}.hero-actions .refresh-button{{width:100%}}}}
@media(max-width:600px){{.wrap{{padding:20px 14px 60px}}.hero{{padding-bottom:16px}}h1{{font-size:34px}}.hero p{{font-size:13px;line-height:1.35}}.sources{{margin:13px 0 22px}}.match{{grid-template-columns:58px minmax(0,1fr) 60px;gap:9px;min-height:70px;padding:9px 11px}}.clock time,.score-pair strong{{font-size:15px}}.team-name{{font-size:15px}}.spoiler-toggle{{padding-left:11px;padding-right:11px;font-size:12px}}}}
</style></head><body><main class="wrap">
<header class="hero"><div><div class="eyebrow">ХОККЕЙНЫЙ АГРЕГАТОР · v0.8</div><h1>Мой хоккей</h1><p>СКА · СКА-ВМФ · СКА-1946 · Академия СКА · Эскулап</p></div>
<div class="hero-actions"><button type="button" id="spoilerToggle" class="spoiler-toggle"><span class="spoiler-dot"></span><span class="spoiler-label">Не спойлерить</span></button><form method="post" action="/refresh"><button class="refresh-button">Обновить данные</button></form></div></header>
<section class="sources">{"".join(pills)}</section>{upcoming_html}{recent_html}
</main><script>
(function(){{
  const key='hockeyHubNoSpoilers';
  const root=document.documentElement;
  const toggle=document.getElementById('spoilerToggle');
  const label=toggle.querySelector('.spoiler-label');
  function sync(){{
    const active=root.classList.contains('spoiler-mode');
    toggle.classList.toggle('active',active);
    toggle.setAttribute('aria-pressed',active?'true':'false');
    label.textContent=active?'Не спойлерить: вкл':'Не спойлерить';
  }}
  toggle.addEventListener('click',function(){{
    root.classList.toggle('spoiler-mode');
    try{{localStorage.setItem(key,root.classList.contains('spoiler-mode')?'1':'0')}}catch(e){{}}
    document.querySelectorAll('.match.revealed').forEach(el=>el.classList.remove('revealed'));
    sync();
  }});
  window.revealScore=function(button){{button.closest('.match').classList.add('revealed')}};
  sync();
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
}})();
</script></body></html>'''


core.render_page = render_page_v08
app = core.app
