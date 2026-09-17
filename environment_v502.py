from __future__ import annotations

from datetime import datetime
import html

import app_v05 as core
import environment_v50 as env
import personal_hockey_v42 as personal_base
from design_system_v46 import COMMON_CSS, topbar


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _result(game) -> tuple[str, str]:
    if game.home_score is None or game.away_score is None:
        return "—", "neutral"
    home = game.home_team == "Эскулап"
    gf = game.home_score if home else game.away_score
    ga = game.away_score if home else game.home_score
    if gf > ga:
        return "В", "win"
    if gf < ga:
        return "П", "loss"
    return "Н", "draw"


def _opponent(game) -> str:
    return game.away_team if game.home_team == "Эскулап" else game.home_team


def _personal_data() -> tuple[list[dict], list[dict]]:
    try:
        data = personal_base.STORE.load()
        sessions = sorted(data.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
        notes = sorted(data.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
        return sessions, notes
    except Exception:
        return [], []


def _date_label(raw: str | None) -> str:
    try:
        return datetime.strptime(str(raw or ""), "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(raw or "")


def _coach_context(sessions: list[dict], notes: list[dict]) -> str:
    if notes:
        latest = notes[0]
        focus = _esc(latest.get("text") or "")
        focus_date = _esc(_date_label(latest.get("date")))
    else:
        focus = "Новый комментарий тренера появится здесь после тренировки."
        focus_date = ""
    return f'''<div class="coach-context">
      <div class="focus-cell"><span>Текущий фокус</span><b>{focus}</b>{f'<em>{focus_date}</em>' if focus_date else ''}</div>
      <div><span>Тренировок в истории</span><strong>{len(sessions)}</strong><em>личная история</em></div>
      <div><span>Комментариев тренера</span><strong>{len(notes)}</strong><em>сохранено</em></div>
    </div>'''


def _coach_notes(notes: list[dict]) -> str:
    if not notes:
        return '<div class="empty">Отдельных комментариев тренера пока нет.</div>'
    rows = []
    for note in notes[:5]:
        rows.append(
            f'''<article class="coach-note"><time>{_esc(_date_label(note.get('date')))}</time><p>{_esc(note.get('text') or '')}</p></article>'''
        )
    return "".join(rows)


def _form(finished) -> str:
    if not finished:
        return '<div class="empty">Результаты пока не загружены.</div>'
    chips = []
    for game in finished[-8:]:
        label, cls = _result(game)
        chips.append(f'<span class="form-chip {cls}" title="{game.start_at.strftime("%d.%m")} · {_esc(_opponent(game))}">{label}</span>')
    return "".join(chips)


def _recent(finished) -> str:
    if not finished:
        return '<div class="empty">Матчей пока нет.</div>'
    rows = []
    for game in reversed(finished[-3:]):
        label, cls = _result(game)
        source_url = getattr(game, "source_url", None)
        source = (
            f'<a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">источник ↗</a>'
            if source_url else ""
        )
        arena = getattr(game, "arena", None) or "СПбХЛ"
        rows.append(f'''<article class="match-row">
          <time>{game.start_at.strftime('%d.%m')}</time>
          <span class="result-mark {cls}">{label}</span>
          <div><b>{_esc(game.home_team)} <strong>{game.home_score}:{game.away_score}</strong> {_esc(game.away_team)}</b><em>{_esc(arena)}</em></div>
          {source}
        </article>''')
    return "".join(rows)


def _next_game(game) -> str:
    if not game:
        return '<div class="empty compact">Следующий матч пока не появился в источнике.</div>'
    live = game.status == "live"
    score = ""
    if game.home_score is not None and game.away_score is not None:
        score = f'<strong class="next-score">{game.home_score}:{game.away_score}</strong>'
    source_url = getattr(game, "source_url", None)
    source = (
        f'<a class="ghost" href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">источник ↗</a>'
        if source_url else ""
    )
    arena = getattr(game, "arena", None) or "Арена пока не указана"
    kicker = "LIVE" if live else game.start_at.strftime("%d.%m.%Y · %H:%M")
    return f'''<div class="next-game{' live' if live else ''}"><div class="next-kicker">{kicker}</div><h3>{_esc(game.home_team)} <span>—</span> {_esc(game.away_team)}</h3>{score}<p>{_esc(arena)}</p>{source}</div>'''


def render_environment_v502() -> str:
    games = env._eskulap_games()
    summary = env._eskulap_summary(games)
    finished = summary["finished"]
    sessions, notes = _personal_data()
    played = len(finished)
    record = f'{summary["wins"]}–{summary["losses"]}' + (f'–{summary["draws"]}' if summary["draws"] else '')

    css = r'''
:root{--soyuz:#2a86d9;--soyuz-dim:#365c7d;--silver:#c8d0da}
body{background:radial-gradient(circle at 80% 2%,rgba(42,134,217,.10),transparent 24%),linear-gradient(180deg,#05070b,#080b0f 58%,#05070b)}
.env-hero{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}
.env-hero h1{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}.env-hero p{margin:0;color:#929dac;max-width:720px;font-size:15px;line-height:1.55}.env-code{text-align:right;color:#708094;font-size:9px;letter-spacing:.12em;text-transform:uppercase}.env-code b{display:block;color:#d8dee6;font-size:13px;letter-spacing:.04em;margin-bottom:4px}
.mine-tabs{display:flex;gap:8px;margin:18px 0;overflow:auto}.mine-tabs a{position:relative;text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}.mine-tabs a.active{color:#f2f5f8;border-color:#53616f;background:linear-gradient(180deg,#161c23,#0e1319)}.mine-tabs a.active:after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--soyuz);box-shadow:0 0 10px rgba(42,134,217,.3)}
.coach-card{position:relative;overflow:hidden;margin-bottom:14px;background:radial-gradient(circle at 90% 10%,rgba(42,134,217,.11),transparent 35%),linear-gradient(145deg,#11171f,#090d12);border:1px solid #28323e;border-radius:16px;padding:20px 22px}.coach-card:before{content:"";position:absolute;left:22px;top:0;width:56px;height:2px;background:linear-gradient(90deg,var(--soyuz),var(--soyuz-dim))}.coach-kicker{color:#6f8297;font-size:9px;text-transform:uppercase;letter-spacing:.12em}.coach-card h2{font-size:29px;margin:10px 0 4px}.coach-role{color:#c6ced8;font-size:11px}.coach-copy{max-width:820px;color:#8995a5;font-size:10px;line-height:1.55;margin:12px 0 0}.coach-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.coach-tags span{border:1px solid #2d3946;background:#0b1118;border-radius:999px;padding:4px 8px;color:#8494a6;font-size:8px;text-transform:uppercase;letter-spacing:.06em}
.coach-context{display:grid;grid-template-columns:minmax(0,1.8fr) .6fr .6fr;gap:8px;margin-top:15px}.coach-context>div{border:1px solid #26313c;background:#090d12;border-radius:11px;padding:10px 12px;min-height:69px}.coach-context span{display:block;color:#667587;font-size:8px;text-transform:uppercase;letter-spacing:.08em}.coach-context b{display:block;color:#cbd2db;font-size:10px;line-height:1.42;margin-top:6px;font-weight:650}.coach-context strong{display:block;font-size:20px;margin-top:6px}.coach-context em{display:block;color:#617080;font-size:8px;font-style:normal;margin-top:4px}
.env-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr);gap:14px;align-items:start}.panel,.team-card{padding:18px}.team-card{margin:0}.section-title{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:14px}.section-title h2{margin:0;font-size:15px}.section-title span{color:#6f7d8d;font-size:9px;text-transform:uppercase;letter-spacing:.12em}.team-head{display:flex;justify-content:space-between;gap:18px;align-items:start}.team-head h2{font-size:24px;margin:3px 0}.team-head p{color:#738194;font-size:10px;margin:0}.team-badge{border:1px solid #31506c;border-radius:999px;padding:5px 8px;color:#8eb4d8;font-size:8px;white-space:nowrap}.team-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:17px 0}.mini-stat{position:relative;overflow:hidden;border:1px solid #232d38;background:#090d12;border-radius:12px;padding:12px;min-height:82px}.mini-stat:before{content:"";position:absolute;left:12px;top:0;width:28px;height:2px;background:var(--soyuz);opacity:.65}.mini-stat span{display:block;color:#697687;font-size:8px;text-transform:uppercase;letter-spacing:.08em}.mini-stat b{display:block;font-size:20px;margin-top:10px}
.form-line{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.form-chip{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;font-size:8px;font-weight:850;border:1px solid #2a333d;background:#10151b;color:#9aa5b2}.form-chip.win,.result-mark.win{border-color:#335844;color:#9fcaae}.form-chip.loss,.result-mark.loss{border-color:#57363c;color:#d69ba2}.form-chip.draw,.result-mark.draw{border-color:#5b5238;color:#cfbd8e}
.recent-card{margin-top:14px}.match-row{display:grid;grid-template-columns:44px 30px 1fr auto;gap:9px;align-items:center;padding:9px 0;border-top:1px solid #202832}.match-row:first-of-type{border-top:0}.match-row time{font-size:9px;color:#687586}.result-mark{display:grid;place-items:center;width:26px;height:23px;border-radius:6px;font-size:7px;font-weight:850;border:1px solid #29333e}.match-row b{display:block;font-size:10px}.match-row b strong{color:#d8dfe7}.match-row em{display:block;color:#687586;font-size:8px;font-style:normal;margin-top:3px}.match-row a{color:#728499;text-decoration:none;font-size:8px}
.side-stack{display:grid;gap:14px;align-content:start}.coach-note{padding:9px 0;border-top:1px solid #202832}.coach-note:first-of-type{border-top:0}.coach-note time{display:block;color:#667484;font-size:8px}.coach-note p{margin:5px 0 0;color:#c1c9d3;font-size:10px;line-height:1.5}.world-card{border:1px solid #26313d;border-radius:13px;background:#090d12;padding:13px}.world-card strong{display:block;font-size:12px}.world-card span{display:block;color:#6f7d8e;font-size:9px;margin-top:5px;line-height:1.45}.world-card.current{border-left:2px solid var(--soyuz)}.world-card.history{border-left:2px solid #8c97a4}.next-panel{padding:14px 16px}.next-panel .section-title{margin-bottom:8px}.next-game{border:1px solid #263443;background:#090e14;border-radius:11px;padding:10px 12px}.next-game.live{border-color:#743845}.next-kicker{color:#7790aa;font-size:8px;letter-spacing:.08em;text-transform:uppercase}.next-game.live .next-kicker{color:#e66777}.next-game h3{font-size:14px;margin:8px 0 4px}.next-game h3 span{color:#566475;font-weight:400}.next-game p{color:#6d7a8b;font-size:8px;margin:5px 0}.next-score{font-size:19px}.ghost{display:inline-block;margin-top:5px;color:#8293a7;text-decoration:none;font-size:8px}.empty{color:#6f7b8a;font-size:10px;padding:8px 0;line-height:1.5}.empty.compact{padding:2px 0}.footer-note{display:flex;justify-content:space-between;gap:20px;margin-top:20px;padding-top:15px;border-top:1px solid #1e252e;color:#596575;font-size:9px;text-transform:uppercase;letter-spacing:.05em}
@media(max-width:900px){.env-grid{grid-template-columns:1fr}.coach-context{grid-template-columns:1fr 1fr}.coach-context .focus-cell{grid-column:1/-1}}
@media(max-width:760px){.env-hero{grid-template-columns:1fr;padding-top:26px}.env-hero h1{font-size:40px}.env-code{text-align:left}.team-head{flex-direction:column}.match-row{grid-template-columns:38px 28px 1fr}.match-row a{grid-column:3}.footer-note{flex-direction:column}}
@media(max-width:620px){.coach-context,.team-stats{grid-template-columns:1fr}.coach-context .focus-cell{grid-column:auto}}
'''

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Моя хоккейная среда · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>{COMMON_CSS}{css}</style></head><body><main class="hub-shell">{topbar('mine')}
<section class="env-hero"><div><div class="hub-eyebrow">Мой хоккей · v0.50.2</div><h1>Моя хоккейная среда</h1><p>Тренер, команды и люди вокруг моего хоккея. Публичные результаты рядом с личными заметками — внутри закрытого раздела.</p></div><div class="env-code"><b>PEOPLE / TEAMS / CONTEXT</b>личный хоккейный круг</div></section>
<nav class="mine-tabs"><a href="/my-hockey">Я</a><a class="active" href="/my-hockey/environment">Моя хоккейная среда</a><a href="/my-hockey/closet">Хоккейный шкаф</a><a href="/my-hockey#memory">Память</a></nav>
<article class="coach-card"><div class="coach-kicker">Мой тренер</div><h2>Артём Кунаев</h2><div class="coach-role">тренер · главный тренер «Эскулапа»</div><p class="coach-copy">Рабочий контекст вокруг моих тренировок: актуальный фокус, рекомендации, команды и история. Публичные факты о командах отделены от личных заметок.</p>{_coach_context(sessions, notes)}<div class="coach-tags"><span>тренер</span><span>Эскулап</span><span>СПбХЛ</span></div></article>
<section class="env-grid"><div>
<article class="hub-card team-card"><div class="team-head"><div><div class="hub-eyebrow">Текущая команда</div><h2>Эскулап</h2><p>СПбХЛ · данные из текущего официального источника</p></div><span class="team-badge">ПУБЛИЧНЫЕ ДАННЫЕ</span></div><div class="team-stats"><div class="mini-stat"><span>Сыграно</span><b>{played}</b></div><div class="mini-stat"><span>Баланс</span><b>{record}</b></div><div class="mini-stat"><span>Шайбы</span><b>{summary['gf']}:{summary['ga']}</b></div></div><div class="section-title"><h2>Форма</h2><span>последние матчи</span></div><div class="form-line">{_form(finished)}</div></article>
<article class="hub-card panel recent-card"><div class="section-title"><h2>Последние матчи Эскулапа</h2><span>3 последних</span></div>{_recent(finished)}</article>
</div><aside class="side-stack">
<article class="hub-card panel"><div class="section-title"><h2>Мои заметки от тренера</h2><span>приватно</span></div>{_coach_notes(notes)}</article>
<article class="hub-card panel"><div class="section-title"><h2>Команды в среде</h2><span>карта</span></div><div class="world-card current"><strong>Эскулап</strong><span>Текущая команда Тёмы. Live, результаты и календарь уже подключены.</span></div><div class="world-card history" style="margin-top:8px"><strong>Сборная врачей</strong><span>Историческая команда. Добавим сезоны и связи, когда соберём надёжные источники.</span></div></article>
<article class="hub-card next-panel"><div class="section-title"><h2>Ближайший матч</h2><span>Эскулап</span></div>{_next_game(summary['current'])}</article>
</aside></section>
<footer class="footer-note"><span>Hockey Hub · Моя хоккейная среда</span><span>люди · команды · личный контекст</span></footer></main></body></html>'''


env.render_environment = render_environment_v502
