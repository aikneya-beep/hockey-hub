from __future__ import annotations

from datetime import datetime, timedelta
import html

# Импорт v0.6 применяет исправления KHL (пагинация и scheduled 0:0 -> —:—).
import app_v06  # noqa: F401
import app_v05 as core


# --- Защита от дублей -------------------------------------------------------
# В ранних версиях в памяти оставался резервный снимок Эскулапа, а затем тот
# же матч приходил со СПбХЛ под другим source_game_id. Склеиваем матчи по их
# бизнес-ключу: лига + хозяева + гости + минута начала.
def _canonical_game_key(game: core.Game) -> tuple[str, str, str, str]:
    return (
        game.league.casefold(),
        core.compact(game.home_team).casefold(),
        core.compact(game.away_team).casefold(),
        game.start_at.astimezone(core.MOSCOW).strftime("%Y-%m-%d %H:%M"),
    )


def _game_quality(game: core.Game) -> int:
    score = 0
    if game.status == "finished":
        score += 5
    if game.status == "live":
        score += 4
    if game.home_score is not None and game.away_score is not None:
        score += 2
    if game.arena:
        score += 1
    if game.source_url:
        score += 1
    # Для СПбХЛ ссылка на конкретный матч полезнее резервной ссылки на календарь.
    if game.source == "spbhl" and game.source_url and "Schedule?TeamID=" not in game.source_url:
        score += 10
    return score


def deduplicate_games() -> None:
    with core.LOCK:
        winner_by_key: dict[tuple[str, str, str, str], tuple[tuple[str, str], core.Game]] = {}
        remove: set[tuple[str, str]] = set()
        for storage_key, game in list(core.GAMES.items()):
            business_key = _canonical_game_key(game)
            previous = winner_by_key.get(business_key)
            if previous is None:
                winner_by_key[business_key] = (storage_key, game)
                continue
            previous_key, previous_game = previous
            if _game_quality(game) > _game_quality(previous_game):
                remove.add(previous_key)
                winner_by_key[business_key] = (storage_key, game)
            else:
                remove.add(storage_key)
        for key in remove:
            core.GAMES.pop(key, None)


_original_refresh_all = core.refresh_all


def refresh_all_v07() -> None:
    _original_refresh_all()
    deduplicate_games()


core.refresh_all = refresh_all_v07
core.app.version = "0.7.0"


# --- Компактный интерфейс ---------------------------------------------------
TRACKED = {team.name.casefold() for team in core.TEAMS}


def _team_html(name: str) -> str:
    cls = "team-name fav" if name.casefold() in TRACKED else "team-name"
    return f'<span class="{cls}" title="{html.escape(name)}">{html.escape(name)}</span>'


def _score_for(game: core.Game, value: int | None) -> str:
    if game.status == "scheduled":
        return "—"
    return str(value) if value is not None else "—"


def _game_card(game: core.Game) -> str:
    hs = _score_for(game, game.home_score)
    aw = _score_for(game, game.away_score)
    status_text = "LIVE" if game.status == "live" else ""
    decision = "Б" if game.decision == "SO" else "ОТ" if game.decision == "OT" else ""
    source = (
        f'<a class="source-link" href="{html.escape(game.source_url)}" target="_blank" rel="noopener" '
        f'aria-label="Открыть источник" title="Открыть источник">↗</a>'
        if game.source_url else ""
    )
    secondary = " · ".join(x for x in (decision, game.arena or "") if x)
    secondary_html = f'<div class="secondary">{html.escape(secondary)}</div>' if secondary else ""
    live_html = f'<span class="live-label">{status_text}</span>' if status_text else ""

    return f'''<article class="match {game.status}">
      <div class="clock"><time>{game.start_at.strftime('%H:%M')}</time><span>{html.escape(game.league)} {source}</span></div>
      <div class="match-teams">
        {_team_html(game.home_team)}
        {_team_html(game.away_team)}
        {secondary_html}
      </div>
      <div class="match-scores"><strong>{hs}</strong><strong>{aw}</strong>{live_html}</div>
    </article>'''


def render_page_v07() -> str:
    deduplicate_games()
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
<style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}} body{{margin:0;background:#0b0d11;color:#f5f7fa}} a{{color:inherit}}
.wrap{{max-width:920px;margin:auto;padding:26px 20px 80px}}
.hero{{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;border-bottom:1px solid #262b35;padding-bottom:20px}}
.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}} h1{{font-size:40px;margin:7px 0 3px;line-height:1}}
.hero p{{margin:0;color:#a8b0bd;font-size:15px}} button{{border:0;border-radius:11px;padding:11px 15px;background:#f0f3f7;color:#11151b;font-weight:750;cursor:pointer;white-space:nowrap}}
.sources{{display:flex;gap:8px;margin:16px 0 26px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}} .sources::-webkit-scrollbar{{display:none}}
.pill{{flex:0 0 auto;background:#151922;border:1px solid #252b36;border-radius:999px;padding:7px 11px;font-size:12px;white-space:nowrap}}
.pill b{{margin-right:7px}} .good{{color:#8bd49c}} .bad{{color:#ff8f8f}} .muted{{color:#818a99}}
.day{{margin-top:22px}} .day h2{{font-size:14px;color:#a7afbc;text-transform:uppercase;letter-spacing:.07em;margin:0 0 8px}}
.match-list{{border:1px solid #252a33;border-radius:14px;overflow:hidden;background:#12161d}}
.match{{display:grid;grid-template-columns:70px minmax(0,1fr) 30px;gap:12px;align-items:center;min-height:74px;padding:10px 14px;border-bottom:1px solid #242a33}}
.match:last-child{{border-bottom:0}} .match.live{{box-shadow:inset 3px 0 0 #f5f7fa}}
.clock{{align-self:start;padding-top:2px}} .clock time{{display:block;font-size:17px;font-weight:750;font-variant-numeric:tabular-nums}}
.clock span{{display:block;color:#7f8999;font-size:10px;margin-top:3px;white-space:nowrap}} .source-link{{color:#8f99aa;text-decoration:none;margin-left:2px}}
.match-teams{{min-width:0;display:grid;gap:3px}} .team-name{{font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#e8ebf0}}
.team-name.fav{{font-weight:750;color:#fff}} .secondary{{font-size:11px;color:#737d8c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}}
.match-scores{{display:grid;gap:3px;text-align:right;align-self:center}} .match-scores strong{{font-size:17px;font-variant-numeric:tabular-nums}}
.live-label{{font-size:9px;font-weight:800;letter-spacing:.05em;color:#f5f7fa;margin-top:2px}}
.archive-title{{display:flex;align-items:center;gap:12px;margin:38px 0 6px;color:#747e8d;font-size:12px;text-transform:uppercase;letter-spacing:.08em}}
.archive-title:after{{content:"";height:1px;background:#252a33;flex:1}} .empty{{color:#8993a4;padding:30px 0}}
@media(max-width:600px){{.wrap{{padding:20px 14px 60px}}.hero{{align-items:flex-start;flex-direction:column;padding-bottom:16px}}.hero form,.hero button{{width:100%}}h1{{font-size:34px}}.hero p{{font-size:13px;line-height:1.35}}.sources{{margin:13px 0 22px}}.match{{grid-template-columns:58px minmax(0,1fr) 25px;gap:9px;min-height:70px;padding:9px 11px}}.clock time,.match-scores strong{{font-size:15px}}.team-name{{font-size:15px}}}}
</style></head><body><main class="wrap">
<header class="hero"><div><div class="eyebrow">ХОККЕЙНЫЙ АГРЕГАТОР · v0.7</div><h1>Мой хоккей</h1><p>СКА · СКА-ВМФ · СКА-1946 · Академия СКА · Эскулап</p></div><form method="post" action="/refresh"><button>Обновить данные</button></form></header>
<section class="sources">{"".join(pills)}</section>{upcoming_html}{recent_html}
</main><script>if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');</script></body></html>'''


core.render_page = render_page_v07
app = core.app
