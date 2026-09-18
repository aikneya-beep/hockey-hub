from __future__ import annotations

from datetime import datetime, timedelta

from bs4 import BeautifulSoup

import app_v52
import app_v05 as core
import personal_hockey_v42 as personal_base


_previous_renderer = personal_base.render_personal_page


def _avg_load_30_days() -> tuple[float | None, int]:
    try:
        sessions = (personal_base.STORE.load() or {}).get("sessions") or []
    except Exception:
        return None, 0
    today = datetime.now(core.MOSCOW).date()
    cutoff = today - timedelta(days=29)
    values: list[float] = []
    for row in sessions:
        try:
            day = datetime.strptime(str(row.get("date") or ""), "%Y-%m-%d").date()
        except Exception:
            continue
        load = row.get("load")
        if cutoff <= day <= today and isinstance(load, (int, float)):
            values.append(float(load))
    return ((sum(values) / len(values)) if values else None), len(values)


def render_personal_v521(saved: bool = False, error: str | None = None) -> str:
    page = _previous_renderer(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")

    # Best lap is already fully represented by the benchmark block below.
    # The top KPI should describe current training state instead.
    stats = soup.select("section.stats > article.stat")
    if stats:
        avg, count = _avg_load_30_days()
        stat = stats[0]
        label = stat.find("span")
        strong = stat.find("strong")
        note = stat.find("em")
        if label:
            label.string = "Средняя нагрузка · 30 дней"
        if strong:
            strong.clear()
            if avg is None:
                strong.append("—")
            else:
                strong.append(f"{avg:.1f}")
                small = soup.new_tag("small")
                small.string = "/10"
                strong.append(" ")
                strong.append(small)
        if note:
            note.string = f"по {count} тренировк{'е' if count == 1 else 'ам' if count in (2,3,4) else 'ам'} с оценкой нагрузки" if count else "пока нет оценок нагрузки"

    # Current focus already has a dedicated card directly above. Keep the
    # development strip for actions/checkpoints only.
    focus = soup.select_one(".dev-strip .dev-kpi.focus")
    if focus:
        focus.decompose()

    style = soup.find("style")
    if style:
        style.append(r"""
/* v0.52.1: remove duplicate focus/best-lap emphasis */
.dev-strip{grid-template-columns:.7fr .7fr 1.6fr}
.dev-kpi{min-height:92px}
.benchmark-row .chart-wrap{padding-top:13px;padding-bottom:12px}
.benchmark-row .chart-wrap svg{height:145px}
@media(max-width:950px){.dev-strip{grid-template-columns:1fr 1fr 1.5fr}}
@media(max-width:620px){.dev-strip{grid-template-columns:1fr}.benchmark-row .chart-wrap svg{height:132px}}
""")

    text = str(soup)
    if "v0.52.0" in text:
        text = text.replace("v0.52.0", "v0.52.1", 1)
    else:
        text = text.replace("v0.52", "v0.52.1", 1)
    return text


personal_base.render_personal_page = render_personal_v521
core.app.version = "0.52.1"

app = core.app
