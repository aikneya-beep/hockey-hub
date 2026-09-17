from __future__ import annotations

from datetime import datetime
import html

import app_v05 as core
import personal_hockey_v42 as personal_base
import closet_v48
from design_system_v46 import COMMON_CSS, topbar


_previous_personal_renderer = personal_base.render_personal_page
_previous_closet_renderer = closet_v48.render_closet


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _eskulap_games():
    with core.LOCK:
        games = [g for g in core.GAMES.values() if "Эскулап" in (g.home_team, g.away_team)]
    # Deduplicate by date + pair, because historical adapters may leave aliases in cache.
    unique = {}
    for game in games:
        key = (game.start_at.strftime("%Y-%m-%d %H:%M"), game.home_team, game.away_team)
        old = unique.get(key)
        if old is None or (old.home_score is None and game.home_score is not None):
            unique[key] = game
    return sorted(unique.values(), key=lambda g: g.start_at)


def _eskulap_summary(games) -> dict:
    now = datetime.now(core.MOSCOW)
    finished = [g for g in games if g.status == "finished" and g.home_score is not None and g.away_score is not None]
    wins = losses = draws = goals_for = goals_against = 0
    for g in finished:
        home = g.home_team == "Эскулап"
        gf = g.home_score if home else g.away_score
        ga = g.away_score if home else g.home_score
        goals_for += int(gf)
        goals_against += int(ga)
        if gf > ga:
            wins += 1
        elif gf < ga:
            losses += 1
        else:
            draws += 1
    live = next((g for g in games if g.status == "live"), None)
    upcoming = next((g for g in games if g.start_at >= now and g.status != "finished"), None)
    latest = finished[-1] if finished else None
    return {
        "finished": finished,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "gf": goals_for,
        "ga": goals_against,
        "current": live or upcoming,
        "latest": latest,
    }


def _result_for_eskulap(game) -> tuple[str, str]:
    if game.home_score is None or game.away_score is None:
        return "—", "neutral"
    home = game.home_team == "Эскулап"
    gf = game.home_score if home else game.away_score
    ga = game.away_score if home else game.home_score
    if gf > ga:
        return "П", "win"
    if gf < ga:
        return "ПР", "loss"
    return "Н", "draw"


def _opponent(game) -> str:
    return game.away_team if game.home_team == "Эскулап" else game.home_team


def _form_html(finished) -> str:
    if not finished:
        return '<div class="empty">Результаты пока не загружены.</div>'
    chips = []
    for game in finished[-8:]:
        label, cls = _result_for_eskulap(game)
        chips.append(
            f'<span class="form-chip {cls}" title="{_esc(game.start_at.strftime("%d.%m"))} · {_esc(_opponent(game))}">{label}</span>'
        )
    return "".join(chips)


def _recent_games_html(finished) -> str:
    if not finished:
        return '<div class="empty">Матчей пока нет.</div>'
    rows = []
    for game in reversed(finished[-5:]):
        label, cls = _result_for_eskulap(game)
        source = (
            f'<a href="{html.escape(game.source_url, quote=True)}" target="_blank" rel="noopener">источник ↗</a>'
            if game.source_url else ""
        )
        rows.append(
            f'''<article class="match-row">
              <time>{game.start_at.strftime('%d.%m')}</time>
              <span class="result-mark {cls}">{label}</span>
              <div><b>{_esc(game.home_team)} <strong>{game.home_score}:{game.away_score}</strong> {_esc(game.away_team)}</b><em>{_esc(game.arena or 'СПбХЛ')}</em></div>
              {source}
            </article>'''
        )
    return "".join(rows)


def _next_game_html(game) -> str:
    if not game:
        return '<div class="empty">Следующий матч пока не появился в источнике.</div>'
    live = game.status == "live"
    score = ""
    if game.home_score is not None and game.away_score is not None:
        score = f'<div class="next-score">{game.home_score}:{game.away_score}</div>'
    source = (
        f'<a class="ghost" href="{html.escape(game.source_url, quote=True)}" target="_blank" rel="noopener">Открыть источник ↗</a>'
        if game.source_url else ""
    )
    return f'''<div class="next-game{' live' if live else ''}">
      <div class="next-kicker">{'LIVE' if live else game.start_at.strftime('%d.%m.%Y · %H:%M')}</div>
      <h3>{_esc(game.home_team)} <span>—</span> {_esc(game.away_team)}</h3>
      {score}<p>{_esc(game.arena or 'Арена пока не указана')}</p>{source}
    </div>'''


def _coach_notes_html() -> str:
    try:
        data = personal_base.STORE.load()
        notes = sorted(data.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    except Exception:
        notes = []
    if not notes:
        return '<div class="empty">Отдельных комментариев тренера пока нет.</div>'
    rows = []
    for note in notes[:5]:
        raw_date = note.get("date") or ""
        try:
            label = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            label = raw_date
        rows.append(
            f'<article class="coach-note"><time>{_esc(label)}</time><p>{_esc(note.get("text") or "")}</p></article>'
        )
    return "".join(rows)


def render_environment() -> str:
    games = _eskulap_games()
    summary = _eskulap_summary(games)
    finished = summary["finished"]
    played = len(finished)
    record = f'{summary["wins"]}–{summary["losses"]}' + (f'–{summary["draws"]}' if summary["draws"] else '')
    latest = summary["latest"]
    latest_text = "—"
    if latest:
        latest_text = f'{latest.home_team} {latest.home_score}:{latest.away_score} {latest.away_team}'

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Моя хоккейная среда · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>
{COMMON_CSS}
:root{{--soyuz:#2a86d9;--soyuz-dim:#365c7d;--silver:#c8d0da}}
body{{background:radial-gradient(circle at 80% 2%,rgba(42,134,217,.10),transparent 24%),linear-gradient(180deg,#05070b,#080b0f 58%,#05070b)}}
.env-hero{{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}.env-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.env-hero p{{margin:0;color:#929dac;max-width:720px;font-size:15px;line-height:1.55}}.env-code{{text-align:right;color:#708094;font-size:9px;letter-spacing:.12em;text-transform:uppercase}}.env-code b{{display:block;color:#d8dee6;font-size:13px;letter-spacing:.04em;margin-bottom:4px}}
.mine-tabs{{display:flex;gap:8px;margin:18px 0;overflow:auto}}.mine-tabs a{{position:relative;text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}}.mine-tabs a.active{{color:#f2f5f8;border-color:#53616f;background:linear-gradient(180deg,#161c23,#0e1319)}}.mine-tabs a.active:after{{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--soyuz);box-shadow:0 0 10px rgba(42,134,217,.3)}}
.env-grid{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:14px}}.panel{{padding:18px}}.section-title{{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:15px}}.section-title h2{{margin:0;font-size:15px}}.section-title span{{color:#6f7d8d;font-size:9px;text-transform:uppercase;letter-spacing:.12em}}
.coach-card{{position:relative;overflow:hidden;min-height:240px;background:radial-gradient(circle at 90% 10%,rgba(42,134,217,.11),transparent 35%),linear-gradient(145deg,#11171f,#090d12);border:1px solid #28323e;border-radius:16px;padding:20px}}.coach-card:before{{content:"";position:absolute;left:20px;top:0;width:56px;height:2px;background:linear-gradient(90deg,var(--soyuz),var(--soyuz-dim))}}.coach-kicker{{color:#6f8297;font-size:9px;text-transform:uppercase;letter-spacing:.12em}}.coach-card h2{{font-size:30px;margin:12px 0 5px}}.coach-role{{color:#c6ced8;font-size:12px}}.coach-copy{{max-width:650px;color:#8995a5;font-size:11px;line-height:1.6;margin-top:22px}}.coach-tags{{display:flex;flex-wrap:wrap;gap:7px;margin-top:18px}}.coach-tags span{{border:1px solid #2d3946;background:#0b1118;border-radius:999px;padding:5px 8px;color:#8494a6;font-size:8px;text-transform:uppercase;letter-spacing:.06em}}
.team-card{{margin-top:14px;padding:18px}}.team-head{{display:flex;justify-content:space-between;gap:18px;align-items:start}}.team-head h2{{font-size:24px;margin:3px 0}}.team-head p{{color:#738194;font-size:10px;margin:0}}.team-badge{{border:1px solid #31506c;border-radius:999px;padding:5px 8px;color:#8eb4d8;font-size:8px;white-space:nowrap}}.team-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:17px 0}}.mini-stat{{position:relative;overflow:hidden;border:1px solid #232d38;background:#090d12;border-radius:12px;padding:12px;min-height:82px}}.mini-stat:before{{content:"";position:absolute;left:12px;top:0;width:28px;height:2px;background:var(--soyuz);opacity:.65}}.mini-stat span{{display:block;color:#697687;font-size:8px;text-transform:uppercase;letter-spacing:.08em}}.mini-stat b{{display:block;font-size:20px;margin-top:10px}}.form-line{{display:flex;align-items:center;gap:6px;flex-wrap:wrap}}.form-chip{{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;font-size:8px;font-weight:850;border:1px solid #2a333d;background:#10151b;color:#9aa5b2}}.form-chip.win{{border-color:#335844;color:#9fcaae}}.form-chip.loss{{border-color:#57363c;color:#d69ba2}}.form-chip.draw{{border-color:#5b5238;color:#cfbd8e}}
.next-game{{border:1px solid #263443;background:#090e14;border-radius:13px;padding:15px;min-height:160px}}.next-game.live{{border-color:#743845}}.next-kicker{{color:#7790aa;font-size:9px;letter-spacing:.08em;text-transform:uppercase}}.next-game.live .next-kicker{{color:#e66777}}.next-game h3{{font-size:17px;margin:18px 0 8px}}.next-game h3 span{{color:#566475;font-weight:400}}.next-game p{{color:#6d7a8b;font-size:9px}}.next-score{{font-size:28px;font-weight:850}}.ghost{{display:inline-block;margin-top:8px;border:1px solid #314052;border-radius:8px;padding:7px 9px;color:#9aaabd;text-decoration:none;font-size:9px}}
.match-row{{display:grid;grid-template-columns:44px 30px 1fr auto;gap:9px;align-items:center;padding:10px 0;border-top:1px solid #202832}}.match-row:first-child{{border-top:0}}.match-row time{{font-size:9px;color:#687586}}.result-mark{{display:grid;place-items:center;width:26px;height:23px;border-radius:6px;font-size:7px;font-weight:850;border:1px solid #29333e}}.result-mark.win{{color:#9fcaae;border-color:#335844}}.result-mark.loss{{color:#d69ba2;border-color:#57363c}}.match-row b{{display:block;font-size:10px}}.match-row b strong{{color:#d8dfe7}}.match-row em{{display:block;color:#687586;font-size:8px;font-style:normal;margin-top:3px}}.match-row a{{color:#728499;text-decoration:none;font-size:8px}}
.side-stack{{display:grid;gap:14px;align-content:start}}.coach-note{{padding:10px 0;border-top:1px solid #202832}}.coach-note:first-of-type{{border-top:0}}.coach-note time{{display:block;color:#667484;font-size:8px}}.coach-note p{{margin:5px 0 0;color:#c1c9d3;font-size:10px;line-height:1.55}}.world-card{{border:1px solid #26313d;border-radius:13px;background:#090d12;padding:14px}}.world-card strong{{display:block;font-size:12px}}.world-card span{{display:block;color:#6f7d8e;font-size:9px;margin-top:5px;line-height:1.45}}.world-card.current{{border-left:2px solid var(--soyuz)}}.world-card.history{{border-left:2px solid #8c97a4}}.empty{{color:#6f7b8a;font-size:10px;padding:8px 0;line-height:1.5}}.footer-note{{display:flex;justify-content:space-between;gap:20px;margin-top:20px;padding-top:15px;border-top:1px solid #1e252e;color:#596575;font-size:9px;text-transform:uppercase;letter-spacing:.05em}}
@media(max-width:900px){{.env-grid{{grid-template-columns:1fr}}.team-stats{{grid-template-columns:1fr 1fr}}}}
@media(max-width:760px){{.env-hero{{grid-template-columns:1fr;padding-top:26px}}.env-hero h1{{font-size:40px}}.env-code{{text-align:left}}.team-head{{flex-direction:column}}.match-row{{grid-template-columns:38px 28px 1fr}}.match-row a{{grid-column:3}}.footer-note{{flex-direction:column}}}}
</style></head><body><main class="hub-shell">{topbar('mine')}
<section class="env-hero"><div><div class="hub-eyebrow">Мой хоккей · v0.50</div><h1>Моя хоккейная среда</h1><p>Тренер, команды и люди вокруг моего хоккея. Публичные результаты живут рядом с личными заметками, но сама эта страница остаётся закрытой.</p></div><div class="env-code"><b>PEOPLE / TEAMS / CONTEXT</b>личный хоккейный круг</div></section>
<nav class="mine-tabs"><a href="/my-hockey">Я</a><a class="active" href="/my-hockey/environment">Моя хоккейная среда</a><a href="/my-hockey/closet">Хоккейный шкаф</a><a href="/my-hockey#memory">Память</a></nav>
<section class="env-grid"><div>
<article class="coach-card"><div class="coach-kicker">Мой тренер</div><h2>Артём Кунаев</h2><div class="coach-role">тренер · главный тренер «Эскулапа»</div><p class="coach-copy">Здесь постепенно соберётся рабочий контекст вокруг тренировок: команды, актуальные матчи, тренерские рекомендации и история. Публичные факты о командах отделяем от моих личных заметок.</p><div class="coach-tags"><span>тренер</span><span>Эскулап</span><span>СПбХЛ</span></div></article>
<article class="hub-card team-card"><div class="team-head"><div><div class="hub-eyebrow">Текущая команда</div><h2>Эскулап</h2><p>СПбХЛ · данные из текущего официального источника</p></div><span class="team-badge">ПУБЛИЧНЫЕ ДАННЫЕ</span></div>
<div class="team-stats"><div class="mini-stat"><span>Сыграно</span><b>{played}</b></div><div class="mini-stat"><span>Баланс</span><b>{record}</b></div><div class="mini-stat"><span>Шайбы</span><b>{summary['gf']}:{summary['ga']}</b></div><div class="mini-stat"><span>Последний матч</span><b style="font-size:11px;line-height:1.35">{_esc(latest_text)}</b></div></div>
<div class="section-title"><h2>Форма</h2><span>последние матчи</span></div><div class="form-line">{_form_html(finished)}</div></article>
<article class="hub-card panel" style="margin-top:14px"><div class="section-title"><h2>Последние матчи Эскулапа</h2><span>5 последних</span></div>{_recent_games_html(finished)}</article>
</div><aside class="side-stack">
<article class="hub-card panel"><div class="section-title"><h2>Ближайший матч</h2><span>Эскулап</span></div>{_next_game_html(summary['current'])}</article>
<article class="hub-card panel"><div class="section-title"><h2>Мои заметки от тренера</h2><span>приватно</span></div>{_coach_notes_html()}</article>
<article class="hub-card panel"><div class="section-title"><h2>Команды в среде</h2><span>карта</span></div><div class="world-card current"><strong>Эскулап</strong><span>Текущая команда Тёмы. Live, результаты и календарь уже подключены.</span></div><div class="world-card history" style="margin-top:8px"><strong>Сборная врачей</strong><span>Историческая команда. Добавим сезоны и связи, когда соберём надёжные источники.</span></div></article>
</aside></section>
<footer class="footer-note"><span>Hockey Hub · Моя хоккейная среда</span><span>люди · команды · личный контекст</span></footer>
</main></body></html>'''


def patch_personal_page(saved: bool = False, error: str | None = None) -> str:
    page = _previous_personal_renderer(saved=saved, error=error)
    page = page.replace("Личный хоккей · v0.48.1", "Личный хоккей · v0.50", 1)
    page = page.replace('href="#tema">Тёма и команды</a>', 'href="/my-hockey/environment">Моя хоккейная среда</a>', 1)
    page = page.replace('<h3>Тёма и команды</h3>', '<h3><a href="/my-hockey/environment" style="text-decoration:none">Моя хоккейная среда →</a></h3>', 1)
    page = page.replace('Эскулап сейчас; другие команды и история тренера — следующим этапом.', 'Тренер, Эскулап, другие команды и личный контекст — в отдельном разделе.', 1)
    return page


def patch_closet_page(saved: str | None = None, error: str | None = None) -> str:
    page = _previous_closet_renderer(saved=saved, error=error)
    page = page.replace("Мой хоккей · v0.48.1", "Мой хоккей · v0.50", 1)
    page = page.replace('href="/my-hockey#tema">Тёма и команды</a>', 'href="/my-hockey/environment">Моя хоккейная среда</a>', 1)
    return page


personal_base.render_personal_page = patch_personal_page
closet_v48.render_closet = patch_closet_page


@core.app.get("/my-hockey/environment", response_class=__import__("fastapi.responses", fromlist=["HTMLResponse"]).HTMLResponse)
def hockey_environment():
    return render_environment()
