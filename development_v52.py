from __future__ import annotations

from datetime import datetime
import html

from bs4 import BeautifulSoup
from fastapi import Form
from fastapi.responses import RedirectResponse

import app_v513  # current production stack
import app_v05 as core
import personal_hockey_v42 as personal_base
from development_store_v52 import DevelopmentStore


STORE = DevelopmentStore()
_BOOTSTRAP = STORE.load()  # ensure schema/seed at startup; load() fails soft and logs the reason
_previous_renderer = personal_base.render_personal_page

LEVEL_LABELS = {
    1: "База",
    2: "Развиваю",
    3: "Рабочий",
    4: "Уверенно",
    5: "Сильная сторона",
}

SKILL_KEYWORDS = {
    "skating": ("катан", "скорост", "разгон"),
    "puck": ("шайб", "веден", "ведён", "контрол"),
    "shooting": ("брос", "кист", "щелч", "неудобн"),
    "maneuvers": ("манев", "манёв", "п-зон", "поворот", "переступ"),
    "game_sense": ("игр", "пози", "решен", "решён", "пас", "виден"),
    "physical": ("офп", "физ", "сил", "вынослив"),
}


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date_label(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(value)


def _last_trained(skill_key: str, sessions: list[dict]) -> str | None:
    needles = SKILL_KEYWORDS.get(skill_key, ())
    for session in sorted(sessions, key=lambda x: x.get("date", ""), reverse=True):
        hay = " ".join(session.get("focus") or []).casefold()
        if any(needle in hay for needle in needles):
            return session.get("date")
    return None


def _active(items: list[dict]) -> list[dict]:
    return [x for x in items if x.get("status") == "active"]


def _nearest_goal(goals: list[dict]) -> dict | None:
    active = _active(goals)
    dated = [x for x in active if x.get("target_date")]
    if dated:
        return sorted(dated, key=lambda x: x.get("target_date") or "9999-12-31")[0]
    return active[0] if active else None


def _last_lap_date(tests: list[dict]) -> str | None:
    dates = [x.get("date") for x in tests if x.get("metric") == "Полный круг" and x.get("date")]
    return max(dates) if dates else None


def _skill_cards(skills: list[dict], sessions: list[dict]) -> str:
    out = []
    for skill in skills:
        level = skill.get("level")
        label = LEVEL_LABELS.get(level, "Не оценено")
        trained = _last_trained(skill.get("key") or "", sessions)
        note = skill.get("note") or ""
        options = ['<option value="">Не оценено</option>']
        for value, title in LEVEL_LABELS.items():
            selected = " selected" if level == value else ""
            options.append(f'<option value="{value}"{selected}>{value} · {_esc(title)}</option>')
        out.append(f'''<article class="skill-card">
          <div class="skill-head"><div><span>НАВЫК</span><h3>{_esc(skill.get("title"))}</h3></div><b>{_esc(label)}</b></div>
          <div class="skill-meter level-{level or 0}"><i></i><i></i><i></i><i></i><i></i></div>
          <div class="skill-meta">{f'последний фокус · {_date_label(trained)}' if trained else 'в тренировках пока не распознан'}</div>
          {f'<p>{_esc(note)}</p>' if note else ''}
          <details><summary>Обновить оценку</summary><form method="post" action="/my-hockey/development/skill">
            <input type="hidden" name="skill_key" value="{_esc(skill.get('key'))}">
            <select name="level">{''.join(options)}</select>
            <input name="note" value="{_esc(note)}" placeholder="Короткая заметка о навыке">
            <button type="submit">Сохранить</button>
          </form></details>
        </article>''')
    return "".join(out)


def _goal_rows(goals: list[dict]) -> str:
    rows = []
    for goal in _active(goals):
        target = _date_label(goal.get("target_date")) or "без даты"
        category = goal.get("category") or "цель"
        rows.append(f'''<div class="task-row">
          <div><span>{_esc(category)} · {target}</span><b>{_esc(goal.get('title'))}</b>{f'<p>{_esc(goal.get("note"))}</p>' if goal.get("note") else ''}</div>
          <form method="post" action="/my-hockey/development/goal/{goal.get('id')}/done"><button class="done-btn" type="submit">✓</button></form>
        </div>''')
    return "".join(rows) or '<div class="dev-empty">Активных целей пока нет. Добавь первую конкретную контрольную точку.</div>'


def _homework_rows(items: list[dict]) -> str:
    rows = []
    for item in _active(items):
        due = _date_label(item.get("due_date"))
        source = item.get("source") or "личное"
        meta = f"{source}{' · до ' + due if due else ''}"
        rows.append(f'''<div class="task-row">
          <div><span>{_esc(meta)}</span><b>{_esc(item.get('text'))}</b></div>
          <form method="post" action="/my-hockey/development/homework/{item.get('id')}/done"><button class="done-btn" type="submit">✓</button></form>
        </div>''')
    return "".join(rows) or '<div class="dev-empty">Активных домашних заданий пока нет.</div>'


def _inherited_homework(sessions: list[dict]) -> str:
    for session in sorted(sessions, key=lambda x: x.get("date", ""), reverse=True):
        text = (session.get("homework") or "").strip()
        if text:
            return f'''<div class="inherited"><span>из тренировки {_date_label(session.get("date"))}</span><b>{_esc(text)}</b></div>'''
    return ""


def render_personal_v52(saved: bool = False, error: str | None = None) -> str:
    page = _previous_renderer(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")

    personal = personal_base.STORE.load()
    dev = STORE.load()
    sessions = personal.get("sessions") or []
    tests = personal.get("tests") or []
    notes = sorted(personal.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    skills = dev.get("skills") or []
    goals = dev.get("goals") or []
    homework = dev.get("homework") or []

    # The second current card becomes a true current-focus card rather than a
    # second history of every coach comment.
    current = soup.select_one("section.current-grid")
    if current:
        cards = current.find_all("article", recursive=False)
        if len(cards) >= 2:
            focus_card = cards[1]
            heading = focus_card.find("h2")
            if heading:
                heading.string = "Текущий фокус"
            coach_rows = focus_card.select(".coach-row")
            for row in coach_rows[1:]:
                row.decompose()
            if coach_rows:
                hint = soup.new_tag("div")
                hint["class"] = ["focus-hint"]
                hint.string = "Последний комментарий Тёмы. История остаётся в «Моей хоккейной среде»."
                focus_card.append(hint)

    active_goals = _active(goals)
    active_hw = _active(homework)
    nearest = _nearest_goal(goals)
    lap_date = _last_lap_date(tests)

    if nearest:
        checkpoint_title = _esc(nearest.get("title"))
        checkpoint_meta = _date_label(nearest.get("target_date")) or "дата не задана"
    elif lap_date:
        checkpoint_title = "Повтор полного круга пока не запланирован"
        checkpoint_meta = f"последний замер · {_date_label(lap_date)}"
    else:
        checkpoint_title = "Контрольная точка пока не задана"
        checkpoint_meta = "добавь цель с датой"

    focus_text = notes[0].get("text") if notes else "Новый фокус тренера пока не записан."

    dev_html = f'''<section class="development" id="development">
      <div class="dev-title"><div><span class="hub-eyebrow">РАЗВИТИЕ ИГРОКА</span><h2>Что делать дальше</h2></div><p>Не архив, а рабочий слой: фокус → задача → контроль.</p></div>
      <div class="dev-strip">
        <article class="dev-kpi focus"><span>ФОКУС</span><b>{_esc(focus_text)}</b><em>{_date_label(notes[0].get("date")) if notes else "—"}</em></article>
        <article class="dev-kpi"><span>АКТИВНЫЕ ЦЕЛИ</span><strong>{len(active_goals)}</strong><em>контрольных точек</em></article>
        <article class="dev-kpi"><span>ДОМАШНИЕ ЗАДАНИЯ</span><strong>{len(active_hw)}</strong><em>в работе</em></article>
        <article class="dev-kpi checkpoint"><span>БЛИЖАЙШАЯ КОНТРОЛЬНАЯ ТОЧКА</span><b>{checkpoint_title}</b><em>{_esc(checkpoint_meta)}</em></article>
      </div>

      <article class="hub-card dev-panel skills-panel">
        <div class="hub-section-head"><h2>Матрица навыков</h2><span class="hub-eyebrow">субъективная рабочая оценка</span></div>
        <div class="skills-grid">{_skill_cards(skills, sessions)}</div>
      </article>

      <div class="dev-lists">
        <article class="hub-card dev-panel">
          <div class="hub-section-head"><h2>Цели и контрольные точки</h2><span class="hub-eyebrow">{len(active_goals)} активных</span></div>
          <div class="task-list">{_goal_rows(goals)}</div>
          <details class="dev-add"><summary>Добавить цель</summary><form method="post" action="/my-hockey/development/goal">
            <input name="title" required placeholder="Например: повторить тест полного круга">
            <div class="dev-two"><input name="category" placeholder="Категория"><input type="date" name="target_date"></div>
            <textarea name="note" placeholder="Как пойму, что цель выполнена"></textarea>
            <button type="submit">Добавить цель</button>
          </form></details>
        </article>

        <article class="hub-card dev-panel">
          <div class="hub-section-head"><h2>Домашние задания</h2><span class="hub-eyebrow">{len(active_hw)} в работе</span></div>
          {_inherited_homework(sessions)}
          <div class="task-list">{_homework_rows(homework)}</div>
          <details class="dev-add"><summary>Добавить ДЗ</summary><form method="post" action="/my-hockey/development/homework">
            <input name="text" required placeholder="Что сделать до следующей тренировки">
            <div class="dev-two"><input name="source" placeholder="Источник: Тёма / сам"><input type="date" name="due_date"></div>
            <button type="submit">Добавить ДЗ</button>
          </form></details>
        </article>
      </div>
    </section>'''

    anchor = soup.select_one("section.benchmark-row")
    if anchor:
        anchor.insert_before(BeautifulSoup(dev_html, "html.parser"))
    else:
        form = soup.select_one("section.training-form")
        if form:
            form.insert_before(BeautifulSoup(dev_html, "html.parser"))

    css = r'''
/* v0.52: player development cockpit */
.development{margin-top:14px}.dev-title{display:flex;justify-content:space-between;gap:24px;align-items:end;margin:20px 0 10px}.dev-title h2{font-size:22px;margin:4px 0 0}.dev-title p{margin:0;color:#6e7a8a;font-size:10px}
.dev-strip{display:grid;grid-template-columns:1.55fr .65fr .65fr 1.15fr;gap:10px;margin-bottom:14px}.dev-kpi{min-height:104px;padding:14px 15px;background:linear-gradient(180deg,#11171e,#0a0e13);border:1px solid #25303b;border-radius:14px;position:relative;overflow:hidden}.dev-kpi:before{content:"";position:absolute;left:14px;top:0;width:32px;height:2px;background:#2a86d9;opacity:.55}.dev-kpi span{display:block;color:#6f7e90;font-size:8px;letter-spacing:.1em}.dev-kpi strong{display:block;font-size:30px;line-height:1;margin-top:12px}.dev-kpi b{display:block;font-size:11px;line-height:1.45;margin-top:10px;color:#d4dbe3}.dev-kpi em{display:block;font-style:normal;color:#657486;font-size:8px;margin-top:7px}.dev-kpi.focus:before,.dev-kpi.checkpoint:before{width:48px;opacity:.85}.dev-kpi.focus{background:radial-gradient(circle at 92% 12%,rgba(42,134,217,.08),transparent 35%),linear-gradient(180deg,#11171e,#0a0e13)}
.dev-panel{padding:17px}.skills-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.skill-card{background:#090d12;border:1px solid #252f3a;border-radius:13px;padding:13px}.skill-head{display:flex;justify-content:space-between;gap:12px;align-items:start}.skill-head span{color:#637286;font-size:7px;letter-spacing:.1em}.skill-head h3{font-size:12px;margin:4px 0 0}.skill-head b{font-size:9px;color:#8da6bf;font-weight:650}.skill-meter{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin:13px 0 8px}.skill-meter i{height:3px;border-radius:3px;background:#1e2934}.skill-meter.level-1 i:nth-child(-n+1),.skill-meter.level-2 i:nth-child(-n+2),.skill-meter.level-3 i:nth-child(-n+3),.skill-meter.level-4 i:nth-child(-n+4),.skill-meter.level-5 i:nth-child(-n+5){background:#2a86d9}.skill-meta{color:#647386;font-size:8px}.skill-card p{color:#8895a6;font-size:9px;line-height:1.45;margin:9px 0 0}.skill-card details{margin-top:10px}.skill-card summary,.dev-add summary{cursor:pointer;color:#718398;font-size:8px}.skill-card form,.dev-add form{display:grid;gap:8px;margin-top:9px;padding:0}.skill-card input,.skill-card select,.dev-add input,.dev-add textarea{font-size:9px;padding:8px 9px}.skill-card button,.dev-add button{border:1px solid #46596f;background:#101821;color:#d8e1ea;border-radius:8px;padding:8px 10px;font-size:9px;font-weight:750}
.dev-lists{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.task-list{display:grid}.task-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:11px 0;border-top:1px solid #202934}.task-row:first-child{border-top:0}.task-row span{display:block;color:#647488;font-size:8px}.task-row b{display:block;font-size:10px;margin-top:4px}.task-row p{margin:5px 0 0;color:#798697;font-size:9px;line-height:1.4}.task-row form{padding:0}.done-btn{display:grid;place-items:center;width:28px;height:28px;padding:0!important;border:1px solid #345c48!important;background:#0d1712!important;color:#8fc2a3!important;border-radius:8px!important}.dev-empty{color:#687586;font-size:9px;line-height:1.5;padding:8px 0 12px}.dev-add{border-top:1px solid #202934;padding-top:11px;margin-top:6px}.dev-two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.inherited{border:1px solid #2d3d4d;border-radius:10px;background:#0a1016;padding:10px 11px;margin-bottom:8px}.inherited span{display:block;color:#6c8299;font-size:8px}.inherited b{display:block;font-size:9px;line-height:1.45;margin-top:4px}.focus-hint{color:#617184;font-size:8px;border-top:1px solid #202934;margin-top:10px;padding-top:8px}
@media(max-width:950px){.dev-strip{grid-template-columns:1fr 1fr}.skills-grid{grid-template-columns:1fr 1fr}.dev-lists{grid-template-columns:1fr}}
@media(max-width:620px){.dev-title{display:block}.dev-title p{margin-top:6px}.dev-strip,.skills-grid,.dev-two{grid-template-columns:1fr}}
'''
    style = soup.find("style")
    if style:
        style.append(css)

    text = str(soup)
    text = text.replace("v0.51.3", "v0.52").replace("v0.51", "v0.52")
    return text


def _parse_date(raw: str) -> datetime.date | None:
    raw = (raw or "").strip()
    return datetime.strptime(raw, "%Y-%m-%d").date() if raw else None


@core.app.post("/my-hockey/development/skill")
def update_skill(skill_key: str = Form(...), level: str = Form(""), note: str = Form("")):
    try:
        parsed = int(level) if level.strip() else None
        STORE.update_skill(skill_key, parsed, note)
        return RedirectResponse("/my-hockey#development", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/my-hockey?error={type(exc).__name__}%3A%20{str(exc)[:120]}", status_code=303)


@core.app.post("/my-hockey/development/goal")
def add_goal(
    title: str = Form(...),
    category: str = Form(""),
    target_date: str = Form(""),
    note: str = Form(""),
):
    try:
        STORE.add_goal(title, category, _parse_date(target_date), note)
        return RedirectResponse("/my-hockey#development", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/my-hockey?error={type(exc).__name__}%3A%20{str(exc)[:120]}", status_code=303)


@core.app.post("/my-hockey/development/homework")
def add_homework(text: str = Form(...), source: str = Form(""), due_date: str = Form("")):
    try:
        STORE.add_homework(text, source, _parse_date(due_date))
        return RedirectResponse("/my-hockey#development", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/my-hockey?error={type(exc).__name__}%3A%20{str(exc)[:120]}", status_code=303)


@core.app.post("/my-hockey/development/goal/{item_id}/done")
def finish_goal(item_id: int):
    STORE.set_goal_done(item_id, True)
    return RedirectResponse("/my-hockey#development", status_code=303)


@core.app.post("/my-hockey/development/homework/{item_id}/done")
def finish_homework(item_id: int):
    STORE.set_homework_done(item_id, True)
    return RedirectResponse("/my-hockey#development", status_code=303)


personal_base.render_personal_page = render_personal_v52
core.app.version = "0.52.0"

app = core.app
