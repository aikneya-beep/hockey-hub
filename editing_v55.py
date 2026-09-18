from __future__ import annotations

from datetime import datetime
from io import BytesIO
import html
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi import File, Form, UploadFile
from fastapi.responses import RedirectResponse, Response
from PIL import Image, ImageOps

import app_v541
import app_v05 as core
import memory_v54 as memory_base
import memory_v541
import personal_hockey_v42 as personal_base
import development_v52
import closet_v48
import environment_v50


# ---- helpers -----------------------------------------------------------------

def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date(raw: str | None):
    text = (raw or "").strip()
    return datetime.strptime(text, "%Y-%m-%d").date() if text else None


def _selected(options: list[str], current: str) -> str:
    return "".join(
        f'<option{" selected" if value == current else ""}>{_esc(value)}</option>'
        for value in options
    )


def _bump_page(page: str, selector: str | None = None) -> str:
    soup = BeautifulSoup(page, "html.parser")
    if selector:
        node = soup.select_one(selector)
        if node:
            raw = node.get_text(" ", strip=True)
            prefix = raw.split("·")[0].strip() if "·" in raw else raw
            node.string = f"{prefix} · v0.55.1"
    text = str(soup)
    for old in ("v0.54.1", "v0.54", "v0.53.2", "v0.53.1", "v0.53"):
        if old in text:
            text = text.replace(old, "v0.55.1", 1)
            break
    return text


# ---- Memory: editable album + photos -----------------------------------------

def _photo_gallery(item: dict) -> str:
    photos = item.get("photos") or []
    if not photos:
        return ""
    cells = []
    for p in photos:
        pid = int(p["id"])
        cells.append(f'''<figure class="memory-photo">
          <a href="/my-hockey/memory/photo/{pid}" target="_blank" rel="noopener">
            <img loading="lazy" src="/my-hockey/memory/photo/{pid}" alt="Фото к воспоминанию">
          </a>
          <form method="post" action="/my-hockey/memory/photo/{pid}/delete">
            <input type="hidden" name="season" value="{_esc(item.get("season"))}">
            <button type="submit" title="Удалить фото" onclick="return confirm('Удалить эту фотографию?')">×</button>
          </form>
        </figure>''')
    return f'<div class="memory-photos">{"".join(cells)}</div>'


def _memory_edit(item: dict) -> str:
    hs = "" if item.get("home_score") is None else str(item.get("home_score"))
    aws = "" if item.get("away_score") is None else str(item.get("away_score"))
    return f'''<details class="record-edit memory-edit">
      <summary>Редактировать воспоминание</summary>
      <form method="post" action="/my-hockey/memory/{item["id"]}/edit">
        <div class="edit-two">
          <label>Дата<input type="date" name="match_date" value="{_esc(item.get("match_date"))}" required></label>
          <label>Турнир<input name="competition" value="{_esc(item.get("competition"))}"></label>
        </div>
        <div class="edit-two">
          <label>Хозяева<input name="home_team" value="{_esc(item.get("home_team"))}" required></label>
          <label>Гости<input name="away_team" value="{_esc(item.get("away_team"))}" required></label>
        </div>
        <div class="edit-two">
          <label>Счёт хозяев<input type="number" min="0" name="home_score" value="{_esc(hs)}"></label>
          <label>Счёт гостей<input type="number" min="0" name="away_score" value="{_esc(aws)}"></label>
        </div>
        <label>Арена<input name="arena" value="{_esc(item.get("arena"))}"></label>
        <div class="edit-two">
          <label>Сектор<input name="sector" value="{_esc(item.get("sector"))}"></label>
          <label>Место<input name="seat" value="{_esc(item.get("seat"))}"></label>
        </div>
        <label>С кем ходил<input name="companions" value="{_esc(item.get("companions"))}"></label>
        <label>Что хочется запомнить<textarea name="note">{_esc(item.get("note"))}</textarea></label>
        <button class="edit-save" type="submit">Сохранить изменения</button>
      </form>
    </details>'''


def _memory_photos_form(item: dict) -> str:
    count = len(item.get("photos") or [])
    if count >= 6:
        return '<div class="photo-limit">6/6 фотографий · лимит заполнен</div>'
    return f'''<details class="photo-add">
      <summary>+ Добавить фотографии <span>{count}/6</span></summary>
      <form method="post" action="/my-hockey/memory/{item["id"]}/photos" enctype="multipart/form-data">
        <input type="hidden" name="season" value="{_esc(item.get("season"))}">
        <input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple required>
        <div class="photo-hint">До 6 фото на воспоминание. JPEG, PNG или WebP; большие снимки автоматически уменьшаются.</div>
        <button class="edit-save" type="submit">Загрузить</button>
      </form>
    </details>'''


def _album_cards_v55(matches: list[dict]) -> str:
    if not matches:
        return """<section class="memory-empty">
          <div class="empty-mark">✦</div>
          <h2>Здесь пока тихо.</h2>
          <p>Первый сохранённый матч станет началом твоей хоккейной хроники.</p>
          <a href="#new-memory">+ Сохранить первое воспоминание</a>
        </section>"""

    cards = []
    for item in matches:
        score = ""
        if item.get("home_score") is not None and item.get("away_score") is not None:
            score = f'{item["home_score"]}:{item["away_score"]}'

        where = []
        if item.get("arena"):
            where.append(item["arena"])
        if item.get("sector"):
            where.append(f'сектор {item["sector"]}')
        if item.get("seat"):
            where.append(f'место {item["seat"]}')
        place = " · ".join(where)

        meta = []
        if item.get("competition"):
            meta.append(item["competition"])
        if score:
            meta.append(score)
        if item.get("companions"):
            meta.append(item["companions"])

        note = item.get("note") or ""
        cards.append(f'''<article class="memory-entry" id="memory-{item["id"]}">
          <div class="memory-date">{_esc(memory_v541._date_label(item.get("match_date")))}</div>
          <div class="memory-entry-body">
            <div class="memory-kicker">{_esc(item.get("competition") or "Хоккейный вечер")} · {_esc(item.get("season"))}</div>
            <div class="memory-title-row">
              <h2>{_esc(item.get("home_team"))} <span>—</span> {_esc(item.get("away_team"))}</h2>
              {f'<strong>{_esc(score)}</strong>' if score else ''}
            </div>
            {f'<div class="memory-place">{_esc(place)}</div>' if place else ''}
            {_photo_gallery(item)}
            {f'<p class="memory-note">{_esc(note)}</p>' if note else '<p class="memory-note muted">Пока без заметки — только сам факт этого вечера.</p>'}
            <div class="memory-foot"><div>{' · '.join(_esc(x) for x in meta)}</div></div>
            <div class="memory-actions">
              {_memory_photos_form(item)}
              {_memory_edit(item)}
            </div>
            <form method="post" action="/my-hockey/memory/{item["id"]}/delete" class="memory-delete">
              <button type="submit" onclick="return confirm('Удалить это воспоминание целиком?')">удалить воспоминание</button>
            </form>
          </div>
        </article>''')
    return "".join(cards)


memory_v541._album_cards = _album_cards_v55
_previous_memory_renderer = memory_base.render_memory


def render_memory_v55(season: str | None = None, saved: int = 0, error: str | None = None) -> str:
    page = _previous_memory_renderer(season=season, saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")

    code = soup.select_one(".memory-code b")
    if code:
        code.string = "ВЕЧЕРА / ЛЮДИ / МЕСТА"
    artifact = soup.select_one(".artifact-box")
    if artifact:
        artifact.decompose()

    eyebrow = soup.select_one(".memory-hero .hub-eyebrow")
    if eyebrow:
        eyebrow.string = "Мой хоккей · v0.55.1"

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.55: editable memories and real photo attachments */
.memory-photos{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:16px}
.memory-photo{position:relative;margin:0;border-radius:11px;overflow:hidden;background:#05080c;aspect-ratio:4/3;border:1px solid #26323e}
.memory-photo img{display:block;width:100%;height:100%;object-fit:contain}
.memory-photo form{position:absolute;right:6px;top:6px;padding:0;opacity:0;transform:translateY(-3px);transition:opacity .15s ease,transform .15s ease;pointer-events:none}
.memory-photo:hover form,.memory-photo:focus-within form{opacity:1;transform:none;pointer-events:auto}
.memory-photo button{width:24px;height:24px;padding:0;border:1px solid rgba(255,255,255,.18);border-radius:50%;background:rgba(5,8,12,.88);color:#d4dce5;cursor:pointer}
@media(hover:none){.memory-photo:focus-within form{opacity:1;pointer-events:auto}}
.memory-actions{display:flex;gap:14px;align-items:flex-start;margin-top:13px;flex-wrap:wrap}
.photo-add,.record-edit{font-size:8px;color:#6d8094}.photo-add summary,.record-edit summary{cursor:pointer;color:#7895b0}
.photo-add summary span{color:#526577;margin-left:4px}.photo-add form,.record-edit form{display:grid;gap:8px;margin-top:10px;padding:12px;border:1px solid #283542;border-radius:11px;background:#080d12;min-width:min(520px,70vw)}
.record-edit label{display:grid;gap:4px;color:#7c8a9a;font-size:8px}.record-edit input,.record-edit textarea,.photo-add input[type=file]{border:1px solid #303c49;border-radius:8px;background:#070b0f;color:#e8edf2;padding:8px 9px}
.record-edit textarea{min-height:84px}.edit-two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.edit-save{border:1px solid #53687c;border-radius:8px;background:#111b24;color:#dce6ef;padding:8px 10px;font-size:9px;font-weight:750;cursor:pointer}.photo-hint,.photo-limit{color:#617386;font-size:8px;line-height:1.45}.photo-limit{margin-top:2px}
@media(max-width:680px){.memory-photos{grid-template-columns:1fr 1fr}.edit-two{grid-template-columns:1fr}.photo-add form,.record-edit form{min-width:0;width:82vw}}
""")
    return str(soup)


memory_base.render_memory = render_memory_v55


def _process_photo(raw: bytes) -> tuple[bytes, int, int]:
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError("Один файл не должен быть больше 12 МБ")
    Image.MAX_IMAGE_PIXELS = 40_000_000
    with Image.open(BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (8, 11, 15))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        out = BytesIO()
        image.save(out, format="WEBP", quality=82, method=6)
        payload = out.getvalue()
        if len(payload) > 3 * 1024 * 1024:
            out = BytesIO()
            image.save(out, format="WEBP", quality=70, method=6)
            payload = out.getvalue()
        return payload, image.width, image.height


@core.app.post("/my-hockey/memory/{item_id}/edit")
def edit_memory(
    item_id: int,
    match_date: str = Form(...),
    competition: str = Form(""),
    home_team: str = Form(...),
    away_team: str = Form(...),
    home_score: str = Form(""),
    away_score: str = Form(""),
    arena: str = Form(""),
    sector: str = Form(""),
    seat: str = Form(""),
    companions: str = Form(""),
    note: str = Form(""),
):
    day = memory_base._parse_date(match_date)
    memory_base.STORE.update_match(
        item_id,
        match_date=day,
        competition=competition,
        home_team=home_team,
        away_team=away_team,
        home_score=memory_base._parse_score(home_score),
        away_score=memory_base._parse_score(away_score),
        arena=arena,
        sector=sector,
        seat=seat,
        companions=companions,
        note=note,
    )
    season = memory_base.season_for_date(day)
    return RedirectResponse(f"/my-hockey/memory?season={season}#memory-{item_id}", status_code=303)


@core.app.post("/my-hockey/memory/{item_id}/photos")
async def add_memory_photos(
    item_id: int,
    season: str = Form(""),
    photos: list[UploadFile] | None = File(None),
):
    resolved = season or ""
    try:
        all_data = memory_base.STORE.load()
        match = next((x for x in all_data.get("matches", []) if int(x.get("id")) == int(item_id)), None)
        if not match:
            raise ValueError("Воспоминание не найдено")

        resolved = resolved or match.get("season") or ""
        selected = [p for p in (photos or []) if p and (p.filename or "").strip()]
        if not selected:
            raise ValueError("Выбери хотя бы одну фотографию")

        existing = len(match.get("photos") or [])
        free_slots = max(0, 6 - existing)
        if len(selected) > free_slots:
            if free_slots == 0:
                raise ValueError("Лимит заполнен: к воспоминанию уже добавлено 6 фотографий")
            raise ValueError(f"Можно добавить ещё только {free_slots} фото")

        allowed = {"image/jpeg", "image/png", "image/webp"}
        processed: list[tuple[UploadFile, bytes, int, int]] = []
        for upload in selected:
            content_type = (upload.content_type or "").lower()
            if content_type not in allowed:
                raise ValueError(f"Файл «{upload.filename or 'без имени'}» имеет неподдерживаемый формат")
            raw = await upload.read()
            if not raw:
                raise ValueError(f"Файл «{upload.filename or 'без имени'}» пустой")
            try:
                payload, width, height = _process_photo(raw)
            except ValueError:
                raise
            except Exception:
                raise ValueError(f"Не удалось прочитать изображение «{upload.filename or 'без имени'}»")
            processed.append((upload, payload, width, height))

        for upload, payload, width, height in processed:
            memory_base.STORE.add_photo(
                item_id,
                mime_type="image/webp",
                image_data=payload,
                width=width,
                height=height,
                original_name=upload.filename or "",
            )
        return RedirectResponse(f"/my-hockey/memory?season={quote(resolved)}#memory-{item_id}", status_code=303)
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        return RedirectResponse(
            f"/my-hockey/memory?season={quote(resolved)}&error={quote(message[:180])}#memory-{item_id}",
            status_code=303,
        )


@core.app.get("/my-hockey/memory/photo/{photo_id}")
def memory_photo(photo_id: int):
    photo = memory_base.STORE.get_photo(photo_id)
    if not photo:
        return Response(status_code=404)
    return Response(
        content=photo["image_data"],
        media_type=photo["mime_type"],
        headers={"Cache-Control": "private, max-age=86400"},
    )


@core.app.post("/my-hockey/memory/photo/{photo_id}/delete")
def delete_memory_photo(photo_id: int, season: str = Form("")):
    memory_base.STORE.delete_photo(photo_id)
    return RedirectResponse(f"/my-hockey/memory?season={season}", status_code=303)


# ---- Development: editable goals / homework / sessions ------------------------

def _goal_rows_v55(goals: list[dict]) -> str:
    rows = []
    for goal in development_v52._active(goals):
        target = development_v52._date_label(goal.get("target_date")) or "без даты"
        category = goal.get("category") or "цель"
        rows.append(f'''<div class="task-row editable-task">
          <div><span>{_esc(category)} · {target}</span><b>{_esc(goal.get("title"))}</b>{f'<p>{_esc(goal.get("note"))}</p>' if goal.get("note") else ''}</div>
          <div class="task-actions">
            <details><summary>✎</summary><form method="post" action="/my-hockey/development/goal/{goal["id"]}/edit">
              <input name="title" value="{_esc(goal.get("title"))}" required>
              <div class="dev-two"><input name="category" value="{_esc(goal.get("category"))}" placeholder="Категория"><input type="date" name="target_date" value="{_esc(goal.get("target_date"))}"></div>
              <textarea name="note">{_esc(goal.get("note"))}</textarea>
              <button type="submit">Сохранить</button>
            </form></details>
            <form method="post" action="/my-hockey/development/goal/{goal["id"]}/done"><button class="done-btn" type="submit">✓</button></form>
          </div>
        </div>''')
    return "".join(rows) or '<div class="dev-empty">Активных целей пока нет. Добавь первую конкретную контрольную точку.</div>'


def _homework_rows_v55(items: list[dict]) -> str:
    rows = []
    for item in development_v52._active(items):
        due = development_v52._date_label(item.get("due_date"))
        source = item.get("source") or "личное"
        meta = f"{source}{' · до ' + due if due else ''}"
        rows.append(f'''<div class="task-row editable-task">
          <div><span>{_esc(meta)}</span><b>{_esc(item.get("text"))}</b></div>
          <div class="task-actions">
            <details><summary>✎</summary><form method="post" action="/my-hockey/development/homework/{item["id"]}/edit">
              <input name="text" value="{_esc(item.get("text"))}" required>
              <div class="dev-two"><input name="source" value="{_esc(item.get("source"))}" placeholder="Источник"><input type="date" name="due_date" value="{_esc(item.get("due_date"))}"></div>
              <button type="submit">Сохранить</button>
            </form></details>
            <form method="post" action="/my-hockey/development/homework/{item["id"]}/done"><button class="done-btn" type="submit">✓</button></form>
          </div>
        </div>''')
    return "".join(rows) or '<div class="dev-empty">Активных домашних заданий пока нет.</div>'


development_v52._goal_rows = _goal_rows_v55
development_v52._homework_rows = _homework_rows_v55

_previous_personal_renderer = personal_base.render_personal_page


def _session_edit_form(session: dict, coach_note: str, lap_1: str, lap_2: str) -> str:
    focus = ", ".join(session.get("focus") or [])
    types = ["Ледовая тренировка", "Бросковая тренировка", "Игра", "ОФП / вне льда", "Самостоятельная"]
    return f'''<details class="session-record-edit">
      <summary>Редактировать</summary>
      <form method="post" action="/my-hockey/session/{session["id"]}/edit">
        <div class="edit-two"><label>Дата<input type="date" name="session_date" value="{_esc(session.get("date"))}" required></label>
        <label>Тип<select name="session_type">{_selected(types, session.get("type") or "Ледовая тренировка")}</select></label></div>
        <label>Что тренировали<input name="focus" value="{_esc(focus)}"></label>
        <div class="edit-two"><label>Самочувствие<input type="number" min="1" max="10" name="wellbeing" value="{_esc(session.get("wellbeing"))}"></label>
        <label>Нагрузка<input type="number" min="1" max="10" name="load" value="{_esc(session.get("load"))}"></label></div>
        <label>Моя заметка<textarea name="note">{_esc(session.get("note"))}</textarea></label>
        <label>Домашнее задание<textarea name="homework">{_esc(session.get("homework"))}</textarea></label>
        <label>Комментарий тренера<textarea name="coach_note">{_esc(coach_note)}</textarea></label>
        <div class="edit-two"><label>Круг 1<input name="lap_1" value="{_esc(lap_1)}"></label><label>Круг 2<input name="lap_2" value="{_esc(lap_2)}"></label></div>
        <button class="edit-save" type="submit">Сохранить изменения</button>
      </form>
    </details>'''


def render_personal_v55(saved: bool = False, error: str | None = None) -> str:
    page = _previous_personal_renderer(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")
    data = personal_base.STORE.load()
    sessions = sorted(data.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)[:8]
    notes = data.get("coach_notes") or []
    tests = data.get("tests") or []

    rows = soup.select(".history-row")
    for row, session in zip(rows, sessions):
        sid = session.get("id")
        coach = next((x.get("text") or "" for x in notes if x.get("session_id") == sid), "")
        lap1 = next((x.get("seconds") for x in tests if x.get("session_id") == sid and x.get("direction") == "Направление 1"), "")
        lap2 = next((x.get("seconds") for x in tests if x.get("session_id") == sid and x.get("direction") == "Направление 2"), "")
        fragment = BeautifulSoup(_session_edit_form(session, coach, "" if lap1 == "" else f"{float(lap1):.2f}", "" if lap2 == "" else f"{float(lap2):.2f}"), "html.parser")
        row.append(fragment)

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.55: user-created records are editable */
.history-row{grid-template-columns:82px 1fr auto}.session-record-edit{grid-column:2/-1;margin-top:5px;font-size:8px}.session-record-edit summary{cursor:pointer;color:#6785a3}.session-record-edit form{display:grid;gap:8px;margin-top:8px;padding:11px;border:1px solid #283542;border-radius:10px;background:#080d12}.session-record-edit label{display:grid;gap:4px;color:#78889a;font-size:8px}.session-record-edit input,.session-record-edit textarea,.session-record-edit select{padding:8px 9px;font-size:9px}
.task-actions{display:flex;align-items:center;gap:6px}.task-actions details summary{cursor:pointer;list-style:none;border:1px solid #314051;border-radius:8px;width:28px;height:28px;display:grid;place-items:center;color:#7fa2c1}.task-actions details form{position:absolute;z-index:8;right:42px;width:min(420px,70vw);padding:11px;background:#0a1016;border:1px solid #304052;border-radius:10px;box-shadow:0 12px 35px rgba(0,0,0,.35)}.editable-task{position:relative}
@media(max-width:620px){.task-actions details form{right:0;width:78vw}}
""")
    eyebrow = soup.select_one(".mine-hero .hub-eyebrow")
    if eyebrow:
        eyebrow.string = "Личный хоккей · v0.55.1"
    return str(soup)


personal_base.render_personal_page = render_personal_v55


@core.app.post("/my-hockey/session/{session_id}/edit")
def edit_session(
    session_id: int,
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
    day = datetime.strptime(session_date, "%Y-%m-%d").date()
    focus_items = [x.strip() for x in focus.replace(";", ",").split(",") if x.strip()]
    personal_base.STORE.update_session(
        session_id,
        session_date=day,
        session_type=session_type,
        focus=focus_items,
        wellbeing=wellbeing,
        load=load,
        note=note,
        homework=homework,
        coach_note=coach_note,
        lap_1=personal_base._num(lap_1),
        lap_2=personal_base._num(lap_2),
    )
    return RedirectResponse("/my-hockey", status_code=303)


@core.app.post("/my-hockey/development/goal/{item_id}/edit")
def edit_goal(
    item_id: int,
    title: str = Form(...),
    category: str = Form(""),
    target_date: str = Form(""),
    note: str = Form(""),
):
    development_v52.STORE.update_goal(item_id, title, category, development_v52._parse_date(target_date), note)
    return RedirectResponse("/my-hockey#development", status_code=303)


@core.app.post("/my-hockey/development/homework/{item_id}/edit")
def edit_homework(
    item_id: int,
    text: str = Form(...),
    source: str = Form(""),
    due_date: str = Form(""),
):
    development_v52.STORE.update_homework(item_id, text, source, development_v52._parse_date(due_date))
    return RedirectResponse("/my-hockey#development", status_code=303)


# ---- Closet: editable gear and wishlist --------------------------------------

GEAR_CATEGORIES = ["Защита", "Коньки", "Клюшки", "Одежда", "Сумки и аксессуары", "Расходники", "Спортпит", "Атрибутика", "Другое"]
GEAR_CONDITIONS = ["новое", "в игре", "есть износ", "нужен ремонт", "на замену"]
WISH_CATEGORIES = ["Экипировка", "Расходники", "Спортпит", "Атрибутика", "Другое"]


def _gear_cards_v55(items: list[dict]) -> str:
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[item.get("category") or "Другое"].append(item)
    if not groups:
        return '<div class="empty-state">Шкаф пока пуст. Добавь первую вещь ниже.</div>'

    blocks = []
    for category in sorted(groups):
        cards = []
        for item in groups[category]:
            brand_line = " · ".join(x for x in (item.get("brand"), item.get("model")) if x) or "Без бренда/модели"
            condition = item.get("condition") or "в игре"
            cls = closet_v48._condition_class(condition)
            details = []
            if item.get("color"):
                details.append(f"цвет: {_esc(item['color'])}")
            if item.get("purchased_on"):
                details.append(f"куплено: {closet_v48._date_label(item['purchased_on'])}")
            if item.get("purchase_price") is not None:
                details.append(f"цена: {closet_v48._money(item['purchase_price'])}")
            service = f'<div class="service-line"><span>Следующее обслуживание</span><b>{closet_v48._date_label(item["next_service_on"])}</b></div>' if item.get("next_service_on") else ""
            cards.append(f'''<article class="gear-card {cls}">
              <div class="gear-top"><span class="condition-dot"></span><span>{_esc(condition)}</span></div>
              <h3>{_esc(item.get("name"))}</h3><div class="brand-line">{_esc(brand_line)}</div>
              <div class="gear-meta">{' · '.join(details) if details else 'параметры пока не заполнены'}</div>{service}
              {f'<p>{_esc(item.get("notes"))}</p>' if item.get("notes") else ''}
              <details class="closet-edit"><summary>Редактировать</summary><form method="post" action="/my-hockey/closet/item/{item["id"]}/edit">
                <div class="two"><label>Категория<select name="category">{_selected(GEAR_CATEGORIES,item.get("category") or "Другое")}</select></label><label>Название<input name="name" value="{_esc(item.get("name"))}" required></label></div>
                <div class="two"><label>Бренд<input name="brand" value="{_esc(item.get("brand"))}"></label><label>Модель<input name="model" value="{_esc(item.get("model"))}"></label></div>
                <div class="two"><label>Цвет<input name="color" value="{_esc(item.get("color"))}"></label><label>Состояние<select name="condition">{_selected(GEAR_CONDITIONS,condition)}</select></label></div>
                <div class="two"><label>Куплено<input type="date" name="purchased_on" value="{_esc(item.get("purchased_on"))}"></label><label>Цена, ₽<input name="purchase_price" value="{_esc(item.get("purchase_price"))}"></label></div>
                <label>Следующее обслуживание<input type="date" name="next_service_on" value="{_esc(item.get("next_service_on"))}"></label>
                <label>Заметка<textarea name="notes">{_esc(item.get("notes"))}</textarea></label>
                <button class="edit-save" type="submit">Сохранить</button>
              </form></details>
            </article>''')
        blocks.append(f'<section class="gear-group"><div class="group-head"><h2>{_esc(category)}</h2><span>{len(cards)}</span></div><div class="gear-grid">{"".join(cards)}</div></section>')
    return "".join(blocks)


def _wishlist_cards_v55(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty-state compact">Wishlist пока пуст. Добавь то, что хочешь купить или отслеживать.</div>'
    cards = []
    for row in rows:
        target = row.get("target_price")
        current = row.get("current_price")
        link = closet_v48._safe_url(row.get("url"))
        name = _esc(row.get("name"))
        title = f'<a href="{html.escape(link, quote=True)}" target="_blank" rel="noopener">{name} ↗</a>' if link else name
        cards.append(f'''<article class="wish-card">
          <div class="wish-kicker">{_esc(row.get("category"))}{' · ' + _esc(row.get("store")) if row.get("store") else ''}</div>
          <h3>{title}</h3><div class="wish-brand">{_esc(row.get("brand") or "бренд не указан")}</div>
          <div class="price-grid"><div><span>Сейчас</span><b>{closet_v48._money(current)}</b></div><div><span>Цель</span><b>{closet_v48._money(target)}</b></div></div>
          {f'<p>{_esc(row.get("notes"))}</p>' if row.get("notes") else ''}
          <details class="closet-edit"><summary>Редактировать</summary><form method="post" action="/my-hockey/closet/wishlist/{row["id"]}/edit">
            <div class="two"><label>Категория<select name="category">{_selected(WISH_CATEGORIES,row.get("category") or "Другое")}</select></label><label>Название<input name="name" value="{_esc(row.get("name"))}" required></label></div>
            <label>Бренд<input name="brand" value="{_esc(row.get("brand"))}"></label>
            <div class="two"><label>Текущая цена<input name="current_price" value="{_esc(current)}"></label><label>Купить при<input name="target_price" value="{_esc(target)}"></label></div>
            <div class="two"><label>Магазин<input name="store" value="{_esc(row.get("store"))}"></label><label>Ссылка<input type="url" name="url" value="{_esc(row.get("url"))}"></label></div>
            <label>Заметка<textarea name="notes">{_esc(row.get("notes"))}</textarea></label>
            <button class="edit-save" type="submit">Сохранить</button>
          </form></details>
        </article>''')
    return "".join(cards)


closet_v48._gear_cards = _gear_cards_v55
closet_v48._wishlist_cards = _wishlist_cards_v55

_previous_closet_renderer = closet_v48.render_closet


def render_closet_v55(saved: str | None = None, error: str | None = None) -> str:
    page = _previous_closet_renderer(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")
    style = soup.find("style")
    if style:
        style.append(r"""
.closet-edit{margin-top:11px;border-top:1px solid #202833;padding-top:8px}.closet-edit summary{cursor:pointer;color:#68839f;font-size:8px}.closet-edit form{margin-top:9px;padding:10px;border:1px solid #293744;border-radius:10px;background:#080d12}.closet-edit input,.closet-edit textarea,.closet-edit select{font-size:9px;padding:8px}.edit-save{border:1px solid #53687c;border-radius:8px;background:#111b24;color:#dce6ef;padding:8px 10px;font-size:9px;font-weight:750;cursor:pointer}
""")
    eyebrow = soup.select_one(".closet-hero .hub-eyebrow")
    if eyebrow:
        eyebrow.string = "Мой хоккей · v0.55.1"
    return str(soup)


closet_v48.render_closet = render_closet_v55


@core.app.post("/my-hockey/closet/item/{item_id}/edit")
def edit_closet_item(
    item_id: int,
    category: str = Form("Другое"), name: str = Form(...), brand: str = Form(""), model: str = Form(""),
    color: str = Form(""), condition: str = Form("в игре"), purchased_on: str = Form(""),
    purchase_price: str = Form(""), next_service_on: str = Form(""), notes: str = Form(""),
):
    closet_v48.STORE.update_item(
        item_id, category=category, name=name, brand=brand, model=model, color=color, condition=condition,
        purchased_on=closet_v48._date(purchased_on), purchase_price=purchase_price,
        next_service_on=closet_v48._date(next_service_on), notes=notes,
    )
    return RedirectResponse("/my-hockey/closet", status_code=303)


@core.app.post("/my-hockey/closet/wishlist/{item_id}/edit")
def edit_closet_wishlist(
    item_id: int,
    category: str = Form("Другое"), name: str = Form(...), brand: str = Form(""),
    target_price: str = Form(""), current_price: str = Form(""), store: str = Form(""),
    url: str = Form(""), notes: str = Form(""),
):
    closet_v48.STORE.update_wishlist(
        item_id, category=category, name=name, brand=brand, target_price=target_price,
        current_price=current_price, store=store, url=url, notes=notes,
    )
    return RedirectResponse("/my-hockey/closet", status_code=303)


# ---- Version labels on remaining pages ---------------------------------------

_previous_environment_renderer = environment_v50.render_environment


def render_environment_v55() -> str:
    page = _previous_environment_renderer()
    soup = BeautifulSoup(page, "html.parser")
    node = soup.select_one(".env-hero .hub-eyebrow")
    if node:
        node.string = "Мой хоккей · v0.55.1"
    return str(soup)


environment_v50.render_environment = render_environment_v55

_previous_home_renderer = core.render_page


def render_home_v55() -> str:
    page = _previous_home_renderer()
    soup = BeautifulSoup(page, "html.parser")
    node = soup.select_one(".hero .eyebrow")
    if node:
        node.string = "Hockey Hub · v0.55.1 · персональный briefing"
    return str(soup)


core.render_page = render_home_v55
core.app.version = "0.55.1"
app = core.app
