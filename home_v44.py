from __future__ import annotations

from datetime import datetime, timedelta
import html

from fastapi.responses import HTMLResponse

import app_v05 as core
import app_v40 as live_base


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _dedupe_games(games):
    seen = set()
    out = []
    for game in sorted(games, key=lambda g: g.start_at):
        key = (
            game.start_at.strftime("%Y-%m-%d %H:%M"),
            game.home_team.casefold(),
            game.away_team.casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(game)
    return out


def _tracked_label(game) -> str:
    if "Эскулап" in (game.home_team, game.away_team):
        return "МОЙ МИР"
    if game.league == "КХЛ":
        return "КХЛ"
    return game.league


def _when(game, today) -> tuple[str, str]:
    day = game.start_at.date()
    if day == today:
        return "Сегодня", game.start_at.strftime("%H:%M")
    if day == today + timedelta(days=1):
        return "Завтра", game.start_at.strftime("%H:%M")
    return game.start_at.strftime("%d.%m"), game.start_at.strftime("%H:%M")


def _score(game) -> str:
    if game.home_score is None or game.away_score is None:
        return "— : —"
    return f"{game.home_score} : {game.away_score}"


def _event_card(game, today) -> str:
    day, clock = _when(game, today)
    status = "LIVE" if game.status == "live" else _tracked_label(game)
    status_class = "live" if game.status == "live" else ("personal" if "Эскулап" in (game.home_team, game.away_team) else "big")
    score = _score(game)
    arena = f'<div class="event-arena">{_esc(game.arena)}</div>' if game.arena else ""
    source = f'<a class="event-link" href="{_esc(game.source_url)}" target="_blank" rel="noopener">источник ↗</a>' if game.source_url else ""
    return f'''<article class="event-card {status_class}">
      <div class="event-top"><span class="event-day">{day}</span><span class="event-tag">{status}</span></div>
      <div class="event-time">{clock}</div>
      <div class="event-match"><b>{_esc(game.home_team)}</b><span>—</span><b>{_esc(game.away_team)}</b></div>
      <div class="event-score score-value">{score}</div>
      {arena}{source}
    </article>'''


def _team_next(team_name: str, games, now) -> str:
    team_games = [g for g in games if team_name in (g.home_team, g.away_team)]
    live = next((g for g in team_games if g.status == "live"), None)
    game = live or next((g for g in team_games if g.start_at >= now and g.status != "finished"), None)
    if game is None:
        return '<span class="muted">нет ближайшего матча</span>'
    opponent = game.away_team if game.home_team == team_name else game.home_team
    prefix = "LIVE" if game.status == "live" else game.start_at.strftime("%d.%m · %H:%M")
    return f'<span class="next-meta">{prefix}</span><b>{_esc(opponent)}</b>'


def _source_health(runs) -> str:
    good = 0
    total = len(core.TEAMS)
    for team in core.TEAMS:
        row = runs.get(team.key)
        if row and row.get("ok"):
            good += 1
    return f"{good}/{total} источников"


def render_home_v44() -> str:
    now = datetime.now(core.MOSCOW)
    today = now.date()
    with core.LOCK:
        games = _dedupe_games(list(core.GAMES.values()))
        runs = dict(core.RUNS)

    current = [
        g for g in games
        if g.status == "live" or (g.start_at >= now - timedelta(hours=2) and g.start_at <= now + timedelta(days=21))
    ]
    upcoming = [g for g in current if g.status == "live" or g.start_at >= now]
    nearest = upcoming[:4]

    # What to watch: KHL first, then Eskulap, then nearest tracked event.
    watch = next((g for g in upcoming if g.league == "КХЛ"), None)
    if watch is None:
        watch = next((g for g in upcoming if "Эскулап" in (g.home_team, g.away_team)), None)
    if watch is None and upcoming:
        watch = upcoming[0]

    if nearest:
        event_cards = "".join(_event_card(g, today) for g in nearest)
    else:
        event_cards = '<div class="empty-card">Ближайшие события пока не загрузились.</div>'

    if watch:
        watch_day, watch_time = _when(watch, today)
        watch_score = _score(watch)
        watch_html = f'''<div class="watch-copy">
          <div class="kicker">{watch_day} · {watch.league}</div>
          <div class="watch-time">{watch_time}</div>
          <h3>{_esc(watch.home_team)} <span>—</span> {_esc(watch.away_team)}</h3>
          <div class="watch-score score-value">{watch_score}</div>
          <p>{'Матч уже идёт — карточка обновляется автоматически.' if watch.status == 'live' else 'Ближайший матч высшего приоритета в твоём календаре.'}</p>
          {f'<a class="ghost-button" href="{_esc(watch.source_url)}" target="_blank" rel="noopener">Открыть матч ↗</a>' if watch.source_url else ''}
        </div>'''
    else:
        watch_html = '<div class="watch-copy"><div class="kicker">СЕГОДНЯ</div><h3>Спокойный день</h3><p>Ближайший матч появится здесь после обновления календаря.</p></div>'

    team_tiles = []
    for name, label in (("СКА", "КХЛ"), ("СКА-ВМФ", "ВХЛ"), ("СКА-1946", "МХЛ"), ("Академия СКА", "МХЛ")):
        team_tiles.append(f'''<div class="team-tile"><span>{label}</span><strong>{name}</strong>{_team_next(name, games, now)}</div>''')

    esk = _team_next("Эскулап", games, now)
    recent_finished = [g for g in games if g.status == "finished" and g.start_at < now]
    recent_finished.sort(key=lambda g: g.start_at, reverse=True)
    news_rows = []
    for g in recent_finished[:4]:
        news_rows.append(
            f'''<div class="feed-row"><span>{g.start_at.strftime('%d.%m')}</span><b>{_esc(g.home_team)} <i class="score-value">{_score(g)}</i> {_esc(g.away_team)}</b><em>{g.league}</em></div>'''
        )
    if not news_rows:
        news_rows.append('<div class="feed-row muted">Завершённые матчи появятся после загрузки.</div>')

    date_title = now.strftime("%d.%m.%Y")
    health = _source_health(runs)

    page = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hockey Hub · Сегодня</title><link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#070a10">
<style>
:root{{--bg:#070a10;--panel:#0e141d;--panel2:#111925;--line:#243040;--text:#f4f7fb;--muted:#8995a6;--red:#e51d3e;--blue:#315cff;--silver:#c9d2de;--personal:#8e9aac;color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;background:radial-gradient(circle at 16% 0%,rgba(49,92,255,.09),transparent 28%),radial-gradient(circle at 82% 0%,rgba(229,29,62,.06),transparent 24%),var(--bg);color:var(--text)}}a{{color:inherit}}button{{font:inherit}}.shell{{max-width:1180px;margin:auto;padding:0 22px 64px}}
.topbar{{height:72px;display:grid;grid-template-columns:auto 1fr auto;gap:28px;align-items:center;border-bottom:1px solid rgba(130,150,175,.18)}}.brand{{font-weight:900;letter-spacing:.02em;font-size:19px;text-decoration:none}}.brand span{{color:#4e74ff}}.nav{{display:flex;gap:24px;align-items:center}}.nav a{{text-decoration:none;color:#99a5b5;font-size:13px;white-space:nowrap}}.nav a.active,.nav a:hover{{color:#fff}}.nav a.active{{position:relative}}.nav a.active:after{{content:"";position:absolute;left:0;right:0;bottom:-27px;height:2px;background:linear-gradient(90deg,var(--red),var(--blue))}}.actions{{display:flex;gap:8px;align-items:center}}.icon-btn,.refresh{{border:1px solid #2b3747;background:#101721;color:#dbe2eb;border-radius:10px;padding:9px 11px;text-decoration:none;cursor:pointer}}.refresh{{font-size:12px}}.icon-btn{{width:38px;text-align:center}}
.hero{{display:grid;grid-template-columns:1fr auto;gap:24px;padding:34px 0 22px;align-items:end}}.eyebrow{{font-size:11px;letter-spacing:.16em;color:#778497;text-transform:uppercase}}h1{{font-size:52px;line-height:.96;margin:9px 0 10px;letter-spacing:-.035em}}.hero p{{margin:0;color:#9aa6b6;font-size:16px}}.datebox{{text-align:right;color:#718094;font-size:12px;line-height:1.7}}.datebox strong{{display:block;color:#d6dde7;font-size:13px}}.status-dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#7bd493;margin-right:6px}}
.section-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}.section-head h2{{margin:0;font-size:15px;letter-spacing:.01em}}.section-head a{{font-size:11px;color:#7f8c9e;text-decoration:none}}.events{{border:1px solid #263447;background:linear-gradient(180deg,rgba(17,25,37,.96),rgba(10,15,23,.96));border-radius:18px;padding:16px;margin-bottom:14px}}.event-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.event-card{{min-height:168px;border:1px solid #273444;background:#0d141e;border-radius:14px;padding:13px;position:relative;overflow:hidden}}.event-card.big:before{{content:"";position:absolute;inset:0 auto 0 0;width:2px;background:linear-gradient(var(--red),var(--blue))}}.event-card.personal:before{{content:"";position:absolute;inset:0 auto 0 0;width:2px;background:linear-gradient(#d2d8df,#476f9b)}}.event-card.live{{border-color:#d84459;box-shadow:0 0 0 1px rgba(229,29,62,.18) inset}}.event-top{{display:flex;justify-content:space-between;gap:8px;color:#7f8c9d;font-size:10px;text-transform:uppercase;letter-spacing:.07em}}.event-tag{{color:#adb8c7}}.event-card.live .event-tag{{color:#ff6078}}.event-time{{font-size:24px;font-weight:800;margin:11px 0 13px}}.event-match{{display:grid;gap:3px;font-size:13px}}.event-match span{{display:none}}.event-score{{position:absolute;right:13px;bottom:35px;font-weight:800;font-variant-numeric:tabular-nums}}.event-arena{{position:absolute;left:13px;right:72px;bottom:12px;color:#667489;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.event-link{{position:absolute;right:13px;bottom:12px;color:#8291a5;font-size:9px;text-decoration:none}}.empty-card{{color:#7f8c9d;padding:26px}}
.dashboard{{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;margin-top:14px}}.card{{background:linear-gradient(180deg,#101721,#0c121a);border:1px solid #263241;border-radius:17px;padding:16px;min-width:0}}.watch{{min-height:280px;position:relative;overflow:hidden;background:radial-gradient(circle at 85% 20%,rgba(49,92,255,.16),transparent 36%),linear-gradient(145deg,#111925,#0b1018 62%)}}.watch:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(var(--red),var(--blue))}}.kicker{{color:#ff526b;font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}}.watch-time{{font-size:42px;font-weight:900;margin-top:28px}}.watch h3{{font-size:24px;margin:5px 0 6px;max-width:75%}}.watch h3 span{{color:#607088;font-weight:400}}.watch-score{{font-size:16px;color:#a9b5c5;margin:6px 0 15px}}.watch p{{color:#8895a7;font-size:12px;max-width:66%;line-height:1.5}}.ghost-button{{display:inline-block;border:1px solid #34465e;border-radius:9px;padding:9px 11px;font-size:11px;text-decoration:none;margin-top:8px}}.worlds{{display:grid;gap:14px}}.world-title{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}.world-title h3{{margin:0;font-size:13px}}.world-title a{{font-size:10px;color:#7d899a;text-decoration:none}}.team-strip{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}.team-tile{{background:#0b1119;border:1px solid #253243;border-radius:12px;padding:11px;min-height:88px}}.team-tile>span{{color:#6f7c90;font-size:9px}}.team-tile>strong{{display:block;margin:4px 0 10px;font-size:13px}}.team-tile .next-meta{{display:block;color:#e65068!important;font-size:9px;margin-bottom:2px}}.team-tile b{{font-size:11px;font-weight:600;color:#aeb9c8}}.personal-box{{border-color:#35404d;background:linear-gradient(145deg,#0d1116,#111821)}}.personal-box .world-title h3{{color:#d9dfe7}}.esk-line{{display:flex;justify-content:space-between;gap:18px;align-items:center;border-top:1px solid #252e39;padding-top:12px}}.esk-line>div:first-child span{{display:block;color:#788598;font-size:9px;margin-bottom:3px}}.esk-line b{{font-size:12px}}.lock-note{{font-size:10px;color:#6f7b8b;max-width:160px;text-align:right;line-height:1.35}}
.lower{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}.feed-row{{display:grid;grid-template-columns:42px 1fr auto;gap:10px;align-items:center;border-top:1px solid #222d3b;padding:10px 0;font-size:10px}}.feed-row:first-of-type{{border-top:0}}.feed-row>span{{color:#647186}}.feed-row b{{font-size:11px;font-weight:600}}.feed-row i{{font-style:normal;font-variant-numeric:tabular-nums;color:#cbd3dd;margin:0 4px}}.feed-row em{{font-style:normal;color:#718096;font-size:9px}}.architecture{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.arch-link{{display:block;padding:14px;border:1px solid #293647;border-radius:12px;text-decoration:none;background:#0c121a}}.arch-link strong{{display:block;font-size:14px;margin-bottom:5px}}.arch-link span{{display:block;color:#748196;font-size:10px;line-height:1.4}}.arch-link.big{{box-shadow:inset 2px 0 var(--red)}}.arch-link.mine{{box-shadow:inset 2px 0 #aeb7c2}}.footer{{display:flex;justify-content:space-between;border-top:1px solid #202a36;margin-top:24px;padding-top:16px;color:#59677a;font-size:9px;letter-spacing:.06em;text-transform:uppercase}}
body.hide-scores .score-value{{filter:blur(7px);user-select:none}}.spoiler-on{{color:#fff!important;border-color:#61718a!important}}
@media(max-width:900px){{.event-grid{{grid-template-columns:repeat(2,1fr)}}.dashboard,.lower{{grid-template-columns:1fr}}.topbar{{grid-template-columns:auto auto}}.nav{{grid-column:1/-1;order:3;height:42px;border-top:1px solid #1b2633;overflow:auto}}.topbar{{height:auto;padding-top:14px}}.nav a.active:after{{bottom:-13px}}.actions{{justify-self:end}}}}
@media(max-width:560px){{.shell{{padding:0 13px 48px}}.brand{{font-size:17px}}.nav{{gap:18px}}.hero{{grid-template-columns:1fr;padding-top:25px}}.datebox{{display:none}}h1{{font-size:42px}}.hero p{{font-size:14px}}.event-grid{{grid-template-columns:1fr}}.event-card{{min-height:145px}}.team-strip{{grid-template-columns:1fr 1fr}}.watch-time{{font-size:36px}}.watch h3{{max-width:100%}}.watch p{{max-width:100%}}.architecture{{grid-template-columns:1fr}}}}
</style></head><body><main class="shell">
<header class="topbar"><a class="brand" href="/">HOCKEY <span>HUB</span></a><nav class="nav"><a class="active" href="/">Главная</a><a href="/big-hockey">Большой хоккей</a><a href="/my-hockey">Мой хоккей</a></nav><div class="actions"><button class="icon-btn" id="spoilerToggle" type="button" title="Скрыть счёт">◉</button><form method="post" action="/refresh"><button class="refresh">Обновить</button></form></div></header>
<section class="hero"><div><div class="eyebrow">Hockey Hub · v0.44 · персональный briefing</div><h1>Сегодня</h1><p>За минуту понять, что происходит в твоём хоккейном мире.</p></div><div class="datebox"><strong>{date_title}</strong><span class="status-dot"></span>{health}</div></section>
<section class="events"><div class="section-head"><h2>Ближайшие события</h2><a href="#calendar">единый календарь →</a></div><div class="event-grid">{event_cards}</div></section>
<section class="dashboard"><article class="card watch"><div class="section-head"><h2>Что смотреть</h2><a href="/big-hockey">Большой хоккей →</a></div>{watch_html}</article><div class="worlds"><article class="card"><div class="world-title"><h3>Большой хоккей · СКА-система</h3><a href="/big-hockey">открыть →</a></div><div class="team-strip">{''.join(team_tiles)}</div></article><article class="card personal-box"><div class="world-title"><h3>Мой хоккей</h3><a href="/my-hockey">открыть →</a></div><div class="esk-line"><div><span>ТЁМА И КОМАНДЫ · ЭСКУЛАП</span>{esk}</div><div class="lock-note">Личные тренировки и прогресс перенесём сюда после включения авторизации.</div></div></article></div></section>
<section class="lower"><article class="card"><div class="section-head"><h2>Последние результаты</h2><a href="/big-hockey">весь хоккей →</a></div>{''.join(news_rows)}</article><article class="card"><div class="section-head"><h2>Два мира одной системы</h2><span></span></div><div class="architecture"><a class="arch-link big" href="/big-hockey"><strong>Большой хоккей</strong><span>СКА · НХЛ · международный хоккей · новости · история</span></a><a class="arch-link mine" href="/my-hockey"><strong>Мой хоккей</strong><span>Я · Тёма и команды · хоккейный шкаф · память</span></a></div></article></section>
<footer class="footer"><span>Hockey Hub · личная хоккейная операционная система</span><span>Большой хоккей + Мой хоккей</span></footer>
</main><script>
const key='hockeyHubSpoilersHidden';const btn=document.getElementById('spoilerToggle');function applySpoilers(){{let hidden=false;try{{hidden=localStorage.getItem(key)==='1'}}catch(e){{}}document.body.classList.toggle('hide-scores',hidden);btn?.classList.toggle('spoiler-on',hidden);if(btn)btn.title=hidden?'Показать счёт':'Скрыть счёт'}}btn?.addEventListener('click',()=>{{let hidden=document.body.classList.toggle('hide-scores');try{{localStorage.setItem(key,hidden?'1':'0')}}catch(e){{}}btn.classList.toggle('spoiler-on',hidden);btn.title=hidden?'Показать счёт':'Скрыть счёт'}});applySpoilers();if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
</script></body></html>'''
    return live_base._reload(page)


def render_big_hockey_v44() -> str:
    now = datetime.now(core.MOSCOW)
    with core.LOCK:
        games = _dedupe_games(list(core.GAMES.values()))
    tiles = []
    for name, league in (("СКА", "КХЛ"), ("СКА-ВМФ", "ВХЛ"), ("СКА-1946", "МХЛ"), ("Академия СКА", "МХЛ")):
        tiles.append(f'<article class="bh-team"><span>{league}</span><h2>{name}</h2>{_team_next(name, games, now)}</article>')
    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Большой хоккей · Hockey Hub</title><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#070a10;color:#f5f7fb}}a{{color:inherit}}.wrap{{max-width:1100px;margin:auto;padding:0 22px 70px}}header{{height:72px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #243040}}header a{{text-decoration:none}}.brand{{font-weight:900}}.brand span{{color:#4e74ff}}nav{{display:flex;gap:22px;font-size:13px;color:#8d99aa}}nav .on{{color:#fff}}.hero{{padding:42px 0 26px;border-bottom:1px solid #1f2a37;background:radial-gradient(circle at 75% 30%,rgba(49,92,255,.14),transparent 32%),radial-gradient(circle at 20% 40%,rgba(229,29,62,.10),transparent 28%)}}.hero small{{color:#ff4e69;letter-spacing:.13em}}h1{{font-size:48px;margin:8px 0}}.hero p{{color:#8f9bac}}.tabs{{display:flex;gap:8px;padding:18px 0}}.tabs span{{padding:9px 13px;background:#101722;border:1px solid #273548;border-radius:10px;color:#8693a5;font-size:12px}}.tabs .on{{background:linear-gradient(90deg,#c81835,#315cff);color:white;border-color:transparent}}.teams{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.bh-team{{min-height:150px;padding:16px;background:#0f1620;border:1px solid #283649;border-radius:14px;box-shadow:inset 0 2px rgba(49,92,255,.18)}}.bh-team span{{font-size:10px;color:#718096}}.bh-team h2{{font-size:17px;margin:8px 0 20px}}.bh-team .next-meta{{display:block;color:#ef536a!important;font-size:10px;margin-bottom:4px}}.bh-team b{{font-size:12px;color:#a8b3c2}}.roadmap{{margin-top:14px;display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px}}.roadmap>div{{padding:16px;background:#0c121a;border:1px solid #243144;border-radius:14px}}.roadmap h3{{margin:0 0 8px;font-size:14px}}.roadmap p{{margin:0;color:#788598;font-size:11px;line-height:1.5}}@media(max-width:760px){{.teams{{grid-template-columns:1fr 1fr}}.roadmap{{grid-template-columns:1fr}}nav{{gap:10px;font-size:11px}}}}@media(max-width:480px){{.teams{{grid-template-columns:1fr}}}}
</style></head><body><main class="wrap"><header><a class="brand" href="/">HOCKEY <span>HUB</span></a><nav><a href="/">Главная</a><a class="on" href="/big-hockey">Большой хоккей</a><a href="/my-hockey">Мой хоккей</a></nav></header><section class="hero"><small>ВНЕШНИЙ ХОККЕЙНЫЙ МИР</small><h1>Большой хоккей</h1><p>СКА, НХЛ, международный хоккей, новости и история — в одном разделе.</p></section><div class="tabs"><span class="on">СКА</span><span>НХЛ</span><span>Международный</span><span>Новости</span><span>История</span></div><section class="teams">{''.join(tiles)}</section><section class="roadmap"><div><h3>СКА-система</h3><p>Первым сюда переносим текущие матчи, таблицы, плей-офф и будущую вертикаль игроков.</p></div><div><h3>НХЛ: Наши</h3><p>Следующий источник данных: российские игроки, ночная сводка и таблица.</p></div><div><h3>Мир</h3><p>ИИХФ, чемпионаты мира и Олимпиада — компактно, без глобального livescore.</p></div></section></main></body></html>'''
    return live_base._reload(page)


def register_routes(app):
    @app.get("/big-hockey", response_class=HTMLResponse)
    def big_hockey_page():
        return render_big_hockey_v44()
