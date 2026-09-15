from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import html
import json
from pathlib import Path

from fastapi.responses import HTMLResponse

import app_v05 as core

DATA_PATH = Path(__file__).with_name("personal_hockey_data.json")


def load_personal_data() -> dict:
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[personal] data load failed: {type(exc).__name__}: {exc}", flush=True)
        return {"profile": {}, "coach_notes": [], "sessions": [], "tests": []}


def _date_label(raw: str) -> str:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return raw


def _progress_svg(tests: list[dict]) -> str:
    rows = [t for t in tests if t.get("metric") == "Полный круг" and isinstance(t.get("seconds"), (int, float))]
    if not rows:
        return '<div class="empty">Пока нет замеров для графика.</div>'

    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    directions = []
    for row in sorted(rows, key=lambda x: (x.get("date", ""), x.get("direction", ""))):
        date = row.get("date", "")
        direction = row.get("direction") or "Круг"
        grouped[date][direction] = float(row["seconds"])
        if direction not in directions:
            directions.append(direction)

    dates = sorted(grouped)
    values = [v for day in grouped.values() for v in day.values()]
    low = min(values) - 0.25
    high = max(values) + 0.25
    if high - low < 0.8:
        mid = (high + low) / 2
        low, high = mid - 0.4, mid + 0.4

    width, height = 720, 250
    left, right, top, bottom = 55, 22, 22, 48
    plot_w = width - left - right
    plot_h = height - top - bottom

    def x_pos(index: int) -> float:
        if len(dates) == 1:
            return left + plot_w / 2
        return left + index * plot_w / (len(dates) - 1)

    def y_pos(value: float) -> float:
        return top + (value - low) * plot_h / (high - low)

    grid = []
    for i in range(4):
        val = low + i * (high - low) / 3
        y = y_pos(val)
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="gridline"/>')
        grid.append(f'<text x="{left-8}" y="{y+4:.1f}" class="axis" text-anchor="end">{val:.1f}</text>')

    labels = []
    for i, date in enumerate(dates):
        labels.append(f'<text x="{x_pos(i):.1f}" y="{height-18}" class="axis" text-anchor="middle">{html.escape(_date_label(date)[:5])}</text>')

    series = []
    for direction in directions:
        points = []
        circles = []
        for i, date in enumerate(dates):
            value = grouped[date].get(direction)
            if value is None:
                continue
            x, y = x_pos(i), y_pos(value)
            points.append(f"{x:.1f},{y:.1f}")
            circles.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="point"/>'
                f'<text x="{x:.1f}" y="{y-10:.1f}" class="value" text-anchor="middle">{value:.2f}</text>'
            )
        if len(points) > 1:
            series.append(f'<polyline points="{" ".join(points)}" class="line"/>')
        series.extend(circles)

    legend = " · ".join(html.escape(x) for x in directions)
    hint = "Стартовая точка. После второго замера появится линия динамики." if len(dates) == 1 else "Меньше — быстрее. Сравниваются одинаковые условия теста."
    return f'''<div class="chart"><svg viewBox="0 0 {width} {height}" role="img" aria-label="Динамика времени полного круга">
      {''.join(grid)}{''.join(labels)}{''.join(series)}
      <text x="12" y="16" class="axis">сек.</text>
    </svg><div class="chart-foot"><span>{legend}</span><span>{hint}</span></div></div>'''


def render_personal_page() -> str:
    data = load_personal_data()
    profile = data.get("profile") or {}
    tests = data.get("tests") or []
    sessions = sorted(data.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
    notes = sorted(data.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)

    lap_tests = [t for t in tests if t.get("metric") == "Полный круг" and isinstance(t.get("seconds"), (int, float))]
    best = min((float(t["seconds"]) for t in lap_tests), default=None)
    latest_date = max((t.get("date", "") for t in lap_tests), default="")
    latest = [float(t["seconds"]) for t in lap_tests if t.get("date") == latest_date]
    delta = abs(max(latest) - min(latest)) if len(latest) >= 2 else None

    stat_best = f"{best:.2f} с" if best is not None else "—"
    stat_delta = f"{delta:.2f} с" if delta is not None else "—"

    session_html = []
    for session in sessions:
        focus = " · ".join(session.get("focus") or [])
        session_html.append(
            f'''<article class="timeline-item"><div class="date">{html.escape(_date_label(session.get('date', '')))}</div>
            <div><b>{html.escape(session.get('type') or 'Тренировка')}</b><span>{html.escape(focus)}</span>
            <p>{html.escape(session.get('note') or '')}</p></div></article>'''
        )
    if not session_html:
        session_html.append('<div class="empty">История тренировок пока пуста.</div>')

    notes_html = []
    for note in notes:
        notes_html.append(
            f'''<article class="coach-note"><span>{html.escape(_date_label(note.get('date', '')))}</span>
            <p>{html.escape(note.get('text') or '')}</p></article>'''
        )
    if not notes_html:
        notes_html.append('<div class="empty">Заметок тренера пока нет.</div>')

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Мой хоккей · Личный прогресс</title><meta name="theme-color" content="#0b0d11"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}a{{color:inherit}}.wrap{{max-width:980px;margin:auto;padding:28px 20px 80px}}.back{{color:#96a0b0;text-decoration:none;font-size:13px}}header{{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:end;border-bottom:1px solid #262b35;padding:18px 0 24px}}.eyebrow{{font-size:11px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:44px;line-height:1;margin:7px 0 7px}}header p{{margin:0;color:#98a3b3;max-width:640px}}.routine{{text-align:right;color:#8e99aa;font-size:12px;line-height:1.6}}.routine b{{display:block;color:#dce2eb;font-size:13px}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:24px 0}}.stat{{background:#12161d;border:1px solid #252a33;border-radius:14px;padding:15px}}.stat span{{display:block;color:#7f8999;font-size:10px;text-transform:uppercase;letter-spacing:.06em}}.stat strong{{display:block;font-size:28px;margin-top:7px;font-variant-numeric:tabular-nums}}.stat small{{display:block;color:#818c9c;margin-top:4px;font-size:11px}}.grid{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(280px,.75fr);gap:14px}}.card{{background:#12161d;border:1px solid #252a33;border-radius:16px;padding:16px}}h2{{font-size:12px;color:#9aa5b5;text-transform:uppercase;letter-spacing:.075em;margin:0 0 14px}}.chart{{overflow:hidden}}svg{{width:100%;height:auto;display:block}}.gridline{{stroke:#242b36;stroke-width:1}}.axis{{fill:#737f90;font-size:10px}}.line{{fill:none;stroke:#dfe5ee;stroke-width:2}}.point{{fill:#dfe5ee;stroke:#0b0d11;stroke-width:2}}.value{{fill:#eef2f7;font-size:10px;font-weight:750}}.chart-foot{{display:flex;justify-content:space-between;gap:14px;color:#778394;font-size:10px;border-top:1px solid #232a34;padding-top:9px}}.coach-note{{border-left:3px solid #6079a7;padding:3px 0 3px 12px}}.coach-note span{{color:#768294;font-size:10px}}.coach-note p{{margin:6px 0 0;color:#e2e6ec;font-size:14px;line-height:1.5}}.section{{margin-top:14px}}.timeline{{display:grid;gap:0}}.timeline-item{{display:grid;grid-template-columns:100px 1fr;gap:14px;padding:12px 0;border-bottom:1px solid #252a33}}.timeline-item:last-child{{border-bottom:0}}.timeline-item .date{{color:#7d8898;font-size:11px;padding-top:2px}}.timeline-item b{{font-size:14px}}.timeline-item span{{display:block;color:#8994a4;font-size:11px;margin-top:3px}}.timeline-item p{{margin:6px 0 0;color:#b2bbc8;font-size:12px;line-height:1.45}}.tests{{display:grid;gap:8px}}.test{{padding:11px 12px;background:#171c24;border-radius:10px}}.test b{{display:block;font-size:13px}}.test span{{display:block;color:#8490a0;font-size:11px;margin-top:4px;line-height:1.4}}.badge{{display:inline-block;margin-top:7px;padding:4px 7px;border-radius:6px;background:#1d2837;color:#aebedd;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.05em}}.empty{{color:#7d8796;font-size:12px;padding:10px 0}}.footer-note{{margin-top:20px;color:#697586;font-size:10px;line-height:1.5}}@media(max-width:720px){{.wrap{{padding:20px 14px 60px}}header{{grid-template-columns:1fr}}.routine{{text-align:left}}h1{{font-size:37px}}.stats{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}.chart-foot{{flex-direction:column}}.timeline-item{{grid-template-columns:82px 1fr}}}}
</style></head><body><main class="wrap"><a class="back" href="/">← Хоккейный хаб</a><header><div><div class="eyebrow">ЛИЧНЫЙ ХОККЕЙ · v0.41</div><h1>Мой хоккей</h1><p>Тренировки, контрольные тесты, заметки тренера и динамика катания — отдельно от матчей команд.</p></div><div class="routine"><b>{html.escape(profile.get('training_frequency') or 'Режим не задан')}</b>{html.escape(profile.get('shooting_frequency') or '')}</div></header>
<section class="stats"><div class="stat"><span>Лучший круг</span><strong>{stat_best}</strong><small>{html.escape(profile.get('rink') or '')} · старт с места</small></div><div class="stat"><span>Разница направлений</span><strong>{stat_delta}</strong><small>чем ближе к нулю, тем симметричнее катание</small></div><div class="stat"><span>База</span><strong>{html.escape(_date_label(latest_date) if latest_date else '—')}</strong><small>первая контрольная точка</small></div></section>
<section class="grid"><div class="card"><h2>Динамика полного круга</h2>{_progress_svg(tests)}</div><div class="card"><h2>Фокус от тренера</h2>{''.join(notes_html)}</div></section>
<section class="grid section"><div class="card"><h2>История тренировок</h2><div class="timeline">{''.join(session_html)}</div></div><div class="card"><h2>Следующие контрольные точки</h2><div class="tests"><div class="test"><b>Повтор полного круга</b><span>60×30 м, старт с места, обе стороны. Повторять в сопоставимом состоянии и после одинаковой разминки.</span><span class="badge">следующий замер</span></div><div class="test"><b>Разгон по прямой</b><span>Добавим фиксированную дистанцию и единый протокол, чтобы отдельно видеть стартовую скорость.</span><span class="badge">протокол не задан</span></div><div class="test"><b>Техника элементов</b><span>Отдельная шкала по разворотам, торможению, движению спиной и уверенности на скорости — лучше заполнять вместе с тренером.</span><span class="badge">следующий этап</span></div></div></div></section>
<div class="footer-note">Сейчас данные читаются из отдельной персональной истории проекта. После подключения PostgreSQL к веб-сервису сюда можно добавить ввод тренировок прямо с телефона и синхронизацию между устройствами.</div></main></body></html>'''


@core.app.get("/my-hockey", response_class=HTMLResponse)
def personal_hockey_page():
    return render_personal_page()


@core.app.get("/api/v1/personal-hockey")
def personal_hockey_api():
    return load_personal_data()
