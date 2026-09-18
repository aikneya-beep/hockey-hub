from __future__ import annotations

from datetime import datetime
import html

from bs4 import BeautifulSoup
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v53  # load current production stack first
import app_v05 as core
import personal_hockey_v42 as personal_base
import closet_v48
import environment_v50
from design_system_v46 import COMMON_CSS, topbar
from memory_store_v54 import MemoryStore, season_for_date


STORE = MemoryStore()
_BOOTSTRAP = STORE.load()

_previous_personal_renderer = personal_base.render_personal_page
_previous_closet_renderer = closet_v48.render_closet
_previous_environment_renderer = environment_v50.render_environment


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date_label(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(raw)


def _parse_date(raw: str):
    return datetime.strptime((raw or "").strip(), "%Y-%m-%d").date()


def _parse_score(raw: str) -> int | None:
    text = (raw or "").strip()
    return int(text) if text else None


def _patch_tabs(page: str, active: str) -> str:
    soup = BeautifulSoup(page, "html.parser")
    tabs = soup.select_one(".mine-tabs")
    if not tabs:
        return page

    mapping = {
        "Я": "/my-hockey",
        "Моя хоккейная среда": "/my-hockey/environment",
        "Хоккейный шкаф": "/my-hockey/closet",
        "Память": "/my-hockey/memory",
    }
    aliases = {"Тёма и команды": "Моя хоккейная среда"}

    for anchor in tabs.find_all("a"):
        label = anchor.get_text(" ", strip=True)
        canonical = aliases.get(label, label)
        if canonical in mapping:
            anchor.string = canonical
            anchor["href"] = mapping[canonical]
        classes = [x for x in anchor.get("class", []) if x != "active"]
        anchor["class"] = classes

    target_text = {
        "me": "Я",
        "environment": "Моя хоккейная среда",
        "closet": "Хоккейный шкаф",
        "memory": "Память",
    }[active]
    for anchor in tabs.find_all("a"):
        if anchor.get_text(" ", strip=True) == target_text:
            anchor["class"] = list(dict.fromkeys(anchor.get("class", []) + ["active"]))
            break

    selectors = (".mine-hero .hub-eyebrow", ".env-hero .hub-eyebrow", ".closet-hero .hub-eyebrow")
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            prefix = "Личный хоккей" if "mine-hero" in selector else "Мой хоккей"
            node.string = f"{prefix} · v0.54"
            break
    return str(soup)


def _season_stats(matches: list[dict]) -> dict:
    arenas = {x.get("arena", "").strip() for x in matches if x.get("arena", "").strip()}
    teams = {
        team.strip()
        for x in matches
        for team in (x.get("home_team", ""), x.get("away_team", ""))
        if team.strip()
    }
    scored = sum(
        1
        for x in matches
        if x.get("home_score") is not None and x.get("away_score") is not None
    )
    companions = {
        x.get("companions", "").strip()
        for x in matches
        if x.get("companions", "").strip()
    }
    return {
        "matches": len(matches),
        "arenas": len(arenas),
        "teams": len(teams),
        "scored": scored,
        "companions": len(companions),
    }


def _memory_cards(matches: list[dict]) -> str:
    if not matches:
        return '<div class="memory-empty">В этом сезоне пока нет сохранённых посещённых матчей.</div>'
    cards = []
    for item in matches:
        score = "—:—"
        if item.get("home_score") is not None and item.get("away_score") is not None:
            score = f'{item["home_score"]}:{item["away_score"]}'
        place_bits = [x for x in (item.get("arena"), f'сектор {item.get("sector")}' if item.get("sector") else "", f'место {item.get("seat")}' if item.get("seat") else "") if x]
        place = " · ".join(place_bits) or "место не указано"
        companion = item.get("companions") or ""
        note = item.get("note") or ""
        ticket = item.get("ticket_ref") or ""
        photos = item.get("photo_refs") or ""
        media = []
        if ticket:
            media.append("билет сохранён")
        if photos:
            media.append("фото отмечены")
        cards.append(f'''<article class="memory-card">
          <div class="memory-top">
            <div><span>{_esc(item.get("competition") or "Матч")} · {_esc(item.get("season"))}</span><time>{_date_label(item.get("match_date"))}</time></div>
            <strong>{_esc(score)}</strong>
          </div>
          <div class="memory-match"><b>{_esc(item.get("home_team"))}</b><i>—</i><b>{_esc(item.get("away_team"))}</b></div>
          <div class="memory-place">{_esc(place)}</div>
          {f'<div class="memory-people"><span>С кем</span>{_esc(companion)}</div>' if companion else ''}
          {f'<p>{_esc(note)}</p>' if note else ''}
          {f'<div class="memory-media">{" · ".join(map(_esc, media))}</div>' if media else ''}
          <form method="post" action="/my-hockey/memory/{item.get("id")}/delete" class="memory-delete"><button type="submit">Удалить запись</button></form>
        </article>''')
    return "".join(cards)


def render_memory(season: str | None = None, saved: int = 0, error: str | None = None) -> str:
    all_data = STORE.load()
    seasons = all_data.get("seasons") or []
    today = datetime.now(core.MOSCOW).date()
    current_season = season_for_date(today)
    selected = (season or "").strip() or (seasons[0] if seasons else current_season)
    data = STORE.load(selected)
    matches = data.get("matches") or []
    storage_error = data.get("error") or all_data.get("error")
    stats = _season_stats(matches)

    filter_seasons = list(seasons)
    if current_season not in filter_seasons:
        filter_seasons.insert(0, current_season)
    filter_seasons = sorted(set(filter_seasons), reverse=True)

    filters = []
    for value in filter_seasons:
        active = " active" if value == selected else ""
        filters.append(f'<a class="season-chip{active}" href="/my-hockey/memory?season={html.escape(value, quote=True)}">{_esc(value)}</a>')

    if error:
        flash = f'<div class="memory-flash error">Не удалось сохранить: {_esc(error)}</div>'
    elif saved:
        flash = '<div class="memory-flash success">Матч добавлен в личную хоккейную хронику.</div>'
    elif storage_error:
        flash = f'<div class="memory-flash error">PostgreSQL недоступен: {_esc(storage_error)}</div>'
    else:
        flash = ""

    disabled = " disabled" if storage_error else ""

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Память · Мой хоккей · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>
{COMMON_CSS}
:root{{--soyuz:#2a86d9;--soyuz-dim:#365c7d;--silver:#c8d0da}}
body{{background:radial-gradient(circle at 84% 5%,rgba(42,134,217,.08),transparent 25%),linear-gradient(180deg,#05070b,#080b0f 60%,#05070b)}}
.memory-hero{{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}.memory-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.memory-hero p{{margin:0;color:#929dac;max-width:760px;font-size:15px;line-height:1.55}}.memory-code{{text-align:right;color:#708094;font-size:9px;letter-spacing:.12em;text-transform:uppercase}}.memory-code b{{display:block;color:#d8dee6;font-size:13px;letter-spacing:.04em;margin-bottom:4px}}
.mine-tabs{{display:flex;gap:8px;margin:18px 0;overflow:auto}}.mine-tabs a{{position:relative;text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}}.mine-tabs a.active{{color:#f2f5f8;border-color:#53616f;background:linear-gradient(180deg,#161c23,#0e1319)}}.mine-tabs a.active:after{{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--soyuz);box-shadow:0 0 10px rgba(42,134,217,.3)}}
.memory-flash{{margin-bottom:14px;padding:11px 13px;border:1px solid #2a333f;border-radius:11px;background:#10151c;color:#aeb7c4;font-size:11px}}.memory-flash.success{{border-color:#365541;color:#bcd5c3}}.memory-flash.error{{border-color:#61363d;color:#efb4ba}}
.memory-toolbar{{display:flex;justify-content:space-between;gap:18px;align-items:center;margin:6px 0 14px}}.season-list{{display:flex;gap:7px;overflow:auto}}.season-chip{{text-decoration:none;border:1px solid #27323e;background:#0c1117;color:#758396;border-radius:999px;padding:6px 9px;font-size:9px;white-space:nowrap}}.season-chip.active{{color:#dce5ed;border-color:#396487;background:#0e1720}}.memory-toolbar span{{color:#657587;font-size:9px}}
.memory-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}}.memory-stat{{position:relative;overflow:hidden;min-height:100px;padding:15px;background:linear-gradient(180deg,#10161d,#090d12);border:1px solid #25303b;border-radius:14px}}.memory-stat:before{{content:"";position:absolute;left:15px;top:0;width:32px;height:2px;background:linear-gradient(90deg,var(--soyuz),var(--soyuz-dim));opacity:.7}}.memory-stat span{{display:block;color:#718093;font-size:8px;text-transform:uppercase;letter-spacing:.1em}}.memory-stat b{{display:block;font-size:28px;line-height:1;margin-top:13px}}.memory-stat em{{display:block;color:#657487;font-style:normal;font-size:8px;margin-top:8px}}
.memory-layout{{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(320px,.6fr);gap:14px;align-items:start}}.memory-list{{display:grid;gap:10px}}.memory-card{{position:relative;overflow:hidden;background:linear-gradient(180deg,#0f151c,#090d12);border:1px solid #25303b;border-radius:15px;padding:16px}}.memory-card:before{{content:"";position:absolute;left:0;top:18px;bottom:18px;width:2px;background:linear-gradient(var(--soyuz),#687683)}}.memory-top{{display:flex;justify-content:space-between;gap:14px;align-items:start}}.memory-top span{{display:block;color:#697a8d;font-size:8px;text-transform:uppercase;letter-spacing:.09em}}.memory-top time{{display:block;color:#8996a6;font-size:9px;margin-top:4px}}.memory-top strong{{font-size:22px;font-variant-numeric:tabular-nums}}.memory-match{{display:flex;align-items:center;gap:8px;font-size:16px;margin-top:16px}}.memory-match i{{font-style:normal;color:#526172;font-weight:400}}.memory-place{{color:#7f8d9e;font-size:9px;margin-top:10px}}.memory-people{{display:flex;gap:7px;color:#a7b2bf;font-size:9px;margin-top:12px}}.memory-people span{{color:#617286;text-transform:uppercase;letter-spacing:.08em}}.memory-card p{{color:#9aa5b3;font-size:10px;line-height:1.55;margin:13px 0 0}}.memory-media{{color:#7096b8;font-size:8px;margin-top:11px}}.memory-delete{{padding:0;margin-top:13px}}.memory-delete button{{border:0;background:transparent;color:#5e6b7a;padding:0;font-size:8px;cursor:pointer}}.memory-delete button:hover{{color:#bd7e86}}.memory-empty{{padding:24px;border:1px dashed #2a3440;border-radius:14px;color:#6f7c8c;font-size:10px}}
.memory-side{{display:grid;gap:14px}}.panel{{padding:18px}}.section-title{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px}}.section-title h2{{font-size:15px;margin:0}}.section-title span{{color:#687789;font-size:8px;text-transform:uppercase;letter-spacing:.1em}}
.memory-form{{display:grid;gap:10px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}label{{display:grid;gap:5px;color:#909baa;font-size:9px}}input,textarea,select{{width:100%;border:1px solid #303a47;border-radius:9px;background:#080c11;color:#eef2f6;padding:9px 10px}}input:focus,textarea:focus,select:focus{{outline:none;border-color:#365c7d;box-shadow:0 0 0 2px rgba(42,134,217,.11)}}textarea{{min-height:78px;resize:vertical}}button.save{{border:1px solid #8b949e;border-radius:9px;background:linear-gradient(180deg,#d9dfe5,#bbc4cd);color:#0a0e13;padding:10px 12px;font-weight:850;cursor:pointer}}button:disabled,input:disabled,textarea:disabled,select:disabled{{opacity:.42;cursor:not-allowed}}
.future-box{{border:1px solid #243444;background:rgba(42,134,217,.035);border-radius:12px;padding:13px;color:#7890a7;font-size:9px;line-height:1.55}}.future-box b{{color:#a8bfd4}}.footer-note{{display:flex;justify-content:space-between;gap:20px;margin-top:20px;padding-top:15px;border-top:1px solid #1e252e;color:#596575;font-size:9px;text-transform:uppercase;letter-spacing:.05em}}
@media(max-width:900px){{.memory-layout{{grid-template-columns:1fr}}.memory-stats{{grid-template-columns:1fr 1fr}}}}
@media(max-width:760px){{.memory-hero{{grid-template-columns:1fr;padding-top:26px}}.memory-hero h1{{font-size:42px}}.memory-code{{text-align:left}}.memory-toolbar{{align-items:flex-start;flex-direction:column}}.two{{grid-template-columns:1fr}}.footer-note{{flex-direction:column}}}}
</style></head><body><main class="hub-shell">{topbar('mine')}
<section class="memory-hero"><div><div class="hub-eyebrow">Мой хоккей · v0.54</div><h1>Память</h1><p>Личная хоккейная хроника: какие матчи я видел, где сидел, с кем ходил и что осталось от этого вечера.</p></div><div class="memory-code"><b>MATCHES / PLACES / PEOPLE</b>сезоны · впечатления · артефакты</div></section>
<nav class="mine-tabs"><a href="/my-hockey">Я</a><a href="/my-hockey/environment">Моя хоккейная среда</a><a href="/my-hockey/closet">Хоккейный шкаф</a><a class="active" href="/my-hockey/memory">Память</a></nav>
{flash}
<section class="memory-toolbar"><div class="season-list">{''.join(filters)}</div><span>выбран сезон · {_esc(selected)}</span></section>
<section class="memory-stats"><article class="memory-stat"><span>Посещено</span><b>{stats["matches"]}</b><em>матчей в сезоне</em></article><article class="memory-stat"><span>Арены</span><b>{stats["arenas"]}</b><em>разных площадок</em></article><article class="memory-stat"><span>Команды</span><b>{stats["teams"]}</b><em>видел вживую</em></article><article class="memory-stat"><span>Со счётом</span><b>{stats["scored"]}</b><em>результат сохранён</em></article></section>
<section class="memory-layout"><div class="memory-list">{_memory_cards(matches)}</div><aside class="memory-side">
<article class="hub-card panel"><div class="section-title"><h2>Добавить посещённый матч</h2><span>в хронику</span></div>
<form class="memory-form" method="post" action="/my-hockey/memory">
<div class="two"><label>Дата<input type="date" name="match_date" value="{today.isoformat()}" required{disabled}></label><label>Турнир<input name="competition" placeholder="КХЛ / ВХЛ / ..."{disabled}></label></div>
<div class="two"><label>Хозяева<input name="home_team" required placeholder="СКА"{disabled}></label><label>Гости<input name="away_team" required placeholder="Спартак"{disabled}></label></div>
<div class="two"><label>Счёт хозяев<input type="number" min="0" name="home_score"{disabled}></label><label>Счёт гостей<input type="number" min="0" name="away_score"{disabled}></label></div>
<label>Арена<input name="arena" placeholder="СКА Арена"{disabled}></label>
<div class="two"><label>Сектор<input name="sector" placeholder="216"{disabled}></label><label>Место<input name="seat" placeholder="ряд / место"{disabled}></label></div>
<label>С кем ходил<input name="companions" placeholder="Тёма / Ксюша / друзья"{disabled}></label>
<label>Заметка<textarea name="note" placeholder="Что запомнилось, атмосфера, важный момент"{disabled}></textarea></label>
<input type="hidden" name="season" value="{_esc(selected)}">
<button class="save" type="submit"{disabled}>Сохранить матч</button>
</form></article>
<article class="hub-card panel"><div class="section-title"><h2>Билеты и фото</h2><span>следующий слой</span></div><div class="future-box"><b>Модель уже готова к артефактам.</b> Следующим маленьким этапом подключим загрузку билета и фотографий к конкретной записи — без превращения раздела в бесконечную фотогалерею.</div></article>
</aside></section>
<footer class="footer-note"><span>Hockey Hub · Память</span><span>матчи · люди · места · впечатления</span></footer>
</main></body></html>'''


def patch_personal(saved: bool = False, error: str | None = None) -> str:
    return _patch_tabs(_previous_personal_renderer(saved=saved, error=error), "me")


def patch_closet(saved: str | None = None, error: str | None = None) -> str:
    return _patch_tabs(_previous_closet_renderer(saved=saved, error=error), "closet")


def patch_environment() -> str:
    return _patch_tabs(_previous_environment_renderer(), "environment")


personal_base.render_personal_page = patch_personal
closet_v48.render_closet = patch_closet
environment_v50.render_environment = patch_environment


@core.app.get("/my-hockey/memory", response_class=HTMLResponse)
def hockey_memory(season: str | None = None, saved: int = 0, error: str | None = None):
    return render_memory(season=season, saved=saved, error=error)


@core.app.post("/my-hockey/memory")
def add_memory(
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
    season: str = Form(""),
):
    try:
        resolved_date = _parse_date(match_date)
        STORE.add_match(
            match_date=resolved_date,
            competition=competition,
            home_team=home_team,
            away_team=away_team,
            home_score=_parse_score(home_score),
            away_score=_parse_score(away_score),
            arena=arena,
            sector=sector,
            seat=seat,
            companions=companions,
            note=note,
            season=season,
        )
        resolved_season = season.strip() or season_for_date(resolved_date)
        return RedirectResponse(f"/my-hockey/memory?season={html.escape(resolved_season, quote=True)}&saved=1", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/my-hockey/memory?error={html.escape(type(exc).__name__ + ': ' + str(exc)[:120], quote=True)}", status_code=303)


@core.app.post("/my-hockey/memory/{item_id}/delete")
def delete_memory(item_id: int):
    STORE.delete_match(item_id)
    return RedirectResponse("/my-hockey/memory", status_code=303)


core.app.version = "0.54.0"
app = core.app
