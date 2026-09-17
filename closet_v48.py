from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date, timedelta
import html
from urllib.parse import urlparse

from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

import app_v05 as core
import personal_hockey_v42 as personal_base
from closet_store_v48 import ClosetStore
from design_system_v46 import COMMON_CSS, topbar

STORE = ClosetStore()
_previous_personal_renderer = personal_base.render_personal_page


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def _date_label(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(raw)


def _money(value: float | None, currency: str = "₽") -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + f" {currency}"


def _safe_url(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return text
    except Exception:
        pass
    return None


def _condition_class(value: str | None) -> str:
    text = (value or "").lower()
    if any(word in text for word in ("замен", "ремонт", "плохо", "износ", "вниман")):
        return "attention"
    if any(word in text for word in ("нов", "отлич")):
        return "fresh"
    return "normal"


def _gear_cards(items: list[dict]) -> str:
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
            cls = _condition_class(condition)
            details = []
            if item.get("color"):
                details.append(f"цвет: {_esc(item['color'])}")
            if item.get("purchased_on"):
                details.append(f"куплено: {_date_label(item['purchased_on'])}")
            if item.get("purchase_price") is not None:
                details.append(f"цена: {_money(item['purchase_price'])}")
            service = ""
            if item.get("next_service_on"):
                service = f'<div class="service-line"><span>Следующее обслуживание</span><b>{_date_label(item["next_service_on"])}</b></div>'
            notes = f'<p>{_esc(item.get("notes"))}</p>' if item.get("notes") else ""
            cards.append(
                f'''<article class="gear-card {cls}">
                  <div class="gear-top"><span class="condition-dot"></span><span class="condition-label">{_esc(condition)}</span></div>
                  <h3>{_esc(item.get('name'))}</h3>
                  <div class="brand-line">{_esc(brand_line)}</div>
                  <div class="gear-meta">{' · '.join(details) if details else 'параметры пока не заполнены'}</div>
                  {service}{notes}
                </article>'''
            )
        blocks.append(
            f'''<section class="gear-group"><div class="group-head"><h2>{_esc(category)}</h2><span>{len(cards)}</span></div><div class="gear-grid">{''.join(cards)}</div></section>'''
        )
    return "".join(blocks)


def _service_rows(items: list[dict]) -> str:
    today = datetime.now(core.MOSCOW).date()
    rows = []
    for item in items:
        raw = item.get("next_service_on")
        if not raw:
            continue
        try:
            due = datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            continue
        days = (due - today).days
        if days < 0:
            state = f"просрочено на {abs(days)} дн."
            cls = "late"
        elif days == 0:
            state = "сегодня"
            cls = "soon"
        elif days <= 30:
            state = f"через {days} дн."
            cls = "soon"
        else:
            state = f"через {days} дн."
            cls = "ok"
        rows.append((due, f'''<article class="service-row {cls}"><div><b>{_esc(item.get('name'))}</b><span>{_esc(item.get('brand') or item.get('category'))}</span></div><div><strong>{_date_label(raw)}</strong><em>{state}</em></div></article>'''))
    rows.sort(key=lambda x: x[0])
    if not rows:
        return '<div class="empty-state compact">Пока нет запланированного обслуживания. Его можно задать в карточке новой вещи.</div>'
    return "".join(row for _, row in rows[:6])


def _wishlist_cards(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty-state compact">Wishlist пока пуст. Добавь то, что хочешь купить или отслеживать.</div>'
    cards = []
    for row in rows:
        target = row.get("target_price")
        current = row.get("current_price")
        delta = None
        if target is not None and current is not None and current > 0:
            delta = (current - target) / current * 100
        price_note = ""
        if delta is not None:
            if delta <= 0:
                price_note = '<span class="price-hit">цель достигнута</span>'
            else:
                price_note = f'<span class="price-gap">ещё {delta:.0f}% до цели</span>'
        link = _safe_url(row.get("url"))
        name = _esc(row.get("name"))
        title = f'<a href="{html.escape(link, quote=True)}" target="_blank" rel="noopener">{name} ↗</a>' if link else name
        cards.append(
            f'''<article class="wish-card">
              <div class="wish-kicker">{_esc(row.get('category'))}{' · ' + _esc(row.get('store')) if row.get('store') else ''}</div>
              <h3>{title}</h3>
              <div class="wish-brand">{_esc(row.get('brand') or 'бренд не указан')}</div>
              <div class="price-grid"><div><span>Сейчас</span><b>{_money(current)}</b></div><div><span>Цель</span><b>{_money(target)}</b></div></div>
              {price_note}
              {f'<p>{_esc(row.get("notes"))}</p>' if row.get('notes') else ''}
            </article>'''
        )
    return "".join(cards)


def render_closet(saved: str | None = None, error: str | None = None) -> str:
    data = STORE.load()
    items = data.get("items") or []
    wishlist = data.get("wishlist") or []
    storage = data.get("storage") or STORE.status()
    db_ready = bool(storage.get("enabled")) and not storage.get("error")

    today = datetime.now(core.MOSCOW).date()
    attention = 0
    for item in items:
        if _condition_class(item.get("condition")) == "attention":
            attention += 1
            continue
        raw = item.get("next_service_on")
        if raw:
            try:
                if datetime.strptime(raw, "%Y-%m-%d").date() <= today + timedelta(days=30):
                    attention += 1
            except Exception:
                pass
    monitored = sum(1 for row in wishlist if row.get("store") or row.get("url"))

    if error:
        flash = f'<div class="closet-flash error">Не удалось сохранить: {_esc(error)}</div>'
    elif saved == "gear":
        flash = '<div class="closet-flash success">Вещь добавлена в шкаф.</div>'
    elif saved == "wish":
        flash = '<div class="closet-flash success">Позиция добавлена в wishlist.</div>'
    elif db_ready:
        flash = '<div class="closet-flash ready"><span></span>PostgreSQL подключён · шкаф сохраняется постоянно.</div>'
    else:
        flash = f'<div class="closet-flash error">PostgreSQL недоступен: {_esc(storage.get("error") or "DATABASE_URL не подключён")}</div>'

    disabled = "" if db_ready else " disabled"
    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Хоккейный шкаф · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>
{COMMON_CSS}
:root{{--soyuz:#2a86d9;--soyuz-dim:#365c7d;--silver:#c8d0da}}
body{{background:radial-gradient(circle at 82% 5%,rgba(42,134,217,.11),transparent 24%),linear-gradient(180deg,#05070b,#070a0e 60%,#05070b)}}
.closet-hero{{display:grid;grid-template-columns:1fr auto;align-items:end;gap:24px;padding:34px 0 24px;border-bottom:1px solid var(--hub-line-soft)}}.closet-hero h1{{font-size:52px;line-height:.96;letter-spacing:-.035em;margin:9px 0 10px}}.closet-hero p{{margin:0;color:#929cab;max-width:720px}}.kit-code{{text-align:right;color:#708094;font-size:10px;letter-spacing:.12em;text-transform:uppercase}}.kit-code b{{display:block;color:#d8dee6;font-size:13px;letter-spacing:.04em;margin-bottom:4px}}
.mine-tabs{{display:flex;gap:8px;margin:18px 0 0;overflow:auto}}.mine-tabs a{{position:relative;text-decoration:none;color:#8b96a5;background:#0d1218;border:1px solid #242d38;border-radius:10px;padding:9px 13px;font-size:11px;white-space:nowrap}}.mine-tabs a.active{{color:#f2f5f8;border-color:#53616f;background:linear-gradient(180deg,#161c23,#0e1319)}}.mine-tabs a.active:after{{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--soyuz);box-shadow:0 0 10px rgba(42,134,217,.3)}}
.closet-flash{{margin:18px 0 0;padding:11px 13px;border:1px solid #2a333f;border-radius:11px;background:#10151c;color:#aeb7c4;font-size:11px}}.closet-flash.ready span{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#8eb89a;margin-right:8px}}.closet-flash.success{{border-color:#365541;color:#bcd5c3}}.closet-flash.error{{border-color:#61363d;color:#efb4ba}}
.closet-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 18px}}.closet-stat{{position:relative;overflow:hidden;min-height:104px;padding:16px;background:linear-gradient(180deg,#10151c,#0a0e13);border:1px solid #242d38;border-radius:15px}}.closet-stat:before{{content:"";position:absolute;left:16px;top:0;width:18%;height:2px;background:linear-gradient(90deg,var(--soyuz),var(--soyuz-dim))}}.closet-stat span{{display:block;color:#748091;font-size:9px;text-transform:uppercase;letter-spacing:.1em}}.closet-stat b{{display:block;font-size:29px;margin-top:12px}}.closet-stat em{{display:block;color:#6e7a89;font-style:normal;font-size:9px;margin-top:7px}}
.closet-layout{{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.55fr);gap:14px}}.panel{{padding:18px}}.section-title{{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:15px}}.section-title h2{{margin:0;font-size:15px}}.section-title span{{color:#6f7d8d;font-size:9px;text-transform:uppercase;letter-spacing:.12em}}
.gear-group{{margin-top:20px}}.gear-group:first-child{{margin-top:0}}.group-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}}.group-head h2{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#8390a0;margin:0}}.group-head span{{font-size:9px;color:#556170}}.gear-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}}.gear-card{{position:relative;overflow:hidden;padding:14px;background:#090d12;border:1px solid #242d37;border-radius:13px;min-height:150px}}.gear-card:after{{content:"";position:absolute;right:-8px;top:14px;width:48px;height:2px;background:linear-gradient(90deg,transparent,var(--soyuz),transparent);transform:rotate(-34deg);opacity:.35}}.gear-top{{display:flex;align-items:center;gap:6px;color:#768394;font-size:8px;text-transform:uppercase;letter-spacing:.08em}}.condition-dot{{width:6px;height:6px;border-radius:50%;background:#8996a5}}.gear-card.fresh .condition-dot{{background:#89b59a}}.gear-card.attention .condition-dot{{background:#d4966a}}.gear-card h3{{font-size:14px;margin:13px 0 4px}}.brand-line{{font-size:11px;color:#91a7bd}}.gear-meta{{font-size:9px;color:#697586;margin-top:10px;line-height:1.5}}.gear-card p{{font-size:9px;color:#7e8998;line-height:1.5;margin:10px 0 0}}.service-line{{display:flex;justify-content:space-between;gap:10px;border-top:1px solid #202833;margin-top:11px;padding-top:9px;font-size:8px;color:#687584}}.service-line b{{color:#aebac7}}
.side-stack{{display:grid;gap:14px;align-content:start}}.service-row{{display:flex;justify-content:space-between;gap:10px;padding:11px 0;border-top:1px solid #202833}}.service-row:first-child{{border-top:0}}.service-row b,.service-row strong{{display:block;font-size:10px}}.service-row span,.service-row em{{display:block;font-style:normal;color:#687585;font-size:8px;margin-top:3px}}.service-row.soon em{{color:#c9a36b}}.service-row.late em{{color:#d88484}}.service-row.ok em{{color:#6f8e78}}
.wish-section{{margin-top:14px}}.wish-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.wish-card{{position:relative;overflow:hidden;padding:14px;background:#090d12;border:1px solid #25303b;border-radius:13px;min-height:155px}}.wish-card:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:linear-gradient(var(--soyuz),#355e80)}}.wish-kicker{{font-size:8px;color:#65768a;text-transform:uppercase;letter-spacing:.08em}}.wish-card h3{{font-size:13px;margin:10px 0 3px}}.wish-card h3 a{{text-decoration:none}}.wish-card h3 a:hover{{color:#8dbbe1}}.wish-brand{{font-size:9px;color:#748092}}.price-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:13px}}.price-grid span{{display:block;color:#687485;font-size:8px}}.price-grid b{{display:block;font-size:12px;margin-top:4px}}.price-hit,.price-gap{{display:inline-block;font-size:8px;margin-top:10px;padding:3px 6px;border-radius:999px}}.price-hit{{color:#a9d3b3;border:1px solid #34523c}}.price-gap{{color:#86acd0;border:1px solid #2c4d69}}.wish-card p{{font-size:9px;color:#758192;line-height:1.45}}
.forms{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}details.form-card{{border:1px solid #28323e;border-radius:15px;background:#0c1015;overflow:hidden}}details.form-card summary{{cursor:pointer;list-style:none;padding:15px 17px;font-size:12px;font-weight:750}}details.form-card summary::-webkit-details-marker{{display:none}}details.form-card summary:after{{content:"＋";float:right;color:var(--soyuz)}}details.form-card[open] summary:after{{content:"−"}}.form-body{{border-top:1px solid #202833;padding:14px 17px 17px}}form{{display:grid;gap:10px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}label{{display:grid;gap:5px;color:#909baa;font-size:9px}}input,textarea,select{{width:100%;border:1px solid #303a47;border-radius:9px;background:#080c11;color:#eef2f6;padding:9px 10px}}input:focus,textarea:focus,select:focus{{outline:none;border-color:#365c7d;box-shadow:0 0 0 2px rgba(42,134,217,.11)}}textarea{{min-height:62px;resize:vertical}}button.save{{border:1px solid #8b949e;border-radius:9px;background:linear-gradient(180deg,#d9dfe5,#bbc4cd);color:#0a0e13;padding:10px 12px;font-weight:850;cursor:pointer}}button:disabled,input:disabled,textarea:disabled,select:disabled{{opacity:.42;cursor:not-allowed}}.form-note,.empty-state{{color:#6f7a89;font-size:9px;line-height:1.5}}.empty-state{{padding:18px;border:1px dashed #2a3440;border-radius:12px}}.empty-state.compact{{padding:12px}}
.monitor-note{{margin-top:12px;padding:12px 13px;border:1px solid #213447;border-radius:11px;background:rgba(42,134,217,.035);color:#7891a8;font-size:9px;line-height:1.5}}.monitor-note b{{color:#a6bed4}}
@media(max-width:900px){{.closet-layout{{grid-template-columns:1fr}}.wish-grid{{grid-template-columns:1fr 1fr}}.forms{{grid-template-columns:1fr}}}}
@media(max-width:760px){{.closet-hero{{grid-template-columns:1fr;padding-top:26px}}.closet-hero h1{{font-size:42px}}.kit-code{{text-align:left}}.closet-stats{{grid-template-columns:1fr 1fr}}.gear-grid,.wish-grid,.two{{grid-template-columns:1fr}}}}
</style></head><body><main class="hub-shell">{topbar('mine')}
<section class="closet-hero"><div><div class="hub-eyebrow">Мой хоккей · v0.48</div><h1>Хоккейный шкаф</h1><p>Экипировка, обслуживание, расходники, спортпит, wishlist и цены — в одном месте.</p></div><div class="kit-code"><b>BLACK / SILVER / SOYUZ BLUE</b>комплект игрока · личный инвентарь</div></section>
<nav class="mine-tabs"><a href="/my-hockey">Я</a><a href="/my-hockey#tema">Тёма и команды</a><a class="active" href="/my-hockey/closet">Хоккейный шкаф</a><a href="/my-hockey#memory">Память</a></nav>
{flash}
<section class="closet-stats"><article class="closet-stat"><span>В шкафу</span><b>{len(items)}</b><em>вещей и комплектов</em></article><article class="closet-stat"><span>Требует внимания</span><b>{attention}</b><em>износ или обслуживание ≤30 дней</em></article><article class="closet-stat"><span>Wishlist</span><b>{len(wishlist)}</b><em>хочу купить / отслеживаю</em></article><article class="closet-stat"><span>С источником</span><b>{monitored}</b><em>магазин или ссылка указаны</em></article></section>
<section class="closet-layout"><article class="hub-card panel"><div class="section-title"><h2>Комплект</h2><span>что уже есть</span></div>{_gear_cards(items)}</article><aside class="side-stack"><article class="hub-card panel"><div class="section-title"><h2>Обслуживание</h2><span>ближайшее</span></div>{_service_rows(items)}</article><article class="hub-card panel"><div class="section-title"><h2>Стиль комплекта</h2><span>принцип</span></div><div class="empty-state compact">Чёрная база, минимум коммерческих лейблов, серебро как технический металл и несколько процентов холодного синего — только прожилками.</div></article></aside></section>
<section class="hub-card panel wish-section"><div class="section-title"><h2>Wishlist и мониторинг цен</h2><span>следим, а не скроллим магазины</span></div><div class="wish-grid">{_wishlist_cards(wishlist)}</div><div class="monitor-note"><b>Автоматический мониторинг ещё не включён.</b> Уже сейчас сохраняются целевая/текущая цена, магазин и ссылка. Следующим этапом подключим проверку выбранных магазинов и уведомления только при полезном изменении.</div></section>
<section class="forms"><details class="form-card"{' open' if saved == 'gear' and error else ''}><summary>Добавить вещь</summary><div class="form-body"><form method="post" action="/my-hockey/closet/item"><div class="two"><label>Категория<select name="category"{disabled}><option>Защита</option><option>Коньки</option><option>Клюшки</option><option>Одежда</option><option>Сумки и аксессуары</option><option>Расходники</option><option>Спортпит</option><option>Атрибутика</option><option>Другое</option></select></label><label>Название<input name="name" required placeholder="Нагрудник"{disabled}></label></div><div class="two"><label>Бренд<input name="brand" placeholder="Soyuz"{disabled}></label><label>Модель<input name="model" placeholder="если знаешь"{disabled}></label></div><div class="two"><label>Цвет<input name="color" placeholder="чёрный"{disabled}></label><label>Состояние<select name="condition"{disabled}><option>новое</option><option selected>в игре</option><option>есть износ</option><option>нужен ремонт</option><option>на замену</option></select></label></div><div class="two"><label>Куплено<input type="date" name="purchased_on"{disabled}></label><label>Цена, ₽<input inputmode="decimal" name="purchase_price"{disabled}></label></div><label>Следующее обслуживание<input type="date" name="next_service_on"{disabled}></label><label>Заметка<textarea name="notes" placeholder="размер, особенности, что менять"{disabled}></textarea></label><button class="save" type="submit"{disabled}>Добавить в шкаф</button></form></div></details>
<details class="form-card"><summary>Добавить в wishlist</summary><div class="form-body"><form method="post" action="/my-hockey/closet/wishlist"><div class="two"><label>Категория<select name="category"{disabled}><option>Экипировка</option><option>Расходники</option><option>Спортпит</option><option>Атрибутика</option><option>Другое</option></select></label><label>Название<input name="name" required placeholder="Что ищем"{disabled}></label></div><label>Бренд<input name="brand"{disabled}></label><div class="two"><label>Текущая цена, ₽<input inputmode="decimal" name="current_price"{disabled}></label><label>Купить при, ₽<input inputmode="decimal" name="target_price"{disabled}></label></div><div class="two"><label>Магазин<input name="store" placeholder="Ozon / Яндекс / ..."{disabled}></label><label>Ссылка<input type="url" name="url" placeholder="https://..."{disabled}></label></div><label>Заметка<textarea name="notes" placeholder="размер, цвет, условия"{disabled}></textarea></label><button class="save" type="submit"{disabled}>Добавить в wishlist</button></form></div></details></section>
</main></body></html>'''
    return page


def patch_personal_page(saved: bool = False, error: str | None = None) -> str:
    page = _previous_personal_renderer(saved=saved, error=error)
    page = page.replace('href="#closet">Хоккейный шкаф</a>', 'href="/my-hockey/closet">Хоккейный шкаф</a>', 1)
    page = page.replace('<h3>Хоккейный шкаф</h3>', '<h3><a href="/my-hockey/closet" style="text-decoration:none">Хоккейный шкаф →</a></h3>', 1)
    return page


personal_base.render_personal_page = patch_personal_page


@core.app.get("/my-hockey/closet", response_class=HTMLResponse)
def hockey_closet(saved: str | None = None, error: str | None = None):
    return render_closet(saved=saved, error=error)


@core.app.post("/my-hockey/closet/item")
def add_closet_item(
    category: str = Form("Другое"), name: str = Form(...), brand: str = Form(""), model: str = Form(""),
    color: str = Form(""), condition: str = Form("в игре"), purchased_on: str = Form(""),
    purchase_price: str = Form(""), next_service_on: str = Form(""), notes: str = Form(""),
):
    try:
        STORE.add_item(
            category=category, name=name, brand=brand, model=model, color=color, condition=condition,
            purchased_on=_date(purchased_on), purchase_price=purchase_price,
            next_service_on=_date(next_service_on), notes=notes,
        )
        return RedirectResponse("/my-hockey/closet?saved=gear", status_code=303)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:180]
        return HTMLResponse(render_closet(error=message), status_code=503)


@core.app.post("/my-hockey/closet/wishlist")
def add_closet_wishlist(
    category: str = Form("Другое"), name: str = Form(...), brand: str = Form(""),
    target_price: str = Form(""), current_price: str = Form(""), store: str = Form(""),
    url: str = Form(""), notes: str = Form(""),
):
    try:
        STORE.add_wishlist(
            category=category, name=name, brand=brand, target_price=target_price, current_price=current_price,
            store=store, url=url, notes=notes,
        )
        return RedirectResponse("/my-hockey/closet?saved=wish", status_code=303)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:180]
        return HTMLResponse(render_closet(error=message), status_code=503)


@core.app.get("/api/v1/personal-hockey/closet")
def closet_api():
    return STORE.load()
