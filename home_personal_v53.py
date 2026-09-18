from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
import html

from bs4 import BeautifulSoup

import app_v521  # current production stack
import app_v05 as core
import auth_v49
import personal_hockey_v42 as personal_base
import development_v52


_HOME_AUTH: ContextVar[bool] = ContextVar("hockey_hub_home_authenticated", default=False)
_previous_home = core.render_page


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _date_label(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d.%m")
    except Exception:
        return str(raw)


def _active(rows: list[dict]) -> list[dict]:
    return [x for x in rows if x.get("status") == "active"]


def _nearest_goal(goals: list[dict]) -> dict | None:
    active = _active(goals)
    dated = [x for x in active if x.get("target_date")]
    if dated:
        return sorted(dated, key=lambda x: x.get("target_date") or "9999-12-31")[0]
    return active[0] if active else None


def _personal_briefing_html() -> str:
    try:
        personal = personal_base.STORE.load() or {}
        development = development_v52.STORE.load() or {}
    except Exception as exc:
        print(f"[home-personal] load failed: {type(exc).__name__}: {exc}", flush=True)
        return '<div class="home-personal-error">Личный briefing временно недоступен. Публичная Главная работает нормально.</div>'

    sessions = sorted(personal.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
    notes = sorted(personal.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
    goals = development.get("goals") or []
    homework = development.get("homework") or []

    latest = sessions[0] if sessions else None
    focus = notes[0] if notes else None
    active_goals = _active(goals)
    active_hw = _active(homework)
    checkpoint = _nearest_goal(goals)

    if latest:
        latest_title = latest.get("type") or "Тренировка"
        latest_meta = f'{_date_label(latest.get("date"))} · нагрузка {latest.get("load")}/10' if latest.get("load") is not None else _date_label(latest.get("date"))
    else:
        latest_title = "Тренировок пока нет"
        latest_meta = "добавь первую запись"

    focus_text = focus.get("text") if focus else "Новый фокус Тёмы пока не записан"
    focus_date = _date_label(focus.get("date")) if focus else "—"

    if checkpoint:
        checkpoint_title = checkpoint.get("title") or "Контрольная точка"
        checkpoint_meta = _date_label(checkpoint.get("target_date")) if checkpoint.get("target_date") else "без даты"
    else:
        checkpoint_title = "Контрольная точка не задана"
        checkpoint_meta = "можно добавить в «Я»"

    return f'''<div class="home-personal-grid">
      <a class="home-personal-item primary" href="/my-hockey">
        <span>ПОСЛЕДНЯЯ ТРЕНИРОВКА</span><b>{_esc(latest_title)}</b><em>{_esc(latest_meta)}</em>
      </a>
      <a class="home-personal-item" href="/my-hockey/environment">
        <span>ФОКУС ТЁМЫ · {focus_date}</span><b>{_esc(focus_text)}</b>
      </a>
      <a class="home-personal-item counter" href="/my-hockey#development">
        <span>В РАБОТЕ</span><strong>{len(active_goals)} <i>целей</i> · {len(active_hw)} <i>ДЗ</i></strong>
      </a>
      <a class="home-personal-item checkpoint" href="/my-hockey#development">
        <span>КОНТРОЛЬНАЯ ТОЧКА</span><b>{_esc(checkpoint_title)}</b><em>{_esc(checkpoint_meta)}</em>
      </a>
    </div>'''


def render_home_v53() -> str:
    page = _previous_home()
    if not _HOME_AUTH.get():
        soup = BeautifulSoup(page, "html.parser")
        for node in soup.find_all(string=True):
            raw = str(node)
            if "HOCKEY HUB" in raw and "ПЕРСОНАЛЬНЫЙ BRIEFING" in raw:
                node.replace_with("HOCKEY HUB · v0.53.1 · ПЕРСОНАЛЬНЫЙ BRIEFING")
                break
        return str(soup)

    soup = BeautifulSoup(page, "html.parser")
    card = soup.select_one("article.personal-box")
    if card:
        title = card.select_one(".world-title h3")
        link = card.select_one(".world-title a")
        if title:
            title.string = "Мой хоккей"
        if link:
            link.string = "открыть →"
            link["href"] = "/my-hockey"
        old = card.select_one(".esk-line")
        if old:
            old.replace_with(BeautifulSoup(_personal_briefing_html(), "html.parser"))

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.53: authenticated personal briefing on the daily page */
.personal-box{padding-bottom:14px}
.home-personal-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:8px}
.home-personal-item{display:block;min-width:0;padding:10px 11px;background:#090f15;border:1px solid #263443;border-radius:10px;text-decoration:none}
.home-personal-item.primary{box-shadow:inset 2px 0 #2a86d9}
.home-personal-item span{display:block;color:#64778c;font-size:7px;letter-spacing:.08em;margin-bottom:5px}
.home-personal-item b{display:block;color:#d9e0e8;font-size:9px;line-height:1.35;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.home-personal-item em{display:block;color:#637386;font-size:7px;font-style:normal;margin-top:4px}
.home-personal-item.counter strong{display:block;color:#dce3ea;font-size:16px;line-height:1.2}
.home-personal-item.counter i{font-size:8px;font-style:normal;color:#76879a;font-weight:600}
.home-personal-item.checkpoint b{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.home-personal-error{color:#8a98a9;font-size:9px;line-height:1.5;padding:10px 0}
@media(max-width:560px){.home-personal-grid{grid-template-columns:1fr}}
""")

    for node in soup.find_all(string=True):
        raw = str(node)
        if "HOCKEY HUB" in raw and "ПЕРСОНАЛЬНЫЙ BRIEFING" in raw:
            node.replace_with("HOCKEY HUB · v0.53.1 · ПЕРСОНАЛЬНЫЙ BRIEFING")
            break
    return str(soup)


@core.app.middleware("http")
async def home_personal_context(request, call_next):
    authenticated = False
    if request.url.path == "/":
        try:
            authenticated = auth_v49.verify_session_token(request.cookies.get(auth_v49.COOKIE_NAME))
        except Exception:
            authenticated = False

    token = _HOME_AUTH.set(authenticated)
    try:
        response = await call_next(request)
    finally:
        _HOME_AUTH.reset(token)

    if request.url.path == "/" and authenticated:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
    return response


core.render_page = render_home_v53
core.app.version = "0.53.1"

app = core.app
