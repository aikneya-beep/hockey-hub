from __future__ import annotations

from datetime import datetime
import html

import app_v05 as core
import personal_hockey_v42 as base
from design_system_v46 import COMMON_CSS, topbar


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _next_eskulap() -> str:
    now = datetime.now(core.MOSCOW)
    with core.LOCK:
        games = [g for g in core.GAMES.values() if "Эскулап" in (g.home_team, g.away_team)]
    games.sort(key=lambda g: g.start_at)
    live = next((g for g in games if g.status == "live"), None)
    game = live or next((g for g in games if g.start_at >= now and g.status != "finished"), None)
    if not game:
        return '<div class="ecosystem-main">Ближайший матч пока не загружен</div>'
    opponent = game.away_team if game.home_team == "Эскулап" else game.home_team
    prefix = "LIVE" if game.status == "live" else game.start_at.strftime("%d.%m · %H:%M")
    score = ""
    if game.home_score is not None and game.away_score is not None:
        score = f'<strong class="esk-score">{game.home_score}:{game.away_score}</strong>'
    return (
        f'<div class="ecosystem-kicker">Эскулап · СПбХЛ</div>'
        f'<div class="ecosystem-main">{_esc(prefix)} · {_esc(opponent)} {score}</div>'
    )


def _latest_session(session: dict | None) -> str:
    if not session:
        return '<div class="empty">Пока нет записанных тренировок.</div>'
    focus = " · ".join(session.get("focus") or []) or "Фокус не указан"
    meta = []
    if session.get("wellbeing") is not None:
        meta.append(f"самочувствие {session['wellbeing']}/10")
    if session.get("load") is not None:
        meta.append(f"нагрузка {session['load']}/10")
    note = session.get("note") or "Заметки нет."
    homework = session.get("homework") or ""
    return f'''
      <div class="latest-date">{_esc(base._date_label(session.get('date', '')))}</div>
      <h3>{_esc(session.get('type') or 'Тренировка')}</h3>
      <div class="latest-focus">{_esc(focus)}</div>
      {f'<div class="latest-meta">{" · ".join(map(_esc, meta))}</div>' if meta else ''}
      <p>{_esc(note)}</p>
      {f'<div class="latest-homework"><span>ДЗ</span>{_esc(homework)}</div>' if homework else ''}
    '''


def render_personal_page_v46(saved: bool = False, error: str | None = None) -> str:
    data = base.STORE.load()
    profile = data.get("profile") or {}
    tests = data.get("tests") or []
    sessions = sorted(data.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
    notes = sorted(data.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    storage = data.get("storage") or base.STORE.status()
    db_ready = bool(storage.get("enabled")) and not storage.get("error")

    lap_tests = [t for t in tests if t.get("metric") == "Полный круг" and isinstance(t.get("seconds"), (int, float))]
    best = min((float(t["seconds"]) for t in lap_tests), default=None)
    latest_date = max((t.get("date", "") for t in lap_tests), default="")
    latest_laps = [float(t["seconds"]) for t in lap_tests if t.get("date") == latest_date]
    delta = abs(max(latest_laps) - min(latest_laps)) if len(latest_laps) >= 2 else None

    stat_best = f"{best:.2f}" if best is not None else "—"
    stat_delta = f"{delta:.2f}" if delta is not None else "—"
    today = datetime.now(core.MOSCOW).date().isoformat()
    disabled = "" if db_ready else " disabled"

    if saved:
        flash = '<div class="flash success">Тренировка сохранена · данные и график обновлены.</div>'
    elif error:
        flash = f'<div class="flash error">Не удалось сохранить: {_esc(error)}</div>'
    elif not db_ready:
        reason = _esc(storage.get("error") or "DATABASE_URL не подключён")
        flash = f'<div class="flash warn">PostgreSQL недоступен: {reason}</div>'
    else:
        flash = '<div class="flash ready"><span></span>PostgreSQL подключён · история сохраняется постоянно.</div>'

    session_rows = []
    for session in sessions[:8]:
        focus = " · ".join(session.get("focus") or []) or "—"
        session_rows.append(
            f'''<article class="history-row"><time>{_esc(base._date_label(session.get('date', '')))}</time><div><b>{_esc(session.get('type') or 'Тренировка')}</b><span>{_esc(focus)}</span></div><em>{_esc(str(session.get('load')) + '/10') if session.get('load') is not None else '—'}</em></article>'''
        )
    if not session_rows:
        session_rows.append('<div class="empty">История тренировок пока пуста.</div>')

    coach_rows = []
    for note in notes[:3]:
        coach_rows.append(
            f'''<article class="coach-row"><time>{_esc(base._date_label(note.get('date', '')))}</time><p>{_esc(note.get('text') or '')}</p></article>'''
        )
    if not coach_rows:
        coach_rows.append('<div class="empty">Новых заметок тренера пока нет.</div>')

    form_open = " open" if error else ""
    routine = _esc(profile.get("training_frequency") or "Режим пока не задан")
    shooting = _esc(profile.get("shooting_frequency") or "")

    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Мой хоккей · Hockey Hub</title><meta name="theme-color" content="#07090c"><style>
{COMMON_CSS}
body{{background:radial-gradient(circle at 82% 6%,rgba(65,111,159,.08),transparent 25%),linear-gradient(180deg,#07090c,#080b0f 58%,#07090c)}}
.mine-hero{{display:grid;grid-template-columns:1fr auto;gap:26px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}
.mine-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.mine-hero p{{margin:0;color:#939eae;font-size:16px}}.routine{{text-align:right;color:#7e8999;font-size:11px;line-height:1.65}}.routine b{{display:block;color:#d6dce4;font-size:13px}}
.mine-tabs{{display:flex;gap:8px;margin:18px 0 0;overflow:auto}}.mine-tabs a{{text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}}.mine-tabs a.active{{color:#f2f5f8;border-color:#7e8996;background:linear-gradient(180deg,#1a2028,#10151c);box-shadow:inset 0 1px rgba(255,255,255,.04)}}
.flash{{margin:18px 0 0;padding:11px 13px;border:1px solid #2a333f;border-radius:11px;background:#10151c;color:#aeb7c4;font-size:11px}}.flash.ready span{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#8eb89a;margin-right:8px}}.flash.success{{border-color:#365541;color:#bcd5c3}}.flash.warn{{border-color:#5c4b2e;color:#d9c293}}.flash.error{{border-color:#61363d;color:#efb4ba}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}}.stat{{min-height:112px;padding:16px;background:linear-gradient(180deg,#11161c,#0b0f14);border:1px solid #242c36;border-radius:15px}}.stat span{{display:block;color:#748091;font-size:10px;text-transform:uppercase;letter-spacing:.08em}}.stat strong{{display:block;color:#f1f4f7;font-size:31px;line-height:1;margin-top:13px;font-variant-numeric:tabular-nums}}.stat strong small{{font-size:13px;color:#8994a3}}.stat em{{display:block;color:#6f7a8a;font-size:10px;font-style:normal;margin-top:9px}}
.progress-grid{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.65fr);gap:14px}}.panel{{padding:17px}}.chart-wrap{{min-height:330px}}.chart-wrap .chart{{overflow:hidden}}.chart-wrap svg{{width:100%;height:auto;display:block}}.gridline{{stroke:#222a34;stroke-width:1}}.axis{{fill:#6e7989;font-size:10px}}.line{{fill:none;stroke:#5b8fc9;stroke-width:2.2}}.point{{fill:#d3d9e1;stroke:#0b0f14;stroke-width:2}}.value{{fill:#edf1f5;font-size:10px;font-weight:750}}.chart-foot{{display:flex;justify-content:space-between;gap:14px;color:#6f7a8a;font-size:10px;border-top:1px solid #202732;padding-top:10px}}
.side-stack{{display:grid;gap:14px}}.latest h3{{font-size:19px;margin:6px 0}}.latest-date{{color:#707c8c;font-size:10px}}.latest-focus{{color:#c8d0da;font-size:12px}}.latest-meta{{color:#7290b0;font-size:10px;margin-top:8px}}.latest p{{color:#909aaa;font-size:11px;line-height:1.55;margin:12px 0 0}}.latest-homework{{margin-top:12px;border-top:1px solid #252c35;padding-top:10px;color:#aab4c0;font-size:10px;line-height:1.45}}.latest-homework span{{display:inline-block;margin-right:7px;padding:2px 5px;border:1px solid #3c4a5c;border-radius:5px;color:#9db4cf;font-size:8px}}
.coach-row{{padding:10px 0;border-top:1px solid #212832}}.coach-row:first-of-type{{border-top:0}}.coach-row time{{display:block;color:#687484;font-size:9px}}.coach-row p{{margin:5px 0 0;color:#c9d0d9;font-size:11px;line-height:1.5}}
.training-form{{margin-top:14px}}details.add-session{{border:1px solid #29323d;border-radius:15px;background:#0c1015;overflow:hidden}}details.add-session summary{{cursor:pointer;list-style:none;padding:15px 17px;font-size:12px;font-weight:750;color:#dce2e9}}details.add-session summary::-webkit-details-marker{{display:none}}details.add-session summary:after{{content:"＋";float:right;color:#718094}}details.add-session[open] summary:after{{content:"−"}}.form-body{{padding:0 17px 17px;border-top:1px solid #202731}}form{{display:grid;gap:11px;padding-top:14px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}label{{display:grid;gap:6px;color:#95a0af;font-size:10px}}input,textarea,select{{width:100%;border:1px solid #303946;border-radius:9px;background:#090d12;color:#eef2f6;padding:10px 11px}}textarea{{min-height:72px;resize:vertical}}button.save{{border:1px solid #808995;border-radius:10px;padding:11px 14px;background:linear-gradient(180deg,#d8dde3,#b9c1ca);color:#0b0e12;font-weight:850;cursor:pointer}}button.save:disabled,input:disabled,textarea:disabled,select:disabled{{opacity:.4;cursor:not-allowed}}.form-note{{font-size:9px;color:#687484;line-height:1.5}}
.bottom-grid{{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;margin-top:14px}}.history-row{{display:grid;grid-template-columns:82px 1fr auto;gap:11px;align-items:start;padding:11px 0;border-top:1px solid #212832}}.history-row:first-of-type{{border-top:0}}.history-row time{{color:#6d7888;font-size:9px}}.history-row b{{display:block;font-size:11px}}.history-row span{{display:block;color:#818c9c;font-size:9px;margin-top:3px}}.history-row em{{font-style:normal;color:#6e88a6;font-size:9px}}
.ecosystem{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.ecosystem-card{{min-height:134px;padding:14px;background:#0b0f14;border:1px solid #252d37;border-radius:13px;position:relative;overflow:hidden}}.ecosystem-card:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:linear-gradient(#c8d0da,#416f9f)}}.ecosystem-card span.badge{{display:inline-block;color:#718095;border:1px solid #303a47;border-radius:999px;padding:3px 7px;font-size:8px;margin-bottom:12px}}.ecosystem-card h3{{font-size:13px;margin:0 0 8px}}.ecosystem-card p{{margin:0;color:#778394;font-size:10px;line-height:1.5}}.ecosystem-kicker{{color:#728196;font-size:9px;text-transform:uppercase;letter-spacing:.06em}}.ecosystem-main{{font-size:11px;color:#cbd2db;margin-top:6px;line-height:1.45}}.esk-score{{color:#dce3ea;margin-left:5px}}.empty{{color:#737e8d;font-size:10px;padding:8px 0}}
.footer-note{{display:flex;justify-content:space-between;gap:20px;margin-top:20px;padding-top:15px;border-top:1px solid #1e252e;color:#596575;font-size:9px;text-transform:uppercase;letter-spacing:.05em}}
@media(max-width:900px){{.progress-grid,.bottom-grid{{grid-template-columns:1fr}}.ecosystem{{grid-template-columns:1fr 1fr}}}}
@media(max-width:760px){{.mine-hero{{grid-template-columns:1fr;padding-top:26px}}.mine-hero h1{{font-size:42px}}.routine{{text-align:left}}.stats{{grid-template-columns:1fr 1fr}}.stats .stat:last-child{{grid-column:1/-1}}.chart-foot{{flex-direction:column}}.two{{grid-template-columns:1fr}}.ecosystem{{grid-template-columns:1fr}}.footer-note{{flex-direction:column}}}}
</style></head><body><main class="hub-shell">{topbar('mine')}
<section class="mine-hero"><div><div class="hub-eyebrow">Личный хоккей · v0.46</div><h1>Мой хоккей</h1><p>Развитие игрока, люди вокруг, вещи и память — в одном личном пространстве.</p></div><div class="routine"><b>{routine}</b>{shooting}</div></section>
<nav class="mine-tabs"><a class="active" href="#me">Я</a><a href="#tema">Тёма и команды</a><a href="#closet">Хоккейный шкаф</a><a href="#memory">Память</a></nav>
{flash}
<section class="stats" id="me"><article class="stat"><span>Лучший круг</span><strong>{stat_best} <small>с</small></strong><em>{_esc(profile.get('rink') or '60×30 м')} · старт с места</em></article><article class="stat"><span>Разница направлений</span><strong>{stat_delta} <small>с</small></strong><em>последний парный замер</em></article><article class="stat"><span>Тренировок в истории</span><strong>{len(sessions)}</strong><em>записано в PostgreSQL</em></article></section>
<section class="progress-grid"><article class="hub-card panel chart-wrap"><div class="hub-section-head"><h2>Динамика полного круга</h2><span class="hub-eyebrow">меньше = быстрее</span></div>{base._progress_svg(tests)}</article><aside class="side-stack"><article class="hub-card panel latest"><div class="hub-section-head"><h2>Последняя тренировка</h2><span></span></div>{_latest_session(sessions[0] if sessions else None)}</article><article class="hub-card panel"><div class="hub-section-head"><h2>Фокус от тренера</h2><span></span></div>{''.join(coach_rows)}</article></aside></section>
<section class="training-form"><details class="add-session"{form_open}><summary>Добавить тренировку</summary><div class="form-body"><form method="post" action="/my-hockey/session"><div class="two"><label>Дата<input type="date" name="session_date" value="{today}" required{disabled}></label><label>Тип<select name="session_type"{disabled}><option>Ледовая тренировка</option><option>Бросковая тренировка</option><option>Игра</option><option>ОФП / вне льда</option><option>Самостоятельная</option></select></label></div><label>Что тренировали<input name="focus" placeholder="катание, скорость, бросок"{disabled}></label><div class="two"><label>Самочувствие 1–10<input type="number" min="1" max="10" name="wellbeing"{disabled}></label><label>Нагрузка 1–10<input type="number" min="1" max="10" name="load"{disabled}></label></div><label>Моя заметка<textarea name="note" placeholder="Что получилось, что не получилось"{disabled}></textarea></label><label>Домашнее задание<textarea name="homework" placeholder="Что сделать до следующей тренировки"{disabled}></textarea></label><label>Комментарий тренера<textarea name="coach_note" placeholder="Если был новый фидбек"{disabled}></textarea></label><div class="two"><label>Круг, направление 1<input inputmode="decimal" name="lap_1" placeholder="24,50"{disabled}></label><label>Круг, направление 2<input inputmode="decimal" name="lap_2" placeholder="24,65"{disabled}></label></div><button class="save" type="submit"{disabled}>Сохранить тренировку</button><div class="form-note">Время круга необязательно. Если заполнить — замер автоматически попадёт на график.</div></form></div></details></section>
<section class="bottom-grid"><article class="hub-card panel"><div class="hub-section-head"><h2>История тренировок</h2><span class="hub-eyebrow">последние 8</span></div>{''.join(session_rows)}</article><article class="hub-card panel"><div class="hub-section-head"><h2>Следующие миры</h2><span></span></div><div class="ecosystem"><article class="ecosystem-card" id="tema"><span class="badge">УЖЕ ЕСТЬ ДАННЫЕ</span><h3>Тёма и команды</h3>{_next_eskulap()}<p style="margin-top:10px">Эскулап сейчас; другие команды и история тренера — следующим этапом.</p></article><article class="ecosystem-card" id="closet"><span class="badge">СЛЕДУЮЩИЙ ЭТАП</span><h3>Хоккейный шкаф</h3><p>Экипировка, обслуживание, спортпит, атрибутика, wishlist и мониторинг цен.</p></article><article class="ecosystem-card" id="memory"><span class="badge">СЛЕДУЮЩИЙ ЭТАП</span><h3>Память</h3><p>Посещённые матчи, билеты, фото, заметки, впечатления и сезонные итоги.</p></article></div></article></section>
<footer class="footer-note"><span>Hockey Hub · Мой хоккей</span><span>чёрный · серебро · холодный синий</span></footer>
</main></body></html>'''
    return page


base.render_personal_page = render_personal_page_v46
