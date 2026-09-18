from __future__ import annotations

from datetime import datetime
import html

from bs4 import BeautifulSoup

import memory_v54 as base
import app_v05 as core
import personal_hockey_v42 as personal_base
import closet_v48
import environment_v50
from design_system_v46 import COMMON_CSS, topbar


_previous_personal = personal_base.render_personal_page
_previous_closet = closet_v48.render_closet
_previous_environment = environment_v50.render_environment
_previous_home = core.render_page


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date_label(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%-d %B %Y").replace(
            "January", "января"
        ).replace("February", "февраля").replace("March", "марта").replace(
            "April", "апреля"
        ).replace("May", "мая").replace("June", "июня").replace(
            "July", "июля"
        ).replace("August", "августа").replace("September", "сентября").replace(
            "October", "октября"
        ).replace("November", "ноября").replace("December", "декабря")
    except Exception:
        return str(raw)


def _album_cards(matches: list[dict]) -> str:
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
            meta.append(f"счёт {score}")
        if item.get("companions"):
            meta.append(f'с {item["companions"]}')

        note = item.get("note") or ""
        artifact_bits = []
        if item.get("ticket_ref"):
            artifact_bits.append("билет")
        if item.get("photo_refs"):
            artifact_bits.append("фото")

        cards.append(f"""<article class="memory-entry">
          <div class="memory-date">{_esc(_date_label(item.get("match_date")))}</div>
          <div class="memory-entry-body">
            <div class="memory-kicker">{_esc(item.get("competition") or "Хоккейный вечер")} · {_esc(item.get("season"))}</div>
            <div class="memory-title-row">
              <h2>{_esc(item.get("home_team"))} <span>—</span> {_esc(item.get("away_team"))}</h2>
              {f'<strong>{_esc(score)}</strong>' if score else ''}
            </div>
            {f'<div class="memory-place">{_esc(place)}</div>' if place else ''}
            {f'<p class="memory-note">{_esc(note)}</p>' if note else '<p class="memory-note muted">Пока без заметки — только сам факт этого вечера.</p>'}
            <div class="memory-foot">
              <div>{' · '.join(_esc(x) for x in meta)}</div>
              {f'<span class="artifact-mark">{" · ".join(artifact_bits)}</span>' if artifact_bits else ''}
            </div>
            <form method="post" action="/my-hockey/memory/{item.get("id")}/delete" class="memory-delete">
              <button type="submit" onclick="return confirm('Удалить это воспоминание?')">удалить</button>
            </form>
          </div>
        </article>""")
    return "".join(cards)


def render_memory_v541(season: str | None = None, saved: int = 0, error: str | None = None) -> str:
    all_data = base.STORE.load()
    seasons = all_data.get("seasons") or []
    today = datetime.now(core.MOSCOW).date()
    current_season = base.season_for_date(today)
    selected = (season or "").strip() or (seasons[0] if seasons else current_season)
    data = base.STORE.load(selected)
    matches = data.get("matches") or []
    storage_error = data.get("error") or all_data.get("error")

    season_values = sorted(set([*seasons, current_season]), reverse=True)
    filters = []
    for value in season_values:
        active = " active" if value == selected else ""
        filters.append(
            f'<a class="season-chip{active}" href="/my-hockey/memory?season={html.escape(value, quote=True)}">{_esc(value)}</a>'
        )

    if error:
        flash = f'<div class="memory-flash error">Не удалось сохранить: {_esc(error)}</div>'
    elif saved:
        flash = '<div class="memory-flash success">Воспоминание сохранено.</div>'
    elif storage_error:
        flash = f'<div class="memory-flash error">Хранилище недоступно: {_esc(storage_error)}</div>'
    else:
        flash = ""

    disabled = " disabled" if storage_error else ""

    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Память · Мой хоккей · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>
{COMMON_CSS}
:root{{--soyuz:#2a86d9;--soyuz-dim:#365c7d;--silver:#c8d0da}}
body{{background:radial-gradient(circle at 84% 3%,rgba(42,134,217,.07),transparent 27%),linear-gradient(180deg,#05070b,#080b0f 62%,#05070b)}}
.memory-hero{{display:grid;grid-template-columns:1fr auto;gap:28px;align-items:end;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}.memory-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.memory-hero p{{margin:0;color:#9aa4b2;max-width:760px;font-size:15px;line-height:1.55}}.memory-code{{text-align:right;color:#67778a;font-size:9px;letter-spacing:.12em;text-transform:uppercase}}.memory-code b{{display:block;color:#cfd6de;font-size:12px;letter-spacing:.05em;margin-bottom:5px}}
.mine-tabs{{display:flex;gap:8px;margin:18px 0;overflow:auto}}.mine-tabs a{{position:relative;text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}}.mine-tabs a.active{{color:#f2f5f8;border-color:#53616f;background:linear-gradient(180deg,#161c23,#0e1319)}}.mine-tabs a.active:after{{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--soyuz)}}
.memory-flash{{margin:0 0 14px;padding:11px 13px;border:1px solid #2a333f;border-radius:11px;background:#10151c;color:#aeb7c4;font-size:11px}}.memory-flash.success{{border-color:#365541;color:#bcd5c3}}.memory-flash.error{{border-color:#61363d;color:#efb4ba}}
.memory-toolbar{{display:flex;justify-content:space-between;align-items:center;gap:18px;margin:6px 0 20px}}.season-list{{display:flex;gap:7px;overflow:auto}}.season-chip{{text-decoration:none;border:1px solid #27323e;background:#0c1117;color:#758396;border-radius:999px;padding:6px 10px;font-size:9px;white-space:nowrap}}.season-chip.active{{color:#dce5ed;border-color:#396487;background:#0e1720}}.season-note{{color:#5f6e7f;font-size:9px}}
.memory-layout{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(310px,.55fr);gap:22px;align-items:start}}.memory-feed{{display:grid;gap:0}}
.memory-entry{{display:grid;grid-template-columns:128px 1fr;gap:24px;padding:8px 0 34px;position:relative}}.memory-entry:after{{content:"";position:absolute;left:127px;top:42px;bottom:0;width:1px;background:linear-gradient(#2d3b49,#161d25)}}.memory-date{{text-align:right;padding-top:8px;color:#8794a4;font-size:10px;line-height:1.4}}.memory-entry-body{{position:relative;border:1px solid #25303b;background:linear-gradient(180deg,#0f151b,#090d12);border-radius:17px;padding:20px 22px 18px}}.memory-entry-body:before{{content:"";position:absolute;width:7px;height:7px;border-radius:50%;background:#c8d0da;border:2px solid #10161d;left:-29px;top:20px;box-shadow:0 0 0 1px #365c7d}}.memory-kicker{{color:#66778b;font-size:8px;text-transform:uppercase;letter-spacing:.1em}}.memory-title-row{{display:flex;justify-content:space-between;gap:18px;align-items:start;margin-top:9px}}.memory-title-row h2{{margin:0;font-size:22px;line-height:1.2}}.memory-title-row h2 span{{color:#536274;font-weight:400}}.memory-title-row strong{{font-size:25px;line-height:1;font-variant-numeric:tabular-nums}}.memory-place{{color:#8290a0;font-size:10px;margin-top:9px}}.memory-note{{margin:19px 0 0;padding:0 0 0 15px;border-left:2px solid #304b65;color:#b9c2cc;font-size:12px;line-height:1.7;max-width:760px}}.memory-note.muted{{color:#697687;border-left-color:#28323d}}.memory-foot{{display:flex;justify-content:space-between;gap:14px;margin-top:18px;padding-top:12px;border-top:1px solid #1f2832;color:#657486;font-size:8px}}.artifact-mark{{color:#769ab9}}.memory-delete{{padding:0;margin-top:10px}}.memory-delete button{{border:0;background:transparent;color:#4f5b69;padding:0;font-size:7px;cursor:pointer}}.memory-delete button:hover{{color:#b57a82}}
.memory-empty{{min-height:360px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;border:1px dashed #26313d;border-radius:18px;padding:42px;background:radial-gradient(circle at 12% 20%,rgba(42,134,217,.045),transparent 34%),#080c10}}.empty-mark{{color:#53799a;font-size:18px;margin-bottom:17px}}.memory-empty h2{{font-size:24px;margin:0}}.memory-empty p{{color:#788697;font-size:11px;line-height:1.6;max-width:420px;margin:10px 0 18px}}.memory-empty a{{text-decoration:none;border:1px solid #38516a;border-radius:9px;padding:9px 11px;color:#a9bdd0;font-size:9px;background:#0d151d}}
.memory-side{{display:grid;gap:14px;position:sticky;top:18px}}.memory-add-card{{border:1px solid #293540;border-radius:16px;background:linear-gradient(180deg,#10161c,#090d12);overflow:hidden}}.memory-add-card summary{{cursor:pointer;list-style:none;padding:18px 19px}}.memory-add-card summary::-webkit-details-marker{{display:none}}.memory-add-card summary:after{{content:"＋";float:right;color:#5f9bd0;font-size:17px;margin-top:-26px}}.memory-add-card[open] summary:after{{content:"−"}}.memory-add-card summary span{{display:block;color:#6d7c8d;font-size:8px;letter-spacing:.1em;text-transform:uppercase}}.memory-add-card summary b{{display:block;font-size:16px;margin-top:5px}}.memory-add-card summary p{{color:#7a8797;font-size:9px;line-height:1.5;margin:7px 30px 0 0}}.memory-form-wrap{{border-top:1px solid #202a34;padding:0 18px 18px}}.memory-form{{display:grid;gap:10px;padding-top:14px}}.form-section{{margin-top:4px;color:#657588;font-size:8px;letter-spacing:.1em;text-transform:uppercase}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}label{{display:grid;gap:5px;color:#909baa;font-size:9px}}input,textarea{{width:100%;border:1px solid #303a47;border-radius:9px;background:#080c11;color:#eef2f6;padding:9px 10px}}input:focus,textarea:focus{{outline:none;border-color:#365c7d;box-shadow:0 0 0 2px rgba(42,134,217,.11)}}textarea{{min-height:108px;resize:vertical}}button.save{{border:1px solid #8b949e;border-radius:9px;background:linear-gradient(180deg,#d9dfe5,#bbc4cd);color:#0a0e13;padding:10px 12px;font-weight:850;cursor:pointer}}button:disabled,input:disabled,textarea:disabled{{opacity:.42;cursor:not-allowed}}
.artifact-box{{padding:14px 16px;border:1px solid #23313f;border-radius:14px;background:rgba(42,134,217,.025);color:#708399;font-size:9px;line-height:1.55}}.artifact-box b{{display:block;color:#a3b7ca;font-size:10px;margin-bottom:4px}}
.footer-note{{display:flex;justify-content:space-between;gap:20px;margin-top:30px;padding-top:15px;border-top:1px solid #1e252e;color:#596575;font-size:9px;text-transform:uppercase;letter-spacing:.05em}}
@media(max-width:900px){{.memory-layout{{grid-template-columns:1fr}}.memory-side{{position:static}}.memory-entry{{grid-template-columns:96px 1fr}}.memory-entry:after{{left:95px}}}}
@media(max-width:680px){{.memory-hero{{grid-template-columns:1fr;padding-top:26px}}.memory-hero h1{{font-size:42px}}.memory-code{{text-align:left}}.memory-toolbar{{align-items:flex-start;flex-direction:column}}.memory-entry{{display:block;padding-bottom:18px}}.memory-entry:after,.memory-entry-body:before{{display:none}}.memory-date{{text-align:left;padding:0 0 8px}}.two{{grid-template-columns:1fr}}.footer-note{{flex-direction:column}}}}
</style></head><body><main class="hub-shell">{topbar('mine')}
<section class="memory-hero"><div><div class="hub-eyebrow">Мой хоккей · v0.54.1</div><h1>Память</h1><p>Матчи проходят. Здесь остаётся то, что хочется помнить.</p></div><div class="memory-code"><b>MATCHES / PLACES / PEOPLE</b>билеты · фотографии · несколько строк о вечере</div></section>
<nav class="mine-tabs"><a href="/my-hockey">Я</a><a href="/my-hockey/environment">Моя хоккейная среда</a><a href="/my-hockey/closet">Хоккейный шкаф</a><a class="active" href="/my-hockey/memory">Память</a></nav>
{flash}
<section class="memory-toolbar"><div class="season-list">{''.join(filters)}</div><div class="season-note">хоккейная глава · {_esc(selected)}</div></section>
<section class="memory-layout">
  <div class="memory-feed">{_album_cards(matches)}</div>
  <aside class="memory-side" id="new-memory">
    <details class="memory-add-card"{' open' if error else ''}>
      <summary><span>НОВАЯ ЗАПИСЬ</span><b>Добавить воспоминание</b><p>Матч, место, компания и несколько строк о том, что осталось в памяти.</p></summary>
      <div class="memory-form-wrap"><form class="memory-form" method="post" action="/my-hockey/memory">
        <div class="form-section">Вечер</div>
        <div class="two"><label>Дата<input type="date" name="match_date" value="{today.isoformat()}" required{disabled}></label><label>Турнир<input name="competition" placeholder="КХЛ / ВХЛ / ..."{disabled}></label></div>
        <div class="two"><label>Хозяева<input name="home_team" required placeholder="СКА"{disabled}></label><label>Гости<input name="away_team" required placeholder="Спартак"{disabled}></label></div>
        <div class="two"><label>Счёт хозяев<input type="number" min="0" name="home_score"{disabled}></label><label>Счёт гостей<input type="number" min="0" name="away_score"{disabled}></label></div>
        <div class="form-section">Место и люди</div>
        <label>Арена<input name="arena" placeholder="СКА Арена"{disabled}></label>
        <div class="two"><label>Сектор<input name="sector" placeholder="216"{disabled}></label><label>Место<input name="seat" placeholder="ряд / место"{disabled}></label></div>
        <label>С кем ходил<input name="companions" placeholder="Тёма / Ксюша / друзья"{disabled}></label>
        <div class="form-section">Главное</div>
        <label>Что хочется запомнить<textarea name="note" placeholder="Атмосфера, момент матча, разговор, ощущение — всё, что захочется вспомнить через несколько лет."{disabled}></textarea></label>
        <button class="save" type="submit"{disabled}>Сохранить воспоминание</button>
      </form></div>
    </details>
    <div class="artifact-box"><b>Билет и фотографии</b>Следующим слоем привяжем их к конкретному воспоминанию. Здесь они будут частью вечера, а не отдельной фотогалереей.</div>
  </aside>
</section>
<footer class="footer-note"><span>Hockey Hub · Память</span><span>вечера · люди · места · то, что осталось</span></footer>
</main></body></html>"""
    return page


def _bump_personal(saved: bool = False, error: str | None = None) -> str:
    return _previous_personal(saved=saved, error=error).replace("v0.54", "v0.54.1", 1)


def _bump_closet(saved: str | None = None, error: str | None = None) -> str:
    return _previous_closet(saved=saved, error=error).replace("v0.54", "v0.54.1", 1)


def _bump_environment() -> str:
    return _previous_environment().replace("v0.54", "v0.54.1", 1)


def _bump_home() -> str:
    page = _previous_home()
    soup = BeautifulSoup(page, "html.parser")
    eyebrow = soup.select_one(".hero .eyebrow")
    if eyebrow:
        eyebrow.string = "Hockey Hub · v0.54.1 · персональный briefing"
    return str(soup)


base.render_memory = render_memory_v541
personal_base.render_personal_page = _bump_personal
closet_v48.render_closet = _bump_closet
environment_v50.render_environment = _bump_environment
core.render_page = _bump_home
core.app.version = "0.54.1"

app = core.app
