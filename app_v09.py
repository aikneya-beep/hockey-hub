from __future__ import annotations

from datetime import datetime, timedelta
import html

import app_v08 as prev

core = prev.core
core.app.version = "0.9.0"


def _day_section(day, games, today, section_kind: str) -> str:
    label = "Сегодня" if day == today else "Завтра" if day == today + timedelta(days=1) else day.strftime("%d.%m.%Y")
    cards = "".join(prev._game_card(g) for g in games)
    return f'<section class="day" data-kind="{section_kind}"><h2>{label}</h2><div class="match-list">{cards}</div></section>'


def render_page_v09() -> str:
    # Сначала убираем возможные дубли резервных/живых источников.
    import app_v07 as dedup
    dedup.deduplicate_games()

    now = datetime.now(core.MOSCOW)
    today = now.date()
    with core.LOCK:
        games = list(core.GAMES.values())
        runs = dict(core.RUNS)

    # Будущие матчи храним далеко вперёд, результаты показываем за 30 дней.
    upcoming = [
        g for g in games
        if g.status != "finished" and g.start_at >= now - timedelta(hours=4) and g.start_at <= now + timedelta(days=120)
    ]
    results = [
        g for g in games
        if g.status == "finished" and now - timedelta(days=30) <= g.start_at <= now + timedelta(hours=4)
    ]

    upcoming_by_date: dict = {}
    for game in upcoming:
        upcoming_by_date.setdefault(game.start_at.date(), []).append(game)
    for day_games in upcoming_by_date.values():
        day_games.sort(key=lambda x: x.start_at)

    results_by_date: dict = {}
    for game in results:
        results_by_date.setdefault(game.start_at.date(), []).append(game)
    for day_games in results_by_date.values():
        day_games.sort(key=lambda x: x.start_at, reverse=True)

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

    upcoming_days = sorted(upcoming_by_date)
    result_days = sorted(results_by_date, reverse=True)

    upcoming_html = "".join(
        _day_section(day, upcoming_by_date[day], today, "upcoming") for day in upcoming_days
    ) or '<section class="empty">Ближайших матчей пока нет.</section>'

    results_html = "".join(
        _day_section(day, results_by_date[day], today, "results") for day in result_days
    ) or '<section class="empty">За последние 30 дней результатов пока нет.</section>'

    return f'''<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Мой хоккей</title><link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0b0d11"><meta name="apple-mobile-web-app-capable" content="yes">
<script>
try{{
  if(localStorage.getItem('hockeyHubNoSpoilers')==='1')document.documentElement.classList.add('spoiler-mode');
  const savedView=localStorage.getItem('hockeyHubView');
  if(savedView==='results')document.documentElement.classList.add('show-results');
}}catch(e){{}}
</script>
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
.sources{{display:flex;gap:8px;margin:16px 0 18px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}} .sources::-webkit-scrollbar{{display:none}}
.pill{{flex:0 0 auto;background:#151922;border:1px solid #252b36;border-radius:999px;padding:7px 11px;font-size:12px;white-space:nowrap}}
.pill b{{margin-right:7px}} .good{{color:#8bd49c}} .bad{{color:#ff8f8f}} .muted{{color:#818a99}}
.view-tabs{{display:flex;gap:6px;margin:0 0 26px;border-bottom:1px solid #222833;padding-bottom:10px}}
.view-tab{{padding:8px 12px;border-radius:9px;background:transparent;color:#8f99a8;border:1px solid transparent;font-size:13px}}
.view-tab.active{{background:#171c24;color:#fff;border-color:#2b3340}}
.view-count{{color:#707b8b;margin-left:5px;font-variant-numeric:tabular-nums}}
.view-panel.results{{display:none}} .show-results .view-panel.upcoming{{display:none}} .show-results .view-panel.results{{display:block}}
.day{{margin-top:22px}} .day:first-child{{margin-top:0}} .day h2{{font-size:14px;color:#a7afbc;text-transform:uppercase;letter-spacing:.07em;margin:0 0 8px}}
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
.empty{{color:#8993a4;padding:30px 0}}
@media(max-width:700px){{.hero{{align-items:flex-start;flex-direction:column}}.hero-actions{{width:100%}}.hero-actions form{{flex:1}}.hero-actions .refresh-button{{width:100%}}}}
@media(max-width:600px){{.wrap{{padding:20px 14px 60px}}.hero{{padding-bottom:16px}}h1{{font-size:34px}}.hero p{{font-size:13px;line-height:1.35}}.sources{{margin:13px 0 14px}}.view-tabs{{margin-bottom:22px}}.match{{grid-template-columns:58px minmax(0,1fr) 60px;gap:9px;min-height:70px;padding:9px 11px}}.clock time,.score-pair strong{{font-size:15px}}.team-name{{font-size:15px}}.spoiler-toggle{{padding-left:11px;padding-right:11px;font-size:12px}}}}
</style></head><body><main class="wrap">
<header class="hero"><div><div class="eyebrow">ХОККЕЙНЫЙ АГРЕГАТОР · v0.9</div><h1>Мой хоккей</h1><p>СКА · СКА-ВМФ · СКА-1946 · Академия СКА · Эскулап</p></div>
<div class="hero-actions"><button type="button" id="spoilerToggle" class="spoiler-toggle"><span class="spoiler-dot"></span><span class="spoiler-label">Не спойлерить</span></button><form method="post" action="/refresh"><button class="refresh-button">Обновить данные</button></form></div></header>
<section class="sources">{"".join(pills)}</section>
<nav class="view-tabs" aria-label="Режим просмотра">
  <button type="button" class="view-tab" id="upcomingTab" data-view="upcoming">Ближайшие <span class="view-count">{len(upcoming)}</span></button>
  <button type="button" class="view-tab" id="resultsTab" data-view="results">Результаты <span class="view-count">{len(results)}</span></button>
</nav>
<div class="view-panel upcoming">{upcoming_html}</div>
<div class="view-panel results">{results_html}</div>
</main><script>
(function(){{
  const root=document.documentElement;
  const spoilerKey='hockeyHubNoSpoilers';
  const viewKey='hockeyHubView';
  const toggle=document.getElementById('spoilerToggle');
  const label=toggle.querySelector('.spoiler-label');
  const upcomingTab=document.getElementById('upcomingTab');
  const resultsTab=document.getElementById('resultsTab');

  function syncSpoiler(){{
    const active=root.classList.contains('spoiler-mode');
    toggle.classList.toggle('active',active);
    toggle.setAttribute('aria-pressed',active?'true':'false');
    label.textContent=active?'Не спойлерить: вкл':'Не спойлерить';
  }}
  function syncView(){{
    const results=root.classList.contains('show-results');
    upcomingTab.classList.toggle('active',!results);
    resultsTab.classList.toggle('active',results);
    upcomingTab.setAttribute('aria-selected',results?'false':'true');
    resultsTab.setAttribute('aria-selected',results?'true':'false');
  }}
  function setView(view){{
    root.classList.toggle('show-results',view==='results');
    try{{localStorage.setItem(viewKey,view)}}catch(e){{}}
    syncView();
  }}
  upcomingTab.addEventListener('click',()=>setView('upcoming'));
  resultsTab.addEventListener('click',()=>setView('results'));
  toggle.addEventListener('click',function(){{
    root.classList.toggle('spoiler-mode');
    try{{localStorage.setItem(spoilerKey,root.classList.contains('spoiler-mode')?'1':'0')}}catch(e){{}}
    document.querySelectorAll('.match.revealed').forEach(el=>el.classList.remove('revealed'));
    syncSpoiler();
  }});
  window.revealScore=function(button){{button.closest('.match').classList.add('revealed')}};
  syncSpoiler(); syncView();
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
}})();
</script></body></html>'''


core.render_page = render_page_v09
app = core.app
