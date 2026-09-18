from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta
from io import BytesIO
import html
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi import File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from PIL import Image, ImageOps

import app_v513  # stable public/live/auth shell
import app_v05 as core
import auth_v49
import home_v44
import personal_hockey_v42 as personal_base
import closet_v48
import environment_v50 as env
from closet_store_v48 import ClosetStore
from development_store_v52 import DevelopmentStore
from memory_store_v54 import MemoryStore, season_for_date
from design_system_v46 import COMMON_CSS, topbar


VERSION = "0.56"
PERSONAL = personal_base.STORE
CLOSET = closet_v48.STORE
DEV = DevelopmentStore()
MEMORY = MemoryStore()
MAX_MEMORY_PHOTOS = 20

# Stores bootstrap. Errors remain visible through their normal status/load payloads.
DEV.load()
MEMORY.load()


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date(raw: str | None):
    text = (raw or "").strip()
    return datetime.strptime(text, "%Y-%m-%d").date() if text else None


def _date_label(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(raw)


def _num(raw: str | None) -> float | None:
    text = (raw or "").strip().replace(",", ".")
    return float(text) if text else None


def _selected(options: list[str], current: str) -> str:
    return "".join(
        f'<option value="{_esc(value)}"{" selected" if value == current else ""}>{_esc(value)}</option>'
        for value in options
    )


def _safe_redirect_error(path: str, exc: Exception, anchor: str = ""):
    message = (str(exc) or type(exc).__name__)[:180]
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{sep}error={quote(message)}{anchor}", status_code=303)


def _tabs(active: str) -> str:
    items = [
        ("me", "Я", "/my-hockey"),
        ("environment", "Моя хоккейная среда", "/my-hockey/environment"),
        ("closet", "Хоккейный шкаф", "/my-hockey/closet"),
        ("memory", "Память", "/my-hockey/memory"),
    ]
    return '<nav class="mine-tabs">' + "".join(
        f'<a{" class=\"active\"" if key == active else ""} href="{href}">{label}</a>'
        for key, label, href in items
    ) + "</nav>"


TABS_CSS = r"""
.mine-tabs{display:flex;gap:8px;margin:18px 0;overflow:auto}
.mine-tabs a{position:relative;text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}
.mine-tabs a.active{color:#f2f5f8;border-color:#53616f;background:linear-gradient(180deg,#161c23,#0e1319)}
.mine-tabs a.active:after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:#2a86d9}
"""


# ---------------------------------------------------------------------------
# One-time homework link migration + sync new sessions through existing route
# ---------------------------------------------------------------------------

def _bootstrap_session_homework() -> None:
    try:
        pdata = PERSONAL.load()
        ddata = DEV.load()
        linked = {x.get("session_id") for x in ddata.get("homework") or [] if x.get("session_id")}
        for session in pdata.get("sessions") or []:
            sid = session.get("id")
            homework = (session.get("homework") or "").strip()
            if sid and homework and sid not in linked:
                DEV.sync_session_homework(
                    int(sid), homework, f"Тренировка {_date_label(session.get('date'))}"
                )
    except Exception as exc:
        print(f"[v56] homework migration skipped: {type(exc).__name__}: {exc}", flush=True)


_bootstrap_session_homework()

_original_add_session = PERSONAL.add_session


def _add_session_synced(**kwargs):
    session_id = _original_add_session(**kwargs)
    try:
        DEV.sync_session_homework(
            session_id,
            kwargs.get("homework") or "",
            f"Тренировка {_date_label(kwargs.get('session_date').isoformat() if kwargs.get('session_date') else '')}",
        )
    except Exception as exc:
        print(f"[v56] homework sync failed for session {session_id}: {exc}", flush=True)
    return session_id


PERSONAL.add_session = _add_session_synced


# ---------------------------------------------------------------------------
# Player / "Я"
# ---------------------------------------------------------------------------

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


def _active(rows: list[dict]) -> list[dict]:
    return [x for x in rows if x.get("status") == "active"]


def _done(rows: list[dict]) -> list[dict]:
    return [x for x in rows if x.get("status") == "done"]


def _last_trained(skill_key: str, sessions: list[dict]) -> str | None:
    needles = SKILL_KEYWORDS.get(skill_key, ())
    for session in sorted(sessions, key=lambda x: x.get("date", ""), reverse=True):
        hay = " ".join(session.get("focus") or []).casefold()
        if any(needle in hay for needle in needles):
            return session.get("date")
    return None


def _skill_cards(skills: list[dict], sessions: list[dict]) -> str:
    cards = []
    for skill in skills:
        level = skill.get("level")
        label = LEVEL_LABELS.get(level, "Не оценено")
        trained = _last_trained(skill.get("key") or "", sessions)
        note = skill.get("note") or ""
        options = ['<option value="">Не оценено</option>']
        for value, title in LEVEL_LABELS.items():
            options.append(
                f'<option value="{value}"{" selected" if level == value else ""}>{value} · {_esc(title)}</option>'
            )
        cards.append(f'''<article class="skill-card">
          <div class="skill-head"><div><span>НАВЫК</span><h3>{_esc(skill.get("title"))}</h3></div><b>{_esc(label)}</b></div>
          <div class="skill-meter level-{level or 0}"><i></i><i></i><i></i><i></i><i></i></div>
          <div class="skill-meta">{f'последний фокус · {_date_label(trained)}' if trained else 'в тренировках пока не распознан'}</div>
          {f'<p>{_esc(note)}</p>' if note else ''}
          <details><summary>Обновить оценку</summary><form method="post" action="/my-hockey/development/skill">
            <input type="hidden" name="skill_key" value="{_esc(skill.get("key"))}">
            <select name="level">{''.join(options)}</select>
            <input name="note" value="{_esc(note)}" placeholder="Короткая заметка о навыке">
            <button type="submit">Сохранить</button>
          </form></details>
        </article>''')
    return "".join(cards)


def _goal_row(goal: dict) -> str:
    target = _date_label(goal.get("target_date")) if goal.get("target_date") else "без даты"
    category = goal.get("category") or "цель"
    return f'''<div class="task-row editable-task">
      <div><span>{_esc(category)} · {target}</span><b>{_esc(goal.get("title"))}</b>{f'<p>{_esc(goal.get("note"))}</p>' if goal.get("note") else ''}</div>
      <div class="task-actions">
        <details><summary title="Редактировать">✎</summary><form method="post" action="/my-hockey/development/goal/{goal["id"]}/edit">
          <input name="title" value="{_esc(goal.get("title"))}" required>
          <div class="dev-two"><input name="category" value="{_esc(goal.get("category"))}" placeholder="Категория"><input type="date" name="target_date" value="{_esc(goal.get("target_date"))}"></div>
          <textarea name="note">{_esc(goal.get("note"))}</textarea>
          <button type="submit">Сохранить</button>
          <button class="danger-link" formaction="/my-hockey/development/goal/{goal["id"]}/delete" formmethod="post" onclick="return confirm('Удалить цель?')">Удалить</button>
        </form></details>
        <form method="post" action="/my-hockey/development/goal/{goal["id"]}/done"><button class="done-btn" type="submit" title="Завершить">✓</button></form>
      </div>
    </div>'''


def _homework_row(item: dict) -> str:
    due = _date_label(item.get("due_date")) if item.get("due_date") else ""
    source = item.get("source") or ("из тренировки" if item.get("session_id") else "личное")
    meta = f"{source}{' · до ' + due if due else ''}"
    linked = bool(item.get("session_id"))
    edit = ""
    if not linked:
        edit = f'''<details><summary title="Редактировать">✎</summary><form method="post" action="/my-hockey/development/homework/{item["id"]}/edit">
          <input name="text" value="{_esc(item.get("text"))}" required>
          <div class="dev-two"><input name="source" value="{_esc(item.get("source"))}" placeholder="Источник"><input type="date" name="due_date" value="{_esc(item.get("due_date"))}"></div>
          <button type="submit">Сохранить</button>
          <button class="danger-link" formaction="/my-hockey/development/homework/{item["id"]}/delete" formmethod="post" onclick="return confirm('Удалить ДЗ?')">Удалить</button>
        </form></details>'''
    return f'''<div class="task-row editable-task">
      <div><span>{_esc(meta)}</span><b>{_esc(item.get("text"))}</b>{'<em>редактируется вместе с тренировкой</em>' if linked else ''}</div>
      <div class="task-actions">{edit}
        <form method="post" action="/my-hockey/development/homework/{item["id"]}/done"><button class="done-btn" type="submit" title="Завершить">✓</button></form>
      </div>
    </div>'''


def _completed_history(goals: list[dict], homework: list[dict]) -> str:
    done_goals = _done(goals)
    done_hw = _done(homework)
    if not done_goals and not done_hw:
        return ""
    rows = []
    for g in done_goals[:8]:
        rows.append(f'<div class="done-row"><span>цель</span><b>{_esc(g.get("title"))}</b><form method="post" action="/my-hockey/development/goal/{g["id"]}/reopen"><button>вернуть</button></form></div>')
    for h in done_hw[:8]:
        rows.append(f'<div class="done-row"><span>ДЗ</span><b>{_esc(h.get("text"))}</b><form method="post" action="/my-hockey/development/homework/{h["id"]}/reopen"><button>вернуть</button></form></div>')
    return f'<details class="done-history"><summary>Выполненное · {len(done_goals)+len(done_hw)}</summary><div>{"".join(rows)}</div></details>'


def _session_edit_form(session: dict, coach_note: str, lap_1: str, lap_2: str) -> str:
    types = ["Ледовая тренировка", "Бросковая тренировка", "Игра", "ОФП / вне льда", "Самостоятельная"]
    return f'''<details class="session-record-edit">
      <summary>Редактировать</summary>
      <form method="post" action="/my-hockey/session/{session["id"]}/edit">
        <div class="edit-two"><label>Дата<input type="date" name="session_date" value="{_esc(session.get("date"))}" required></label>
        <label>Тип<select name="session_type">{_selected(types, session.get("type") or "Ледовая тренировка")}</select></label></div>
        <label>Что тренировали<input name="focus" value="{_esc(", ".join(session.get("focus") or []))}"></label>
        <div class="edit-two"><label>Самочувствие<input type="number" min="1" max="10" name="wellbeing" value="{_esc(session.get("wellbeing"))}"></label>
        <label>Нагрузка<input type="number" min="1" max="10" name="load" value="{_esc(session.get("load"))}"></label></div>
        <label>Моя заметка<textarea name="note">{_esc(session.get("note"))}</textarea></label>
        <label>ДЗ<textarea name="homework">{_esc(session.get("homework"))}</textarea></label>
        <label>Комментарий тренера<textarea name="coach_note">{_esc(coach_note)}</textarea></label>
        <div class="edit-two"><label>Круг 1<input name="lap_1" value="{_esc(lap_1)}"></label><label>Круг 2<input name="lap_2" value="{_esc(lap_2)}"></label></div>
        <button class="edit-save" type="submit">Сохранить изменения</button>
        <button class="danger-link" formaction="/my-hockey/session/{session["id"]}/delete" formmethod="post" onclick="return confirm('Удалить тренировку и связанные замеры/комментарий?')">Удалить тренировку</button>
      </form>
    </details>'''


_base_personal_renderer = personal_base.render_personal_page


def render_personal_v56(saved: bool = False, error: str | None = None) -> str:
    page = _base_personal_renderer(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")
    pdata = PERSONAL.load()
    ddata = DEV.load()
    sessions = sorted(pdata.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
    tests = pdata.get("tests") or []
    notes = sorted(pdata.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    goals = ddata.get("goals") or []
    homework = ddata.get("homework") or []
    skills = ddata.get("skills") or []

    # Stable shell: no release number in hero.
    eyebrow = soup.select_one(".mine-hero .hub-eyebrow")
    if eyebrow:
        eyebrow.string = "Личный хоккей"
    old_tabs = soup.select_one(".mine-tabs")
    if old_tabs:
        old_tabs.replace_with(BeautifulSoup(_tabs("me"), "html.parser"))

    # Three live KPIs, no benchmark duplication.
    stats = soup.select("section.stats > article.stat")
    today = datetime.now(core.MOSCOW).date()
    cutoff = today - timedelta(days=29)
    recent = []
    for s in sessions:
        try:
            day = datetime.strptime(s.get("date") or "", "%Y-%m-%d").date()
        except Exception:
            continue
        if cutoff <= day <= today:
            recent.append(s)
    loads = [float(s["load"]) for s in recent if isinstance(s.get("load"), (int, float))]
    if len(stats) >= 3:
        labels = [
            ("Средняя нагрузка · 30 дней", f"{sum(loads)/len(loads):.1f}" if loads else "—", f"по {len(loads)} тренировкам с оценкой" if loads else "пока нет оценок"),
            ("Тренировок за 30 дней", str(len(recent)), "текущий тренировочный ритм"),
            ("Тренировок в истории", str(len(sessions)), "личная история"),
        ]
        for stat, (label, value, note) in zip(stats[:3], labels):
            if stat.find("span"): stat.find("span").string = label
            if stat.find("strong"):
                stat.find("strong").clear()
                stat.find("strong").append(value)
                if label.startswith("Средняя") and value != "—":
                    small = soup.new_tag("small"); small.string = "/10"; stat.find("strong").append(" "); stat.find("strong").append(small)
            if stat.find("em"): stat.find("em").string = note

    # Current focus = only latest coach note. Full history belongs to Environment.
    current = soup.select_one("section.current-grid")
    if current:
        cards = current.find_all("article", recursive=False)
        if len(cards) >= 2:
            focus_card = cards[1]
            h2 = focus_card.find("h2")
            if h2: h2.string = "Текущий фокус"
            for row in focus_card.select(".coach-row")[1:]:
                row.decompose()
            hint = soup.new_tag("div"); hint["class"]=["focus-hint"]
            hint.string = "История комментариев — в «Моей хоккейной среде»."
            focus_card.append(hint)

    active_goals = _active(goals)
    active_hw = _active(homework)
    dated_goals = [x for x in active_goals if x.get("target_date")]
    nearest = sorted(dated_goals, key=lambda x: x.get("target_date") or "9999")[0] if dated_goals else (active_goals[0] if active_goals else None)
    lap_dates = [x.get("date") for x in tests if x.get("metric") == "Полный круг" and x.get("date")]
    if nearest:
        checkpoint = _esc(nearest.get("title"))
        checkpoint_meta = _date_label(nearest.get("target_date")) if nearest.get("target_date") else "без даты"
    elif lap_dates:
        checkpoint = "Повтор полного круга пока не запланирован"
        checkpoint_meta = f"последний замер · {_date_label(max(lap_dates))}"
    else:
        checkpoint = "Контрольная точка пока не задана"
        checkpoint_meta = "добавь цель с датой"

    dev_html = f'''<section class="development" id="development">
      <div class="dev-title"><div><span class="hub-eyebrow">РАЗВИТИЕ ИГРОКА</span><h2>Что делать дальше</h2></div><p>Рабочий слой: задача → действие → контроль.</p></div>
      <div class="dev-strip">
        <article class="dev-kpi"><span>АКТИВНЫЕ ЦЕЛИ</span><strong>{len(active_goals)}</strong><em>контрольных точек</em></article>
        <article class="dev-kpi"><span>ДОМАШНИЕ ЗАДАНИЯ</span><strong>{len(active_hw)}</strong><em>в работе</em></article>
        <article class="dev-kpi checkpoint"><span>БЛИЖАЙШАЯ КОНТРОЛЬНАЯ ТОЧКА</span><b>{checkpoint}</b><em>{_esc(checkpoint_meta)}</em></article>
      </div>
      <article class="hub-card dev-panel skills-panel"><div class="hub-section-head"><h2>Матрица навыков</h2><span class="hub-eyebrow">рабочая самооценка</span></div><div class="skills-grid">{_skill_cards(skills,sessions)}</div></article>
      <div class="dev-lists">
        <article class="hub-card dev-panel"><div class="hub-section-head"><h2>Цели</h2><span class="hub-eyebrow">{len(active_goals)} активных</span></div><div class="task-list">{''.join(_goal_row(x) for x in active_goals) if active_goals else '<div class="dev-empty">Активных целей пока нет.</div>'}</div>
          <details class="dev-add"><summary>Добавить цель</summary><form method="post" action="/my-hockey/development/goal"><input name="title" required placeholder="Конкретная контрольная точка"><div class="dev-two"><input name="category" placeholder="Категория"><input type="date" name="target_date"></div><textarea name="note" placeholder="Как пойму, что цель выполнена"></textarea><button type="submit">Добавить</button></form></details>
        </article>
        <article class="hub-card dev-panel"><div class="hub-section-head"><h2>Домашние задания</h2><span class="hub-eyebrow">{len(active_hw)} в работе</span></div><div class="task-list">{''.join(_homework_row(x) for x in active_hw) if active_hw else '<div class="dev-empty">Активных ДЗ пока нет.</div>'}</div>
          <details class="dev-add"><summary>Добавить ДЗ</summary><form method="post" action="/my-hockey/development/homework"><input name="text" required placeholder="Что сделать до следующей тренировки"><div class="dev-two"><input name="source" placeholder="Источник: Тёма / сам"><input type="date" name="due_date"></div><button type="submit">Добавить</button></form></details>
        </article>
      </div>
      {_completed_history(goals,homework)}
    </section>'''

    benchmark = soup.select_one("section.benchmark-row")
    if benchmark:
        benchmark.insert_before(BeautifulSoup(dev_html, "html.parser"))
    else:
        form = soup.select_one("section.training-form")
        if form: form.insert_before(BeautifulSoup(dev_html, "html.parser"))

    # Session edit/delete lives with the history row.
    rows = soup.select(".history-row")
    for row, session in zip(rows, sessions[:8]):
        sid = session.get("id")
        coach = next((x.get("text") or "" for x in notes if x.get("session_id") == sid), "")
        lap1 = next((x.get("seconds") for x in tests if x.get("session_id") == sid and x.get("direction") == "Направление 1"), "")
        lap2 = next((x.get("seconds") for x in tests if x.get("session_id") == sid and x.get("direction") == "Направление 2"), "")
        row.append(BeautifulSoup(_session_edit_form(
            session, coach,
            "" if lap1 == "" else f"{float(lap1):.2f}",
            "" if lap2 == "" else f"{float(lap2):.2f}",
        ), "html.parser"))

    # Form wording: homework now feeds the single development task list.
    for label in soup.find_all("label"):
        text = label.get_text(" ", strip=True)
        if text.startswith("Домашнее задание"):
            label.contents[0].replace_with("ДЗ / что сделать до следующей тренировки")

    footer = soup.select_one(".footer-note")
    if footer:
        spans = footer.find_all("span")
        if spans:
            spans[-1].string = f"Hockey Hub · v{VERSION}"

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.56 player cleanup */
.dev-title{display:flex;justify-content:space-between;gap:24px;align-items:end;margin:20px 0 10px}.dev-title h2{font-size:22px;margin:4px 0 0}.dev-title p{margin:0;color:#6e7a8a;font-size:10px}
.dev-strip{display:grid;grid-template-columns:.65fr .65fr 1.7fr;gap:10px;margin-bottom:14px}.dev-kpi{min-height:92px;padding:14px 15px;background:linear-gradient(180deg,#11171e,#0a0e13);border:1px solid #25303b;border-radius:14px;position:relative}.dev-kpi:before{content:"";position:absolute;left:14px;top:0;width:32px;height:2px;background:#2a86d9;opacity:.55}.dev-kpi span{display:block;color:#6f7e90;font-size:8px;letter-spacing:.1em}.dev-kpi strong{display:block;font-size:28px;line-height:1;margin-top:12px}.dev-kpi b{display:block;font-size:11px;line-height:1.45;margin-top:10px}.dev-kpi em{display:block;font-style:normal;color:#657486;font-size:8px;margin-top:7px}
.dev-panel{padding:17px}.skills-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.skill-card{background:#090d12;border:1px solid #252f3a;border-radius:13px;padding:13px}.skill-head{display:flex;justify-content:space-between;gap:12px}.skill-head span{color:#637286;font-size:7px}.skill-head h3{font-size:12px;margin:4px 0 0}.skill-head b{font-size:9px;color:#8da6bf}.skill-meter{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin:13px 0 8px}.skill-meter i{height:3px;border-radius:3px;background:#1e2934}.skill-meter.level-1 i:nth-child(-n+1),.skill-meter.level-2 i:nth-child(-n+2),.skill-meter.level-3 i:nth-child(-n+3),.skill-meter.level-4 i:nth-child(-n+4),.skill-meter.level-5 i:nth-child(-n+5){background:#2a86d9}.skill-meta{color:#647386;font-size:8px}.skill-card p{color:#8895a6;font-size:9px}.skill-card details,.dev-add{margin-top:10px}.skill-card summary,.dev-add summary{cursor:pointer;color:#718398;font-size:8px}.skill-card form,.dev-add form{display:grid;gap:8px;margin-top:9px;padding:0}.skill-card input,.skill-card select,.dev-add input,.dev-add textarea{font-size:9px;padding:8px}.skill-card button,.dev-add button,.edit-save{border:1px solid #46596f;background:#101821;color:#d8e1ea;border-radius:8px;padding:8px 10px;font-size:9px;font-weight:750}
.dev-lists{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.task-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:11px 0;border-top:1px solid #202934}.task-row span{display:block;color:#647488;font-size:8px}.task-row b{display:block;font-size:10px;margin-top:4px}.task-row p,.task-row em{display:block;margin:5px 0 0;color:#798697;font-size:8px;font-style:normal}.task-actions{display:flex;gap:6px}.task-actions>form{padding:0}.task-actions details summary{cursor:pointer;list-style:none;border:1px solid #314051;border-radius:8px;width:28px;height:28px;display:grid;place-items:center;color:#7fa2c1}.task-actions details form{position:absolute;z-index:8;right:42px;width:min(420px,70vw);padding:11px;background:#0a1016;border:1px solid #304052;border-radius:10px}.editable-task{position:relative}.done-btn{display:grid!important;place-items:center;width:28px;height:28px;padding:0!important;border:1px solid #345c48!important;background:#0d1712!important;color:#8fc2a3!important;border-radius:8px!important}.dev-empty{color:#687586;font-size:9px;padding:8px 0}.dev-add{border-top:1px solid #202934;padding-top:11px}.dev-two,.edit-two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.focus-hint{color:#617184;font-size:8px;border-top:1px solid #202934;margin-top:10px;padding-top:8px}
.session-record-edit{grid-column:2/-1;margin-top:5px;font-size:8px}.session-record-edit summary{cursor:pointer;color:#6785a3}.session-record-edit form{display:grid;gap:8px;margin-top:8px;padding:11px;border:1px solid #283542;border-radius:10px;background:#080d12}.session-record-edit label{display:grid;gap:4px;color:#78889a;font-size:8px}.danger-link{border:0!important;background:transparent!important;color:#8b5960!important;text-align:left;padding:4px 0!important;font-weight:500!important;cursor:pointer}.done-history{margin-top:12px;border:1px solid #202a34;border-radius:11px;padding:10px 12px;color:#718296;font-size:9px}.done-history summary{cursor:pointer}.done-row{display:grid;grid-template-columns:42px 1fr auto;gap:8px;padding:8px 0;border-top:1px solid #202934}.done-row span{color:#627286}.done-row b{font-size:9px}.done-row form{padding:0}.done-row button{border:0;background:transparent;color:#7894ad;font-size:8px;cursor:pointer}
@media(max-width:950px){.dev-strip{grid-template-columns:1fr 1fr}.dev-strip .checkpoint{grid-column:1/-1}.skills-grid{grid-template-columns:1fr 1fr}.dev-lists{grid-template-columns:1fr}}
@media(max-width:620px){.dev-title{display:block}.dev-strip,.skills-grid,.dev-two,.edit-two{grid-template-columns:1fr}.dev-strip .checkpoint{grid-column:auto}.task-actions details form{right:0;width:78vw}}
""")
    return str(soup)


personal_base.render_personal_page = render_personal_v56


# ---------------------------------------------------------------------------
# Environment / "Моя хоккейная среда"
# ---------------------------------------------------------------------------

def _coach_note_rows(notes: list[dict], limit: int = 5) -> str:
    if not notes:
        return '<div class="empty">Комментариев пока нет.</div>'
    return "".join(
        f'<article class="coach-note"><time>{_date_label(n.get("date"))}</time><p>{_esc(n.get("text"))}</p></article>'
        for n in notes[:limit]
    )


def render_environment_v56() -> str:
    games = env._eskulap_games()
    summary = env._eskulap_summary(games)
    finished = summary["finished"]
    pdata = PERSONAL.load()
    notes = sorted(pdata.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    sessions = pdata.get("sessions") or []
    latest = notes[0] if notes else None
    previous = notes[1] if len(notes) > 1 else None
    record = f'{summary["wins"]}–{summary["losses"]}' + (f'–{summary["draws"]}' if summary["draws"] else '')
    team_meta = f'{len(finished)} матчей · {record} · шайбы {summary["gf"]}:{summary["ga"]}' if finished else "сезонные результаты пока не загружены"

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Моя хоккейная среда · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>
{COMMON_CSS}
:root{{--soyuz:#2a86d9}}body{{background:radial-gradient(circle at 80% 2%,rgba(42,134,217,.08),transparent 24%),#05070b}}
{TABS_CSS}
.env-hero{{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}.env-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.env-hero p{{margin:0;color:#929dac;max-width:760px;font-size:15px;line-height:1.55}}.env-code{{text-align:right;color:#708094;font-size:9px;letter-spacing:.12em;text-transform:uppercase}}.env-code b{{display:block;color:#d8dee6;font-size:13px;margin-bottom:4px}}
.coach-card{{padding:22px;background:radial-gradient(circle at 90% 10%,rgba(42,134,217,.10),transparent 35%),linear-gradient(145deg,#11171f,#090d12);border:1px solid #28323e;border-radius:17px}}.coach-kicker{{color:#6f8297;font-size:9px;letter-spacing:.12em;text-transform:uppercase}}.coach-card h2{{font-size:30px;margin:10px 0 5px}}.coach-role{{color:#c6ced8;font-size:12px}}.coach-focus-grid{{display:grid;grid-template-columns:1.6fr 1.6fr .55fr;gap:9px;margin-top:18px}}.focus-box{{border:1px solid #27333f;border-radius:12px;background:#090e14;padding:12px}}.focus-box span{{display:block;color:#65768a;font-size:8px;text-transform:uppercase;letter-spacing:.08em}}.focus-box b{{display:block;font-size:10px;line-height:1.5;margin-top:7px}}.focus-box em{{display:block;color:#617183;font-size:8px;font-style:normal;margin-top:5px}}.focus-box strong{{display:block;font-size:23px;margin-top:8px}}
.env-grid{{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:14px;margin-top:14px}}.panel{{padding:18px}}.section-title{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px}}.section-title h2{{margin:0;font-size:15px}}.section-title span{{color:#6f7d8d;font-size:8px;text-transform:uppercase;letter-spacing:.1em}}
.team-head h2{{font-size:24px;margin:4px 0}}.team-head p{{color:#738194;font-size:9px;margin:0}}.team-meta{{color:#7e8e9f;font-size:9px;margin:10px 0 14px}}.next-game{{border:1px solid #263443;background:#090e14;border-radius:12px;padding:12px;margin-bottom:14px}}.next-kicker{{color:#7790aa;font-size:8px}}.next-game h3{{font-size:15px;margin:10px 0 6px}}.next-score{{font-size:24px;font-weight:850}}.next-game p{{color:#6d7a8b;font-size:8px}}.ghost{{color:#8ba0b6;font-size:8px;text-decoration:none}}.form-line{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}}.form-chip{{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;font-size:8px;font-weight:850;border:1px solid #2a333d;background:#10151b}}.form-chip.win{{border-color:#335844;color:#9fcaae}}.form-chip.loss{{border-color:#57363c;color:#d69ba2}}.form-chip.draw{{border-color:#5b5238;color:#cfbd8e}}
.match-row{{display:grid;grid-template-columns:44px 30px 1fr auto;gap:9px;align-items:center;padding:9px 0;border-top:1px solid #202832}}.match-row time{{font-size:8px;color:#687586}}.result-mark{{display:grid;place-items:center;width:26px;height:23px;border-radius:6px;font-size:7px;border:1px solid #29333e}}.result-mark.win{{color:#9fcaae;border-color:#335844}}.result-mark.loss{{color:#d69ba2;border-color:#57363c}}.match-row b{{display:block;font-size:10px}}.match-row em,.match-row a{{color:#687586;font-size:8px;font-style:normal;text-decoration:none}}.coach-note{{padding:10px 0;border-top:1px solid #202832}}.coach-note time{{display:block;color:#667484;font-size:8px}}.coach-note p{{margin:5px 0 0;color:#c1c9d3;font-size:10px;line-height:1.55}}.timeline-card{{border-left:2px solid #7c8793;padding:10px 12px;background:#090d12;border-radius:0 11px 11px 0;margin-top:8px}}.timeline-card.current{{border-left-color:#2a86d9}}.timeline-card b{{display:block;font-size:11px}}.timeline-card span{{display:block;color:#6f7d8e;font-size:9px;margin-top:4px}}.footer-note{{display:flex;justify-content:space-between;margin-top:20px;padding-top:15px;border-top:1px solid #1e252e;color:#596575;font-size:9px}}
@media(max-width:900px){{.env-grid{{grid-template-columns:1fr}}.coach-focus-grid{{grid-template-columns:1fr 1fr}}.coach-focus-grid .count{{grid-column:1/-1}}}}@media(max-width:620px){{.env-hero{{grid-template-columns:1fr}}.env-code{{text-align:left}}.coach-focus-grid{{grid-template-columns:1fr}}.coach-focus-grid .count{{grid-column:auto}}}}
</style></head><body><main class="hub-shell">{topbar("mine")}
<section class="env-hero"><div><div class="hub-eyebrow">Мой хоккей</div><h1>Моя хоккейная среда</h1><p>Тренер, команды и люди вокруг моего хоккея — без превращения страницы в ещё один спортивный scoreboard.</p></div><div class="env-code"><b>ЛЮДИ / КОМАНДЫ / КОНТЕКСТ</b>личный хоккейный круг</div></section>
{_tabs("environment")}
<article class="coach-card"><div class="coach-kicker">Мой тренер</div><h2>Артём Кунаев</h2><div class="coach-role">тренер · главный тренер «Эскулапа»</div><div class="coach-focus-grid">
<div class="focus-box"><span>Текущий фокус</span><b>{_esc(latest.get("text") if latest else "Новый комментарий пока не записан.")}</b><em>{_date_label(latest.get("date")) if latest else "—"}</em></div>
<div class="focus-box"><span>Предыдущий устойчивый фокус</span><b>{_esc(previous.get("text") if previous else "История ещё только собирается.")}</b><em>{_date_label(previous.get("date")) if previous else "—"}</em></div>
<div class="focus-box count"><span>Тренировок</span><strong>{len(sessions)}</strong><em>в личной истории</em></div>
</div></article>
<section class="env-grid"><div>
<article class="hub-card panel"><div class="team-head"><div class="hub-eyebrow">Текущая команда Тёмы</div><h2>Эскулап</h2><p>СПбХЛ · публичные данные</p></div><div class="team-meta">{_esc(team_meta)}</div>{env._next_game_html(summary["current"])}
<div class="section-title" style="margin-top:15px"><h2>Форма</h2><span>последние матчи</span></div><div class="form-line">{env._form_html(finished)}</div>
<div class="section-title"><h2>Последние матчи</h2><span>3 последних</span></div>{env._recent_games_html(finished)}</article>
</div><aside>
<article class="hub-card panel"><div class="section-title"><h2>Комментарии Тёмы</h2><span>история</span></div>{_coach_note_rows(notes)}</article>
<article class="hub-card panel" style="margin-top:14px"><div class="section-title"><h2>Команды Тёмы</h2><span>контекст</span></div><div class="timeline-card current"><b>Эскулап</b><span>текущая команда · СПбХЛ</span></div><div class="timeline-card"><b>Сборная врачей</b><span>предыдущая команда · историю дополним по надёжным источникам</span></div></article>
</aside></section>
<footer class="footer-note"><span>Hockey Hub · Моя хоккейная среда</span><span>v{VERSION}</span></footer></main></body></html>'''


env.render_environment = render_environment_v56


# ---------------------------------------------------------------------------
# Closet
# ---------------------------------------------------------------------------

GEAR_CATEGORIES = ["Защита","Коньки","Клюшки","Одежда","Сумки и аксессуары","Расходники","Спортпит","Атрибутика","Другое"]
GEAR_CONDITIONS = ["новое","в игре","есть износ","нужен ремонт","на замену"]
WISH_CATEGORIES = ["Экипировка","Расходники","Спортпит","Атрибутика","Другое"]


def _gear_cards_v56(items: list[dict]) -> str:
    from collections import defaultdict
    groups = defaultdict(list)
    for item in items:
        groups[item.get("category") or "Другое"].append(item)
    if not groups:
        return '<div class="empty-state">Шкаф пока пуст.</div>'
    blocks=[]
    for category in sorted(groups):
        cards=[]
        for item in groups[category]:
            brand = " · ".join(x for x in (item.get("brand"),item.get("model")) if x) or "Без бренда/модели"
            condition=item.get("condition") or "в игре"
            cls=closet_v48._condition_class(condition)
            details=[]
            if item.get("color"): details.append(f"цвет: {_esc(item.get('color'))}")
            if item.get("purchase_price") is not None: details.append(f"цена: {closet_v48._money(item.get('purchase_price'))}")
            cards.append(f'''<article class="gear-card {cls}"><div class="gear-top"><span class="condition-dot"></span><span>{_esc(condition)}</span></div><h3>{_esc(item.get("name"))}</h3><div class="brand-line">{_esc(brand)}</div><div class="gear-meta">{' · '.join(details) if details else 'параметры пока не заполнены'}</div>{f'<div class="service-line"><span>Обслуживание</span><b>{_date_label(item.get("next_service_on"))}</b></div>' if item.get("next_service_on") else ''}{f'<p>{_esc(item.get("notes"))}</p>' if item.get("notes") else ''}
<details class="closet-edit"><summary>Редактировать</summary><form method="post" action="/my-hockey/closet/item/{item["id"]}/edit">
<div class="two"><label>Категория<select name="category">{_selected(GEAR_CATEGORIES,item.get("category") or "Другое")}</select></label><label>Название<input name="name" value="{_esc(item.get("name"))}" required></label></div><div class="two"><label>Бренд<input name="brand" value="{_esc(item.get("brand"))}"></label><label>Модель<input name="model" value="{_esc(item.get("model"))}"></label></div><div class="two"><label>Цвет<input name="color" value="{_esc(item.get("color"))}"></label><label>Состояние<select name="condition">{_selected(GEAR_CONDITIONS,condition)}</select></label></div><div class="two"><label>Куплено<input type="date" name="purchased_on" value="{_esc(item.get("purchased_on"))}"></label><label>Цена<input name="purchase_price" value="{_esc(item.get("purchase_price"))}"></label></div><label>Следующее обслуживание<input type="date" name="next_service_on" value="{_esc(item.get("next_service_on"))}"></label><label>Заметка<textarea name="notes">{_esc(item.get("notes"))}</textarea></label><button class="edit-save">Сохранить</button><button class="danger-link" formaction="/my-hockey/closet/item/{item["id"]}/delete" formmethod="post" onclick="return confirm('Удалить вещь из шкафа?')">Удалить</button></form></details>
</article>''')
        blocks.append(f'<section class="gear-group"><div class="group-head"><h2>{_esc(category)}</h2><span>{len(cards)}</span></div><div class="gear-grid">{"".join(cards)}</div></section>')
    return "".join(blocks)


def _wishlist_cards_v56(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty-state compact">Wishlist пока пуст.</div>'
    cards=[]
    for row in rows:
        target,current=row.get("target_price"),row.get("current_price")
        link=closet_v48._safe_url(row.get("url"))
        title=f'<a href="{html.escape(link,quote=True)}" target="_blank" rel="noopener">{_esc(row.get("name"))} ↗</a>' if link else _esc(row.get("name"))
        cards.append(f'''<article class="wish-card"><div class="wish-kicker">{_esc(row.get("category"))}{' · '+_esc(row.get("store")) if row.get("store") else ''}</div><h3>{title}</h3><div class="wish-brand">{_esc(row.get("brand") or "бренд не указан")}</div><div class="price-grid"><div><span>Сейчас</span><b>{closet_v48._money(current)}</b></div><div><span>Цель</span><b>{closet_v48._money(target)}</b></div></div>{f'<p>{_esc(row.get("notes"))}</p>' if row.get("notes") else ''}
<details class="closet-edit"><summary>Редактировать</summary><form method="post" action="/my-hockey/closet/wishlist/{row["id"]}/edit"><div class="two"><label>Категория<select name="category">{_selected(WISH_CATEGORIES,row.get("category") or "Другое")}</select></label><label>Название<input name="name" value="{_esc(row.get("name"))}" required></label></div><label>Бренд<input name="brand" value="{_esc(row.get("brand"))}"></label><div class="two"><label>Текущая цена<input name="current_price" value="{_esc(current)}"></label><label>Купить при<input name="target_price" value="{_esc(target)}"></label></div><div class="two"><label>Магазин<input name="store" value="{_esc(row.get("store"))}"></label><label>Ссылка<input type="url" name="url" value="{_esc(row.get("url"))}"></label></div><label>Заметка<textarea name="notes">{_esc(row.get("notes"))}</textarea></label><button class="edit-save">Сохранить</button><button class="danger-link" formaction="/my-hockey/closet/wishlist/{row["id"]}/delete" formmethod="post" onclick="return confirm('Удалить позицию из wishlist?')">Удалить</button></form></details></article>''')
    return "".join(cards)


closet_v48._gear_cards = _gear_cards_v56
closet_v48._wishlist_cards = _wishlist_cards_v56
_base_closet_renderer = closet_v48.render_closet


def render_closet_v56(saved: str | None = None, error: str | None = None) -> str:
    page=_base_closet_renderer(saved=saved,error=error)
    soup=BeautifulSoup(page,"html.parser")
    data=CLOSET.load(); items=data.get("items") or []; wishlist=data.get("wishlist") or []
    eyebrow=soup.select_one(".closet-hero .hub-eyebrow")
    if eyebrow: eyebrow.string="Мой хоккей"
    old_tabs=soup.select_one(".mine-tabs")
    if old_tabs: old_tabs.replace_with(BeautifulSoup(_tabs("closet"),"html.parser"))
    ready=soup.select_one(".closet-flash.ready")
    if ready: ready.decompose()
    stats=soup.select_one(".closet-stats")
    if stats: stats.decompose()
    # Remove static style declaration and developer roadmap note.
    for article in soup.select(".side-stack article"):
        h2=article.find("h2")
        if h2 and h2.get_text(" ",strip=True)=="Стиль комплекта": article.decompose()
    note=soup.select_one(".monitor-note")
    if note: note.decompose()

    today=datetime.now(core.MOSCOW).date()
    alerts=[]
    for item in items:
        condition=(item.get("condition") or "").lower()
        if any(x in condition for x in ("износ","ремонт","замен")):
            alerts.append(f'{_esc(item.get("name"))} · {_esc(item.get("condition"))}')
            continue
        if item.get("next_service_on"):
            try:
                due=datetime.strptime(item["next_service_on"],"%Y-%m-%d").date()
                if due <= today+timedelta(days=30):
                    alerts.append(f'{_esc(item.get("name"))} · обслуживание {_date_label(item.get("next_service_on"))}')
            except Exception: pass
    hit=[]
    for w in wishlist:
        if w.get("current_price") is not None and w.get("target_price") is not None and w["current_price"] <= w["target_price"]:
            hit.append(f'{_esc(w.get("name"))} · {closet_v48._money(w.get("current_price"))}')
    now_html='<section class="closet-now"><div><span>СЕЙЧАС</span><b>'+(' · '.join(alerts[:3]) if alerts else 'Экипировка не требует внимания')+'</b></div><div><span>ЦЕНЫ</span><b>'+(' · '.join(hit[:2]) if hit else 'Нет срабатываний wishlist')+'</b></div></section>'
    anchor=soup.select_one(".closet-layout")
    if anchor: anchor.insert_before(BeautifulSoup(now_html,"html.parser"))
    main=soup.find("main")
    if main:
        footer=soup.new_tag("footer"); footer["class"]=["closet-footer"]; footer.string=f"Hockey Hub · Хоккейный шкаф · v{VERSION}"; main.append(footer)
    style=soup.find("style")
    if style: style.append(r"""
/* v0.56 closet = action, not database counters */
.closet-now{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.closet-now>div{padding:11px 13px;border:1px solid #263441;border-radius:11px;background:#0a1016}.closet-now span{display:block;color:#647588;font-size:8px;letter-spacing:.1em}.closet-now b{display:block;color:#c1ccd7;font-size:10px;margin-top:5px}
.closet-edit{margin-top:11px;border-top:1px solid #202833;padding-top:8px}.closet-edit summary{cursor:pointer;color:#68839f;font-size:8px}.closet-edit form{margin-top:9px;padding:10px;border:1px solid #293744;border-radius:10px;background:#080d12}.edit-save{border:1px solid #53687c!important;background:#111b24!important;color:#dce6ef!important}.danger-link{border:0!important;background:transparent!important;color:#8b5960!important;text-align:left;padding:4px 0!important}.closet-footer{margin-top:20px;padding-top:14px;border-top:1px solid #1e252e;color:#596575;font-size:9px}
@media(max-width:760px){.closet-now{grid-template-columns:1fr}}
""")
    return str(soup)


closet_v48.render_closet=render_closet_v56


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

MONTHS = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}


def _memory_date(raw: str | None) -> str:
    try:
        d=datetime.strptime(raw or "","%Y-%m-%d").date()
        return f"{d.day} {MONTHS[d.month]} {d.year}"
    except Exception:
        return raw or "—"


def _memory_gallery(item: dict) -> str:
    photos=item.get("photos") or []
    if not photos: return ""
    return '<div class="memory-photos">'+"".join(
        f'''<figure style="--photo-bg:url('/my-hockey/memory/photo/{int(p["id"])}')"><a href="/my-hockey/memory/photo/{int(p["id"])}" target="_blank"><img loading="lazy" src="/my-hockey/memory/photo/{int(p["id"])}" alt=""></a></figure>'''
        for p in photos
    )+"</div>"


def _memory_edit(item: dict) -> str:
    photos=item.get("photos") or []
    current="".join(
        f'''<label class="edit-photo"><img src="/my-hockey/memory/photo/{int(p["id"])}"><span><input type="checkbox" name="delete_photo_ids" value="{int(p["id"])}"> удалить</span></label>'''
        for p in photos
    ) or '<div class="empty">Фотографий пока нет.</div>'
    hs="" if item.get("home_score") is None else item.get("home_score"); aws="" if item.get("away_score") is None else item.get("away_score")
    return f'''<details class="memory-edit"><summary>Редактировать воспоминание</summary><form method="post" action="/my-hockey/memory/{item["id"]}/edit" enctype="multipart/form-data">
<div class="two"><label>Дата<input type="date" name="match_date" value="{_esc(item.get("match_date"))}" required></label><label>Турнир<input name="competition" value="{_esc(item.get("competition"))}"></label></div><div class="two"><label>Хозяева<input name="home_team" value="{_esc(item.get("home_team"))}" required></label><label>Гости<input name="away_team" value="{_esc(item.get("away_team"))}" required></label></div><div class="two"><label>Счёт хозяев<input type="number" min="0" name="home_score" value="{_esc(hs)}"></label><label>Счёт гостей<input type="number" min="0" name="away_score" value="{_esc(aws)}"></label></div><label>Арена<input name="arena" value="{_esc(item.get("arena"))}"></label><div class="two"><label>Сектор<input name="sector" value="{_esc(item.get("sector"))}"></label><label>Место<input name="seat" value="{_esc(item.get("seat"))}"></label></div><label>С кем ходил<input name="companions" value="{_esc(item.get("companions"))}"></label><label>Что хочется запомнить<textarea name="note">{_esc(item.get("note"))}</textarea></label>
<div class="edit-photo-title">Фотографии · {len(photos)}/{MAX_MEMORY_PHOTOS}</div><div class="edit-photo-grid">{current}</div><label>Добавить ещё<input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple></label><button class="save">Сохранить изменения</button><button class="danger-link" formaction="/my-hockey/memory/{item["id"]}/delete" formmethod="post" onclick="return confirm('Удалить воспоминание целиком?')">Удалить воспоминание</button></form></details>'''


def _memory_cards(matches: list[dict]) -> str:
    if not matches:
        return '<section class="memory-empty"><div>✦</div><h2>Здесь пока тихо.</h2><p>Первый сохранённый матч станет началом твоей хоккейной хроники.</p><a href="#new-memory">+ Сохранить первое воспоминание</a></section>'
    out=[]
    for item in matches:
        score="" if item.get("home_score") is None or item.get("away_score") is None else f'{item["home_score"]}:{item["away_score"]}'
        place=" · ".join(x for x in [item.get("arena"),f'сектор {item.get("sector")}' if item.get("sector") else "",f'место {item.get("seat")}' if item.get("seat") else ""] if x)
        meta=" · ".join(_esc(x) for x in [item.get("competition"),score,item.get("companions")] if x)
        out.append(f'''<article class="memory-entry" id="memory-{item["id"]}"><div class="memory-date">{_esc(_memory_date(item.get("match_date")))}</div><div class="memory-body"><div class="kicker">{_esc(item.get("competition") or "Хоккейный вечер")} · {_esc(item.get("season"))}</div><div class="match-title"><h2>{_esc(item.get("home_team"))} <span>—</span> {_esc(item.get("away_team"))}</h2>{f'<strong>{score}</strong>' if score else ''}</div>{f'<div class="place">{_esc(place)}</div>' if place else ''}{_memory_gallery(item)}<p class="memory-note">{_esc(item.get("note") or "Пока без заметки — только сам факт этого вечера.")}</p><div class="memory-meta">{meta}</div>{_memory_edit(item)}</div></article>''')
    return "".join(out)


def render_memory_v56(season: str | None=None,saved:int=0,error:str|None=None)->str:
    all_data=MEMORY.load(); seasons=all_data.get("seasons") or []; today=datetime.now(core.MOSCOW).date(); current=season_for_date(today); selected=(season or "").strip() or (seasons[0] if seasons else current); data=MEMORY.load(selected); matches=data.get("matches") or []
    season_values=sorted(set([*seasons,current]),reverse=True)
    chips="".join(f'<a class="season-chip{" active" if x==selected else ""}" href="/my-hockey/memory?season={quote(x)}">{_esc(x)}</a>' for x in season_values)
    flash=f'<div class="memory-flash error">{_esc(error)}</div>' if error else ('<div class="memory-flash success">Воспоминание сохранено.</div>' if saved else '')
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Память · Hockey Hub</title><style>
{COMMON_CSS}{TABS_CSS}
body{{background:radial-gradient(circle at 84% 3%,rgba(42,134,217,.06),transparent 27%),#05070b}}.memory-hero{{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}.memory-hero h1{{font-size:52px;margin:9px 0 10px}}.memory-hero p{{margin:0;color:#9aa4b2;font-size:15px}}.memory-code{{text-align:right;color:#67778a;font-size:9px;letter-spacing:.1em}}.memory-code b{{display:block;color:#cfd6de;font-size:12px}}.season-bar{{display:flex;justify-content:space-between;align-items:center;margin:8px 0 20px}}.season-chip{{display:inline-block;text-decoration:none;border:1px solid #27323e;border-radius:999px;padding:6px 10px;color:#758396;font-size:9px;margin-right:5px}}.season-chip.active{{color:#dce5ed;border-color:#396487}}.season-bar span{{color:#5f6e7f;font-size:9px}}.memory-flash{{padding:10px 12px;border-radius:10px;border:1px solid #365541;color:#bcd5c3;margin-bottom:12px;font-size:10px}}.memory-flash.error{{border-color:#61363d;color:#efb4ba}}
.memory-layout{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(310px,.55fr);gap:22px;align-items:start}}.memory-entry{{display:grid;grid-template-columns:128px 1fr;gap:24px;padding:8px 0 34px}}.memory-date{{text-align:right;color:#8794a4;font-size:10px;padding-top:8px}}.memory-body{{border:1px solid #25303b;background:linear-gradient(180deg,#0f151b,#090d12);border-radius:17px;padding:20px 22px}}.kicker{{color:#66778b;font-size:8px;text-transform:uppercase}}.match-title{{display:flex;justify-content:space-between;gap:16px;margin-top:8px}}.match-title h2{{margin:0;font-size:22px}}.match-title h2 span{{color:#536274;font-weight:400}}.match-title strong{{font-size:25px}}.place{{color:#8290a0;font-size:10px;margin-top:9px}}.memory-photos{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:16px}}.memory-photos figure{{position:relative;margin:0;aspect-ratio:4/3;overflow:hidden;border:1px solid #26323e;border-radius:11px;isolation:isolate}}.memory-photos figure:before{{content:"";position:absolute;inset:-10px;background-image:var(--photo-bg);background-size:cover;background-position:center;filter:blur(18px) brightness(.58);transform:scale(1.12);z-index:0}}.memory-photos a{{position:relative;z-index:2;display:block;width:100%;height:100%}}.memory-photos img{{width:100%;height:100%;object-fit:contain}}.memory-note{{margin:18px 0 0;padding-left:15px;border-left:2px solid #304b65;color:#b9c2cc;font-size:12px;line-height:1.7}}.memory-meta{{margin-top:16px;padding-top:11px;border-top:1px solid #1f2832;color:#657486;font-size:8px}}.memory-edit{{margin-top:12px;color:#7895b0;font-size:8px}}.memory-edit summary{{cursor:pointer}}.memory-edit form{{display:grid;gap:8px;margin-top:10px;padding:12px;border:1px solid #283542;border-radius:11px;background:#080d12}}.memory-edit label,.create-form label{{display:grid;gap:5px;color:#8493a4;font-size:8px}}input,textarea,select{{width:100%;border:1px solid #303c49;border-radius:8px;background:#070b0f;color:#e8edf2;padding:8px 9px}}textarea{{min-height:90px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}button.save{{border:1px solid #8995a2;border-radius:8px;background:#d1d9e1;color:#0b0f14;padding:9px;font-weight:800}}.danger-link{{border:0;background:transparent;color:#8b5960;text-align:left;padding:4px 0;cursor:pointer}}.edit-photo-title{{color:#8295a7;font-size:8px;text-transform:uppercase}}.edit-photo-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}}.edit-photo{{border:1px solid #2b3947;border-radius:9px;overflow:hidden}}.edit-photo img{{width:100%;aspect-ratio:4/3;object-fit:cover}}.edit-photo span{{display:flex;gap:5px;padding:6px}}.edit-photo input{{width:auto}}.memory-empty{{min-height:360px;display:flex;flex-direction:column;justify-content:center;border:1px dashed #26313d;border-radius:18px;padding:42px}}.memory-empty h2{{font-size:24px;margin:10px 0}}.memory-empty p{{color:#788697;font-size:11px}}.memory-empty a{{color:#a9bdd0;font-size:9px}}.create-card{{border:1px solid #293540;border-radius:16px;background:#0d1218;overflow:hidden;position:sticky;top:18px}}.create-card summary{{cursor:pointer;list-style:none;padding:18px;font-weight:750}}.create-card summary:after{{content:"＋";float:right;color:#5f9bd0}}.create-card[open] summary:after{{content:"−"}}.create-form{{display:grid;gap:9px;padding:16px 18px;border-top:1px solid #202a34}}.memory-footer{{margin-top:24px;padding-top:14px;border-top:1px solid #1e252e;color:#596575;font-size:9px}}
@media(max-width:900px){{.memory-layout{{grid-template-columns:1fr}}.create-card{{position:static}}}}@media(max-width:680px){{.memory-hero{{grid-template-columns:1fr}}.memory-code{{text-align:left}}.memory-entry{{display:block}}.memory-date{{text-align:left;padding-bottom:8px}}.memory-photos{{grid-template-columns:1fr 1fr}}.two,.edit-photo-grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main class="hub-shell">{topbar("mine")}<section class="memory-hero"><div><div class="hub-eyebrow">Мой хоккей</div><h1>Память</h1><p>Матчи проходят. Здесь остаётся то, что хочется помнить.</p></div><div class="memory-code"><b>ВЕЧЕРА / ЛЮДИ / МЕСТА</b>билеты · фотографии · несколько строк о вечере</div></section>{_tabs("memory")}{flash}<section class="season-bar"><div>{chips}</div><span>хоккейная глава · {_esc(selected)}</span></section><section class="memory-layout"><div>{_memory_cards(matches)}</div><aside id="new-memory"><details class="create-card"{' open' if error else ''}><summary>Добавить воспоминание</summary><form class="create-form" method="post" action="/my-hockey/memory" enctype="multipart/form-data"><div class="two"><label>Дата<input type="date" name="match_date" value="{today.isoformat()}" required></label><label>Турнир<input name="competition" placeholder="КХЛ / ВХЛ / ..."></label></div><div class="two"><label>Хозяева<input name="home_team" required></label><label>Гости<input name="away_team" required></label></div><div class="two"><label>Счёт хозяев<input type="number" min="0" name="home_score"></label><label>Счёт гостей<input type="number" min="0" name="away_score"></label></div><label>Арена<input name="arena"></label><div class="two"><label>Сектор<input name="sector"></label><label>Место<input name="seat"></label></div><label>С кем ходил<input name="companions"></label><label>Что хочется запомнить<textarea name="note"></textarea></label><label>Фотографии<input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple></label><button class="save">Сохранить воспоминание</button></form></details></aside></section><footer class="memory-footer">Hockey Hub · Память · v{VERSION}</footer></main></body></html>'''


# ---------------------------------------------------------------------------
# Home personal briefing
# ---------------------------------------------------------------------------

_HOME_AUTH: ContextVar[bool]=ContextVar("v56_home_auth",default=False)
_base_home_renderer=core.render_page


def _home_personal_html()->str:
    pdata=PERSONAL.load(); ddata=DEV.load(); sessions=sorted(pdata.get("sessions") or [],key=lambda x:x.get("date",""),reverse=True); notes=sorted(pdata.get("coach_notes") or [],key=lambda x:x.get("date",""),reverse=True); goals=_active(ddata.get("goals") or []); hw=_active(ddata.get("homework") or [])
    latest=sessions[0] if sessions else {}; focus=notes[0] if notes else {}
    dated=[x for x in goals if x.get("target_date")]; checkpoint=sorted(dated,key=lambda x:x.get("target_date"))[0] if dated else (goals[0] if goals else None)
    return f'''<div class="home-personal-grid"><a class="home-personal-item primary" href="/my-hockey"><span>ПОСЛЕДНЯЯ ТРЕНИРОВКА</span><b>{_esc(latest.get("type") or "Пока нет записей")}</b><em>{_date_label(latest.get("date")) if latest else "—"}{f' · нагрузка {latest.get("load")}/10' if latest.get("load") is not None else ''}</em></a><a class="home-personal-item" href="/my-hockey/environment"><span>ФОКУС ТЁМЫ</span><b>{_esc(focus.get("text") or "Новый комментарий пока не записан")}</b></a><a class="home-personal-item counter" href="/my-hockey#development"><span>В РАБОТЕ</span><strong>{len(goals)} <i>целей</i> · {len(hw)} <i>ДЗ</i></strong></a><a class="home-personal-item" href="/my-hockey#development"><span>КОНТРОЛЬНАЯ ТОЧКА</span><b>{_esc(checkpoint.get("title") if checkpoint else "Пока не задана")}</b></a></div>'''


def render_home_v56()->str:
    page=_base_home_renderer(); soup=BeautifulSoup(page,"html.parser")
    eye=soup.select_one(".hero .eyebrow")
    if eye: eye.string="Hockey Hub · персональный briefing"
    if _HOME_AUTH.get():
        card=soup.select_one("article.personal-box")
        if card:
            h=card.select_one(".world-title h3")
            if h: h.string="Мой хоккей"
            old=card.select_one(".esk-line")
            if old: old.replace_with(BeautifulSoup(_home_personal_html(),"html.parser"))
    footer=soup.select_one(".footer")
    if footer:
        spans=footer.find_all("span")
        if spans: spans[-1].string=f"Hockey Hub · v{VERSION}"
    style=soup.find("style")
    if style: style.append(r"""
.home-personal-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:8px}.home-personal-item{display:block;padding:10px 11px;background:#090f15;border:1px solid #263443;border-radius:10px;text-decoration:none}.home-personal-item.primary{box-shadow:inset 2px 0 #2a86d9}.home-personal-item span{display:block;color:#64778c;font-size:7px;letter-spacing:.08em;margin-bottom:5px}.home-personal-item b{display:block;color:#d9e0e8;font-size:9px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.home-personal-item em{display:block;color:#637386;font-size:7px;font-style:normal;margin-top:4px}.home-personal-item.counter strong{font-size:15px}.home-personal-item.counter i{font-size:8px;font-style:normal;color:#76879a}@media(max-width:560px){.home-personal-grid{grid-template-columns:1fr}}
""")
    return str(soup)


core.render_page=render_home_v56


@core.app.middleware("http")
async def home_auth_context(request,call_next):
    authenticated=False
    if request.url.path=="/":
        try: authenticated=auth_v49.verify_session_token(request.cookies.get(auth_v49.COOKIE_NAME))
        except Exception: authenticated=False
    token=_HOME_AUTH.set(authenticated)
    try: response=await call_next(request)
    finally: _HOME_AUTH.reset(token)
    if request.url.path=="/" and authenticated:
        response.headers["Cache-Control"]="private, no-store"; response.headers["Vary"]="Cookie"
    return response


# ---------------------------------------------------------------------------
# Photo processing
# ---------------------------------------------------------------------------

def _process_photo(raw:bytes)->dict:
    if len(raw)>12*1024*1024: raise ValueError("Один файл не должен быть больше 12 МБ")
    Image.MAX_IMAGE_PIXELS=40_000_000
    with Image.open(BytesIO(raw)) as source:
        image=ImageOps.exif_transpose(source)
        if image.mode not in ("RGB","RGBA"): image=image.convert("RGB")
        if image.mode=="RGBA":
            bg=Image.new("RGB",image.size,(8,11,15)); bg.paste(image,mask=image.getchannel("A")); image=bg
        image.thumbnail((1800,1800),Image.Resampling.LANCZOS)
        out=BytesIO(); image.save(out,format="WEBP",quality=82,method=6)
        return {"mime_type":"image/webp","image_data":out.getvalue(),"width":image.width,"height":image.height}


async def _prepare_photos(files:list[UploadFile]|None)->list[dict]:
    selected=[f for f in (files or []) if f and (f.filename or "").strip()]
    if len(selected)>MAX_MEMORY_PHOTOS: raise ValueError(f"Не больше {MAX_MEMORY_PHOTOS} фотографий")
    allowed={"image/jpeg","image/png","image/webp"}; result=[]
    for upload in selected:
        if (upload.content_type or "").lower() not in allowed: raise ValueError(f"Неподдерживаемый формат: {upload.filename}")
        raw=await upload.read()
        if not raw: raise ValueError(f"Пустой файл: {upload.filename}")
        try: photo=_process_photo(raw)
        except ValueError: raise
        except Exception: raise ValueError(f"Не удалось прочитать изображение «{upload.filename}»")
        photo["original_name"]=upload.filename or ""; result.append(photo)
    return result


# ---------------------------------------------------------------------------
# Routes: development / sessions / closet / memory
# ---------------------------------------------------------------------------

@core.app.post("/my-hockey/session/{session_id}/edit")
def edit_session(session_id:int,session_date:str=Form(...),session_type:str=Form("Ледовая тренировка"),focus:str=Form(""),wellbeing:int|None=Form(None),load:int|None=Form(None),note:str=Form(""),homework:str=Form(""),coach_note:str=Form(""),lap_1:str=Form(""),lap_2:str=Form("")):
    try:
        day=_date(session_date); focus_items=[x.strip() for x in focus.replace(";",",").split(",") if x.strip()]
        PERSONAL.update_session(session_id,session_date=day,session_type=session_type,focus=focus_items,wellbeing=wellbeing,load=load,note=note,homework=homework,coach_note=coach_note,lap_1=_num(lap_1),lap_2=_num(lap_2))
        DEV.sync_session_homework(session_id,homework,f"Тренировка {_date_label(session_date)}")
        return RedirectResponse("/my-hockey",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey",exc)


@core.app.post("/my-hockey/session/{session_id}/delete")
def delete_session(session_id:int):
    try:
        DEV.sync_session_homework(session_id,"","")
        PERSONAL.delete_session(session_id)
        return RedirectResponse("/my-hockey",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey",exc)


@core.app.post("/my-hockey/development/skill")
def update_skill(skill_key:str=Form(...),level:str=Form(""),note:str=Form("")):
    try:
        DEV.update_skill(skill_key,int(level) if level.strip() else None,note); return RedirectResponse("/my-hockey#development",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey",exc,"#development")


@core.app.post("/my-hockey/development/goal")
def add_goal(title:str=Form(...),category:str=Form(""),target_date:str=Form(""),note:str=Form("")):
    try: DEV.add_goal(title,category,_date(target_date),note); return RedirectResponse("/my-hockey#development",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey",exc,"#development")


@core.app.post("/my-hockey/development/homework")
def add_homework(text:str=Form(...),source:str=Form(""),due_date:str=Form("")):
    try: DEV.add_homework(text,source,_date(due_date)); return RedirectResponse("/my-hockey#development",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey",exc,"#development")


@core.app.post("/my-hockey/development/goal/{item_id}/edit")
def edit_goal(item_id:int,title:str=Form(...),category:str=Form(""),target_date:str=Form(""),note:str=Form("")):
    DEV.update_goal(item_id,title,category,_date(target_date),note); return RedirectResponse("/my-hockey#development",status_code=303)


@core.app.post("/my-hockey/development/homework/{item_id}/edit")
def edit_homework(item_id:int,text:str=Form(...),source:str=Form(""),due_date:str=Form("")):
    DEV.update_homework(item_id,text,source,_date(due_date)); return RedirectResponse("/my-hockey#development",status_code=303)


@core.app.post("/my-hockey/development/goal/{item_id}/done")
def goal_done(item_id:int): DEV.set_goal_done(item_id,True); return RedirectResponse("/my-hockey#development",status_code=303)
@core.app.post("/my-hockey/development/goal/{item_id}/reopen")
def goal_reopen(item_id:int): DEV.set_goal_done(item_id,False); return RedirectResponse("/my-hockey#development",status_code=303)
@core.app.post("/my-hockey/development/goal/{item_id}/delete")
def goal_delete(item_id:int): DEV.delete_goal(item_id); return RedirectResponse("/my-hockey#development",status_code=303)
@core.app.post("/my-hockey/development/homework/{item_id}/done")
def homework_done(item_id:int): DEV.set_homework_done(item_id,True); return RedirectResponse("/my-hockey#development",status_code=303)
@core.app.post("/my-hockey/development/homework/{item_id}/reopen")
def homework_reopen(item_id:int): DEV.set_homework_done(item_id,False); return RedirectResponse("/my-hockey#development",status_code=303)
@core.app.post("/my-hockey/development/homework/{item_id}/delete")
def homework_delete(item_id:int): DEV.delete_homework(item_id); return RedirectResponse("/my-hockey#development",status_code=303)


@core.app.post("/my-hockey/closet/item/{item_id}/edit")
def edit_gear(item_id:int,category:str=Form("Другое"),name:str=Form(...),brand:str=Form(""),model:str=Form(""),color:str=Form(""),condition:str=Form("в игре"),purchased_on:str=Form(""),purchase_price:str=Form(""),next_service_on:str=Form(""),notes:str=Form("")):
    CLOSET.update_item(item_id,category=category,name=name,brand=brand,model=model,color=color,condition=condition,purchased_on=_date(purchased_on),purchase_price=purchase_price,next_service_on=_date(next_service_on),notes=notes); return RedirectResponse("/my-hockey/closet",status_code=303)
@core.app.post("/my-hockey/closet/item/{item_id}/delete")
def delete_gear(item_id:int): CLOSET.delete_item(item_id); return RedirectResponse("/my-hockey/closet",status_code=303)
@core.app.post("/my-hockey/closet/wishlist/{item_id}/edit")
def edit_wish(item_id:int,category:str=Form("Другое"),name:str=Form(...),brand:str=Form(""),target_price:str=Form(""),current_price:str=Form(""),store:str=Form(""),url:str=Form(""),notes:str=Form("")):
    CLOSET.update_wishlist(item_id,category=category,name=name,brand=brand,target_price=target_price,current_price=current_price,store=store,url=url,notes=notes); return RedirectResponse("/my-hockey/closet",status_code=303)
@core.app.post("/my-hockey/closet/wishlist/{item_id}/delete")
def delete_wish(item_id:int): CLOSET.delete_wishlist(item_id); return RedirectResponse("/my-hockey/closet",status_code=303)


@core.app.get("/my-hockey/memory",response_class=HTMLResponse)
def memory_page(season:str|None=None,saved:int=0,error:str|None=None): return render_memory_v56(season,saved,error)


@core.app.post("/my-hockey/memory")
async def create_memory(match_date:str=Form(...),competition:str=Form(""),home_team:str=Form(...),away_team:str=Form(...),home_score:str=Form(""),away_score:str=Form(""),arena:str=Form(""),sector:str=Form(""),seat:str=Form(""),companions:str=Form(""),note:str=Form(""),photos:list[UploadFile]|None=File(None)):
    try:
        day=_date(match_date); prepared=await _prepare_photos(photos); item_id=MEMORY.create_match_with_photos(match_date=day,competition=competition,home_team=home_team,away_team=away_team,home_score=int(home_score) if home_score.strip() else None,away_score=int(away_score) if away_score.strip() else None,arena=arena,sector=sector,seat=seat,companions=companions,note=note,photos=prepared,max_photos=MAX_MEMORY_PHOTOS); season=season_for_date(day); return RedirectResponse(f"/my-hockey/memory?season={quote(season)}&saved=1#memory-{item_id}",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey/memory",exc,"#new-memory")


@core.app.post("/my-hockey/memory/{item_id}/edit")
async def edit_memory(item_id:int,match_date:str=Form(...),competition:str=Form(""),home_team:str=Form(...),away_team:str=Form(...),home_score:str=Form(""),away_score:str=Form(""),arena:str=Form(""),sector:str=Form(""),seat:str=Form(""),companions:str=Form(""),note:str=Form(""),delete_photo_ids:list[int]|None=Form(None),photos:list[UploadFile]|None=File(None)):
    try:
        day=_date(match_date); prepared=await _prepare_photos(photos); MEMORY.update_match_with_photos(item_id,match_date=day,competition=competition,home_team=home_team,away_team=away_team,home_score=int(home_score) if home_score.strip() else None,away_score=int(away_score) if away_score.strip() else None,arena=arena,sector=sector,seat=seat,companions=companions,note=note,delete_photo_ids=delete_photo_ids or [],photos=prepared,max_photos=MAX_MEMORY_PHOTOS); season=season_for_date(day); return RedirectResponse(f"/my-hockey/memory?season={quote(season)}#memory-{item_id}",status_code=303)
    except Exception as exc: return _safe_redirect_error("/my-hockey/memory",exc,f"#memory-{item_id}")


@core.app.post("/my-hockey/memory/{item_id}/delete")
def delete_memory(item_id:int): MEMORY.delete_match(item_id); return RedirectResponse("/my-hockey/memory",status_code=303)


@core.app.get("/my-hockey/memory/photo/{photo_id}")
def memory_photo(photo_id:int):
    photo=MEMORY.get_photo(photo_id)
    return Response(status_code=404) if not photo else Response(content=photo["image_data"],media_type=photo["mime_type"],headers={"Cache-Control":"private, max-age=86400"})


core.app.version="0.56.0"
app=core.app
