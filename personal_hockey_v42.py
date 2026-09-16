from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import html

from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v05 as core
from personal_hockey_store_v42 import PersonalHockeyStore

STORE = PersonalHockeyStore()


def _date_label(raw: str) -> str:
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(raw or "")


def _progress_svg(tests: list[dict]) -> str:
    rows = [t for t in tests if t.get("metric") == "Полный круг" and isinstance(t.get("seconds"), (int, float))]
    if not rows:
        return '<div class="empty">Пока нет замеров для графика.</div>'
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    directions: list[str] = []
    for row in sorted(rows, key=lambda x: (x.get("date", ""), x.get("direction", ""))):
        day = row.get("date", "")
        direction = row.get("direction") or "Круг"
        grouped[day][direction] = float(row["seconds"])
        if direction not in directions:
            directions.append(direction)
    dates = sorted(grouped)
    values = [v for day in grouped.values() for v in day.values()]
    low, high = min(values) - 0.25, max(values) + 0.25
    if high - low < 0.8:
        mid = (high + low) / 2
        low, high = mid - 0.4, mid + 0.4
    width, height = 720, 250
    left, right, top, bottom = 55, 22, 22, 48
    plot_w, plot_h = width - left - right, height - top - bottom

    def xp(i: int) -> float:
        return left + plot_w / 2 if len(dates) == 1 else left + i * plot_w / (len(dates) - 1)

    def yp(value: float) -> float:
        return top + (value - low) * plot_h / (high - low)

    grid = []
    for i in range(4):
        val = low + i * (high - low) / 3
        y = yp(val)
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="gridline"/>')
        grid.append(f'<text x="{left-8}" y="{y+4:.1f}" class="axis" text-anchor="end">{val:.1f}</text>')
    labels = [
        f'<text x="{xp(i):.1f}" y="{height-18}" class="axis" text-anchor="middle">{html.escape(_date_label(day)[:5])}</text>'
        for i, day in enumerate(dates)
    ]
    series = []
    for direction in directions:
        points = []
        circles = []
        for i, day in enumerate(dates):
            value = grouped[day].get(direction)
            if value is None:
                continue
            x, y = xp(i), yp(value)
            points.append(f"{x:.1f},{y:.1f}")
            circles.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="point"/>'
                f'<text x="{x:.1f}" y="{y-10:.1f}" class="value" text-anchor="middle">{value:.2f}</text>'
            )
        if len(points) > 1:
            series.append(f'<polyline points="{" ".join(points)}" class="line"/>')
        series.extend(circles)
    hint = "Стартовая точка. После второго замера появится линия динамики." if len(dates) == 1 else "Меньше — быстрее. Сравнивай одинаковый протокол теста."
    return f'''<div class="chart"><svg viewBox="0 0 {width} {height}" role="img" aria-label="Динамика времени полного круга">{''.join(grid)}{''.join(labels)}{''.join(series)}<text x="12" y="16" class="axis">сек.</text></svg><div class="chart-foot"><span>{' · '.join(map(html.escape, directions))}</span><span>{hint}</span></div></div>'''


def _num(value: str | None) -> float | None:
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    number = float(text)
    if number <= 0 or number > 300:
        raise ValueError("некорректное время круга")
    return number


def render_personal_page(saved: bool = False, error: str | None = None) -> str:
    data = STORE.load()
    profile = data.get("profile") or {}
    tests = data.get("tests") or []
    sessions = sorted(data.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
    notes = sorted(data.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    storage = data.get("storage") or STORE.status()
    db_ready = bool(storage.get("enabled")) and not storage.get("error")

    lap_tests = [t for t in tests if t.get("metric") == "Полный круг" and isinstance(t.get("seconds"), (int, float))]
    best = min((float(t["seconds"]) for t in lap_tests), default=None)
    latest_date = max((t.get("date", "") for t in lap_tests), default="")
    latest = [float(t["seconds"]) for t in lap_tests if t.get("date") == latest_date]
    delta = abs(max(latest) - min(latest)) if len(latest) >= 2 else None

    session_html = []
    for session in sessions:
        focus = " · ".join(session.get("focus") or [])
        scores = []
        if session.get("wellbeing") is not None:
            scores.append(f"самочувствие {session['wellbeing']}/10")
        if session.get("load") is not None:
            scores.append(f"нагрузка {session['load']}/10")
        extra = " · ".join(scores)
        homework = session.get("homework") or ""
        session_html.append(
            f'''<article class="timeline-item"><div class="date">{html.escape(_date_label(session.get('date', '')))}</div><div><b>{html.escape(session.get('type') or 'Тренировка')}</b><span>{html.escape(focus)}</span>{f'<small>{html.escape(extra)}</small>' if extra else ''}<p>{html.escape(session.get('note') or '')}</p>{f'<div class="homework">ДЗ: {html.escape(homework)}</div>' if homework else ''}</div></article>'''
        )
    if not session_html:
        session_html.append('<div class="empty">История тренировок пока пуста.</div>')

    notes_html = [
        f'''<article class="coach-note"><span>{html.escape(_date_label(note.get('date', '')))}</span><p>{html.escape(note.get('text') or '')}</p></article>'''
        for note in notes
    ] or ['<div class="empty">Заметок тренера пока нет.</div>']

    if saved:
        flash = '<div class="flash good">Тренировка сохранена. История и график уже обновлены.</div>'
    elif error:
        flash = f'<div class="flash bad">Не удалось сохранить: {html.escape(error)}</div>'
    elif not db_ready:
        reason = html.escape(storage.get("error") or "DATABASE_URL пока не подключён к веб-сервису")
        flash = f'<div class="flash warn"><b>Форма пока в режиме ожидания.</b> PostgreSQL создан, но веб-сервис ещё не получил подключение к нему. {reason}.</div>'
    else:
        flash = '<div class="flash ready">PostgreSQL подключён · новые тренировки сохраняются постоянно.</div>'

    disabled = "" if db_ready else " disabled"
    today = datetime.now(core.MOSCOW).date().isoformat()
    stat_best = f"{best:.2f} с" if best is not None else "—"
    stat_delta = f"{delta:.2f} с" if delta is not None else "—"

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Мой хоккей · Личный прогресс</title><meta name="theme-color" content="#0b0d11"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}a{{color:inherit}}.wrap{{max-width:1040px;margin:auto;padding:28px 20px 80px}}.back{{color:#96a0b0;text-decoration:none;font-size:13px}}header{{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:end;border-bottom:1px solid #262b35;padding:18px 0 24px}}.eyebrow{{font-size:11px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:44px;line-height:1;margin:7px 0}}header p{{margin:0;color:#98a3b3;max-width:650px}}.routine{{text-align:right;color:#8e99aa;font-size:12px;line-height:1.6}}.routine b{{display:block;color:#dce2eb;font-size:13px}}.flash{{margin:18px 0;padding:11px 13px;border-radius:10px;font-size:12px;line-height:1.45;border:1px solid #2a3340;background:#141923}}.flash.good,.flash.ready{{border-color:#31563b;color:#bde0c4}}.flash.warn{{border-color:#5d4b27;color:#dec58d}}.flash.bad{{border-color:#66383e;color:#efb0b6}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0 14px}}.stat,.card{{background:#12161d;border:1px solid #252a33;border-radius:14px}}.stat{{padding:15px}}.stat span{{display:block;color:#7f8999;font-size:10px;text-transform:uppercase;letter-spacing:.06em}}.stat strong{{display:block;font-size:28px;margin-top:7px;font-variant-numeric:tabular-nums}}.stat small{{display:block;color:#818c9c;margin-top:4px;font-size:11px}}.layout{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(310px,.75fr);gap:14px}}.card{{padding:16px}}h2{{font-size:12px;color:#9aa5b5;text-transform:uppercase;letter-spacing:.075em;margin:0 0 14px}}.chart{{overflow:hidden}}svg{{width:100%;height:auto;display:block}}.gridline{{stroke:#242b36;stroke-width:1}}.axis{{fill:#737f90;font-size:10px}}.line{{fill:none;stroke:#dfe5ee;stroke-width:2}}.point{{fill:#dfe5ee;stroke:#0b0d11;stroke-width:2}}.value{{fill:#eef2f7;font-size:10px;font-weight:750}}.chart-foot{{display:flex;justify-content:space-between;gap:14px;color:#778394;font-size:10px;border-top:1px solid #232a34;padding-top:9px}}.coach-note{{border-left:3px solid #6079a7;padding:3px 0 3px 12px;margin-bottom:12px}}.coach-note span{{color:#768294;font-size:10px}}.coach-note p{{margin:6px 0 0;color:#e2e6ec;font-size:14px;line-height:1.5}}.section{{margin-top:14px}}.timeline-item{{display:grid;grid-template-columns:100px 1fr;gap:14px;padding:12px 0;border-bottom:1px solid #252a33}}.timeline-item:last-child{{border-bottom:0}}.timeline-item .date{{color:#7d8898;font-size:11px;padding-top:2px}}.timeline-item b{{font-size:14px}}.timeline-item span,.timeline-item small{{display:block;color:#8994a4;font-size:11px;margin-top:3px}}.timeline-item p{{margin:6px 0 0;color:#b2bbc8;font-size:12px;line-height:1.45}}.homework{{margin-top:7px;color:#b8c6db;font-size:11px}}form{{display:grid;gap:12px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}label{{display:grid;gap:6px;color:#aab4c3;font-size:11px}}input,textarea,select{{width:100%;border:1px solid #303846;border-radius:9px;background:#0e1218;color:#f5f7fa;padding:10px 11px;font:inherit}}textarea{{min-height:74px;resize:vertical}}input:disabled,textarea:disabled,select:disabled{{opacity:.45}}button{{border:0;border-radius:10px;padding:12px 14px;background:#e8edf4;color:#10141a;font-weight:800;cursor:pointer}}button:disabled{{opacity:.35;cursor:not-allowed}}.form-note{{color:#6f7b8c;font-size:10px;line-height:1.45}}.empty{{color:#7d8796;font-size:12px;padding:10px 0}}@media(max-width:760px){{.wrap{{padding:20px 14px 60px}}header{{grid-template-columns:1fr}}.routine{{text-align:left}}h1{{font-size:37px}}.stats,.layout,.two{{grid-template-columns:1fr}}.chart-foot{{flex-direction:column}}.timeline-item{{grid-template-columns:82px 1fr}}}}
</style></head><body><main class="wrap"><a class="back" href="/">← Хоккейный хаб</a><header><div><div class="eyebrow">ЛИЧНЫЙ ХОККЕЙ · v0.42</div><h1>Мой хоккей</h1><p>Тренировки, тесты, обратная связь тренера и динамика катания.</p></div><div class="routine"><b>{html.escape(profile.get('training_frequency') or 'Режим не задан')}</b>{html.escape(profile.get('shooting_frequency') or '')}</div></header>{flash}
<section class="stats"><div class="stat"><span>Лучший круг</span><strong>{stat_best}</strong><small>{html.escape(profile.get('rink') or '')} · старт с места</small></div><div class="stat"><span>Разница направлений</span><strong>{stat_delta}</strong><small>последний парный замер</small></div><div class="stat"><span>Тренировок в истории</span><strong>{len(sessions)}</strong><small>записанных с базовой точки</small></div></section>
<section class="layout"><div class="card"><h2>Динамика полного круга</h2>{_progress_svg(tests)}</div><div class="card"><h2>Добавить тренировку</h2><form method="post" action="/my-hockey/session"><div class="two"><label>Дата<input type="date" name="session_date" value="{today}" required{disabled}></label><label>Тип<select name="session_type"{disabled}><option>Ледовая тренировка</option><option>Бросковая тренировка</option><option>Игра</option><option>ОФП / вне льда</option><option>Самостоятельная</option></select></label></div><label>Что тренировали<input name="focus" placeholder="катание, скорость, бросок"{disabled}></label><div class="two"><label>Самочувствие 1–10<input type="number" min="1" max="10" name="wellbeing"{disabled}></label><label>Нагрузка 1–10<input type="number" min="1" max="10" name="load"{disabled}></label></div><label>Моя заметка<textarea name="note" placeholder="Что получилось, что не получилось"{disabled}></textarea></label><label>Домашнее задание<textarea name="homework" placeholder="Что сделать до следующей тренировки"{disabled}></textarea></label><label>Комментарий тренера<textarea name="coach_note" placeholder="Если был новый фидбек"{disabled}></textarea></label><div class="two"><label>Круг, направление 1<input inputmode="decimal" name="lap_1" placeholder="24,50"{disabled}></label><label>Круг, направление 2<input inputmode="decimal" name="lap_2" placeholder="24,65"{disabled}></label></div><button type="submit"{disabled}>Сохранить тренировку</button><div class="form-note">Время круга необязательно. Если заполнить — замер автоматически добавится на график с протоколом 60×30 м, старт с места.</div></form></div></section>
<section class="layout section"><div class="card"><h2>История тренировок</h2>{''.join(session_html)}</div><div class="card"><h2>Фокус от тренера</h2>{''.join(notes_html)}</div></section></main></body></html>'''


@core.app.get("/my-hockey", response_class=HTMLResponse)
def personal_hockey_page(saved: int = 0, error: str | None = None):
    return render_personal_page(saved=bool(saved), error=error)


@core.app.post("/my-hockey/session")
def add_personal_session(
    session_date: str = Form(...),
    session_type: str = Form("Ледовая тренировка"),
    focus: str = Form(""),
    wellbeing: int | None = Form(None),
    load: int | None = Form(None),
    note: str = Form(""),
    homework: str = Form(""),
    coach_note: str = Form(""),
    lap_1: str = Form(""),
    lap_2: str = Form(""),
):
    try:
        day = datetime.strptime(session_date, "%Y-%m-%d").date()
        focus_items = [x.strip() for x in focus.replace(";", ",").split(",") if x.strip()]
        STORE.add_session(
            session_date=day,
            session_type=session_type,
            focus=focus_items,
            wellbeing=wellbeing,
            load=load,
            note=note,
            homework=homework,
            coach_note=coach_note,
            lap_1=_num(lap_1),
            lap_2=_num(lap_2),
        )
        return RedirectResponse("/my-hockey?saved=1", status_code=303)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:180]
        return HTMLResponse(render_personal_page(error=message), status_code=503)


@core.app.get("/api/v1/personal-hockey")
def personal_hockey_api():
    return STORE.load()


@core.app.get("/api/v1/personal-hockey/storage")
def personal_hockey_storage_api():
    return STORE.status()
