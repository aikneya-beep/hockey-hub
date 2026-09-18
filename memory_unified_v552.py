from __future__ import annotations

from datetime import datetime
import html
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi import File, Form, UploadFile
from fastapi.responses import RedirectResponse

import editing_v55 as prev
import app_v05 as core
import memory_v54 as memory_base
import memory_v541


MAX_MEMORY_PHOTOS = 20


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _gallery_v552(item: dict) -> str:
    photos = item.get("photos") or []
    if not photos:
        return ""
    cells = []
    for p in photos:
        pid = int(p["id"])
        url = f"/my-hockey/memory/photo/{pid}"
        cells.append(
            f'''<figure class="memory-photo memory-photo-soft" style="--photo-bg:url('{url}')">
              <a href="{url}" target="_blank" rel="noopener">
                <img loading="lazy" src="{url}" alt="Фото к воспоминанию">
              </a>
            </figure>'''
        )
    return f'<div class="memory-photos">{"".join(cells)}</div>'


def _edit_current_photos(item: dict) -> str:
    photos = item.get("photos") or []
    if not photos:
        return '<div class="edit-photo-empty">Фотографий пока нет.</div>'
    cells = []
    for p in photos:
        pid = int(p["id"])
        url = f"/my-hockey/memory/photo/{pid}"
        cells.append(
            f'''<label class="edit-photo-cell">
              <img src="{url}" alt="">
              <span><input type="checkbox" name="delete_photo_ids" value="{pid}"> удалить</span>
            </label>'''
        )
    return f'<div class="edit-photo-grid">{"".join(cells)}</div>'


def _memory_edit_v552(item: dict) -> str:
    hs = "" if item.get("home_score") is None else str(item.get("home_score"))
    aws = "" if item.get("away_score") is None else str(item.get("away_score"))
    count = len(item.get("photos") or [])
    return f'''<details class="record-edit memory-edit">
      <summary>Редактировать воспоминание</summary>
      <form method="post" action="/my-hockey/memory/{item["id"]}/edit-full" enctype="multipart/form-data">
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
        <div class="edit-photo-section">
          <div class="edit-photo-title">Фотографии · {count}/{MAX_MEMORY_PHOTOS}</div>
          {_edit_current_photos(item)}
          <label>Добавить ещё
            <input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple>
          </label>
          <div class="photo-hint">Можно удалить отмеченные и добавить новые одним сохранением.</div>
        </div>
        <button class="edit-save" type="submit">Сохранить изменения</button>
      </form>
    </details>'''


def _album_cards_v552(matches: list[dict]) -> str:
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
            {_gallery_v552(item)}
            {f'<p class="memory-note">{_esc(note)}</p>' if note else '<p class="memory-note muted">Пока без заметки — только сам факт этого вечера.</p>'}
            <div class="memory-foot"><div>{' · '.join(_esc(x) for x in meta)}</div></div>
            <div class="memory-actions">{_memory_edit_v552(item)}</div>
            <form method="post" action="/my-hockey/memory/{item["id"]}/delete" class="memory-delete">
              <button type="submit" onclick="return confirm('Удалить это воспоминание целиком?')">удалить воспоминание</button>
            </form>
          </div>
        </article>''')
    return "".join(cards)


memory_v541._album_cards = _album_cards_v552
_previous_memory_renderer = memory_base.render_memory


def render_memory_v552(season: str | None = None, saved: int = 0, error: str | None = None) -> str:
    page = _previous_memory_renderer(season=season, saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")

    # Creation is one form: memory fields + optional photos.
    create_form = soup.select_one(".memory-add-card form")
    if create_form:
        create_form["action"] = "/my-hockey/memory/create-full"
        create_form["enctype"] = "multipart/form-data"
        button = create_form.select_one("button.save")
        if button:
            block = BeautifulSoup(
                f'''<div class="create-photo-section">
                  <div class="form-section">Фотографии</div>
                  <label>Добавить к воспоминанию
                    <input type="file" name="photos" accept="image/jpeg,image/png,image/webp" multiple>
                  </label>
                  <div class="photo-hint">Необязательно. До {MAX_MEMORY_PHOTOS} фото; большие снимки автоматически уменьшаются.</div>
                </div>''',
                "html.parser",
            )
            button.insert_before(block)

    eyebrow = soup.select_one(".memory-hero .hub-eyebrow")
    if eyebrow:
        eyebrow.string = "Мой хоккей · v0.55.2"

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.55.2: photos live inside create/edit forms; full frame over soft photo background */
.memory-photo-soft{isolation:isolate;background:#111820}
.memory-photo-soft::before{content:"";position:absolute;inset:-10px;background-image:var(--photo-bg);background-size:cover;background-position:center;filter:blur(18px) saturate(.85) brightness(.58);transform:scale(1.12);opacity:.92;z-index:0}
.memory-photo-soft::after{content:"";position:absolute;inset:0;background:rgba(5,8,12,.12);z-index:1}
.memory-photo-soft>a{position:relative;z-index:2;display:block;width:100%;height:100%}
.memory-photo-soft img{position:relative;z-index:2;width:100%;height:100%;object-fit:contain}
.memory-actions{margin-top:13px}
.memory-actions .record-edit{width:100%}
.memory-actions .record-edit form{max-width:760px}
.edit-photo-section,.create-photo-section{display:grid;gap:8px;margin-top:5px;padding-top:10px;border-top:1px solid #24313e}
.edit-photo-title{color:#8295a7;font-size:8px;letter-spacing:.08em;text-transform:uppercase}
.edit-photo-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}
.edit-photo-cell{position:relative;overflow:hidden;border:1px solid #2b3947;border-radius:9px;background:#080d12;cursor:pointer}
.edit-photo-cell img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover}
.edit-photo-cell span{display:flex;gap:5px;align-items:center;padding:6px 7px;color:#8291a2;font-size:8px}
.edit-photo-cell input{width:auto;margin:0}
.edit-photo-empty{color:#647487;font-size:8px}
.create-photo-section input[type=file],.edit-photo-section input[type=file]{border:1px solid #303c49;border-radius:8px;background:#070b0f;color:#dce5ed;padding:8px;font-size:8px}
@media(max-width:680px){.edit-photo-grid{grid-template-columns:1fr 1fr}}
""")
    return str(soup)


memory_base.render_memory = render_memory_v552


def _selected_uploads(photos: list[UploadFile] | None) -> list[UploadFile]:
    return [p for p in (photos or []) if p and (p.filename or "").strip()]


async def _prepare_uploads(photos: list[UploadFile] | None) -> list[dict]:
    selected = _selected_uploads(photos)
    if len(selected) > MAX_MEMORY_PHOTOS:
        raise ValueError(f"Можно загрузить не больше {MAX_MEMORY_PHOTOS} фотографий")
    allowed = {"image/jpeg", "image/png", "image/webp"}
    out: list[dict] = []
    for upload in selected:
        if (upload.content_type or "").lower() not in allowed:
            raise ValueError(f"Файл «{upload.filename or 'без имени'}» имеет неподдерживаемый формат")
        raw = await upload.read()
        if not raw:
            raise ValueError(f"Файл «{upload.filename or 'без имени'}» пустой")
        try:
            payload, width, height = prev._process_photo(raw)
        except ValueError:
            raise
        except Exception:
            raise ValueError(f"Не удалось прочитать изображение «{upload.filename or 'без имени'}»")
        out.append(
            {
                "mime_type": "image/webp",
                "image_data": payload,
                "width": width,
                "height": height,
                "original_name": upload.filename or "",
            }
        )
    return out


@core.app.post("/my-hockey/memory/create-full")
async def create_memory_full(
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
    photos: list[UploadFile] | None = File(None),
):
    try:
        day = memory_base._parse_date(match_date)
        prepared = await _prepare_uploads(photos)
        item_id = memory_base.STORE.create_match_with_photos(
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
            photos=prepared,
            max_photos=MAX_MEMORY_PHOTOS,
        )
        season = memory_base.season_for_date(day)
        return RedirectResponse(
            f"/my-hockey/memory?season={quote(season)}&saved=1#memory-{item_id}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            f"/my-hockey/memory?error={quote((str(exc) or type(exc).__name__)[:180])}#new-memory",
            status_code=303,
        )


@core.app.post("/my-hockey/memory/{item_id}/edit-full")
async def edit_memory_full(
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
    delete_photo_ids: list[int] | None = Form(None),
    photos: list[UploadFile] | None = File(None),
):
    season = ""
    try:
        day = memory_base._parse_date(match_date)
        season = memory_base.season_for_date(day)
        prepared = await _prepare_uploads(photos)
        memory_base.STORE.update_match_with_photos(
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
            delete_photo_ids=delete_photo_ids or [],
            photos=prepared,
            max_photos=MAX_MEMORY_PHOTOS,
        )
        return RedirectResponse(
            f"/my-hockey/memory?season={quote(season)}#memory-{item_id}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            f"/my-hockey/memory?season={quote(season)}&error={quote((str(exc) or type(exc).__name__)[:180])}#memory-{item_id}",
            status_code=303,
        )


# Align release labels on the rest of the product.
_previous_personal = prev.personal_base.render_personal_page
def personal_v552(saved: bool = False, error: str | None = None) -> str:
    return _previous_personal(saved=saved, error=error).replace("v0.55.1", "v0.55.2", 1)
prev.personal_base.render_personal_page = personal_v552

_previous_closet = prev.closet_v48.render_closet
def closet_v552(saved: str | None = None, error: str | None = None) -> str:
    return _previous_closet(saved=saved, error=error).replace("v0.55.1", "v0.55.2", 1)
prev.closet_v48.render_closet = closet_v552

_previous_environment = prev.environment_v50.render_environment
def environment_v552() -> str:
    return _previous_environment().replace("v0.55.1", "v0.55.2", 1)
prev.environment_v50.render_environment = environment_v552

_previous_home = core.render_page
def home_v552() -> str:
    page = _previous_home()
    soup = BeautifulSoup(page, "html.parser")
    node = soup.select_one(".hero .eyebrow")
    if node:
        node.string = "Hockey Hub · v0.55.2 · персональный briefing"
    return str(soup)
core.render_page = home_v552

core.app.version = "0.55.2"
app = core.app
