from __future__ import annotations

from datetime import datetime, timedelta

from bs4 import BeautifulSoup

import app_v05 as core
import home_v44
import personal_hockey_v42 as personal_base
import closet_v48
import environment_v50 as environment_base
from design_system_v46 import COMMON_CSS, topbar


_previous_home = core.render_page
_previous_big = home_v44.render_big_hockey_v44
_previous_personal = personal_base.render_personal_page
_previous_closet = closet_v48.render_closet
_previous_environment = environment_base.render_environment


def _append_css(page: str, css: str) -> str:
    return page.replace("</style>", css + "\n</style>", 1)


def render_home_v51() -> str:
    page = _previous_home()
    soup = BeautifulSoup(page, "html.parser")

    # The architecture explainer duplicated the global navigation and the
    # compact My Hockey preview directly above it. It was useful while the
    # product was still a mock-up, but is now onboarding noise.
    for article in soup.select("section.lower > article.card"):
        heading = article.find("h2")
        if heading and heading.get_text(" ", strip=True) == "Два мира одной системы":
            parent = article.parent
            article.decompose()
            if parent:
                classes = list(parent.get("class") or [])
                if "single" not in classes:
                    classes.append("single")
                parent["class"] = classes
            break

    page = str(soup)
    page = page.replace("v0.50.2", "v0.51")
    page = _append_css(
        page,
        """
/* v0.51: the daily page contains information, not an architecture diagram */
.lower.single{grid-template-columns:1fr}
.personal-box .lock-note{max-width:250px;line-height:1.45}
@media(max-width:900px){.personal-box .lock-note{max-width:none}}
""",
    )
    return page


def render_big_v51() -> str:
    page = _previous_big()
    soup = BeautifulSoup(page, "html.parser")
    old_header = soup.find("header")
    if old_header:
        shared = BeautifulSoup(topbar("big"), "html.parser").find("header")
        if shared:
            old_header.replace_with(shared)
    page = str(soup)
    # Reuse the exact same navigation system as the rest of Hockey Hub.
    page = _append_css(
        page,
        COMMON_CSS
        + """
/* v0.51: align Big Hockey shell/navigation with the rest of Hockey Hub */
.wrap{max-width:1180px}
.hub-topbar{height:72px;display:grid;grid-template-columns:auto 1fr;gap:32px;align-items:center;justify-content:initial}
.hub-nav{display:flex;gap:26px;align-items:center;justify-content:flex-start}
.hub-nav a{font-size:13px}
@media(max-width:760px){
  .hub-topbar{height:auto;padding-top:14px;grid-template-columns:1fr}
  .hub-nav{height:44px;overflow:auto;border-top:1px solid var(--hub-line-soft);padding-top:12px;gap:20px}
}
""",
    )
    return page


def _sessions_last_30_days() -> int:
    try:
        data = personal_base.STORE.load()
        sessions = data.get("sessions") or []
    except Exception:
        return 0
    today = datetime.now(core.MOSCOW).date()
    cutoff = today - timedelta(days=29)
    count = 0
    for row in sessions:
        try:
            day = datetime.strptime(str(row.get("date") or ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if cutoff <= day <= today:
            count += 1
    return count


def render_personal_v51(saved: bool = False, error: str | None = None) -> str:
    page = _previous_personal(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")

    # Success-state database plumbing is not user-facing content. Keep only
    # actual save/error/warning messages.
    ready = soup.select_one(".flash.ready")
    if ready:
        ready.decompose()

    # A direction delta based on a single paired test is less useful on the
    # daily dashboard than recent training cadence.
    stats = soup.select("section.stats > article.stat")
    if len(stats) >= 2:
        stat = stats[1]
        label = stat.find("span")
        strong = stat.find("strong")
        note = stat.find("em")
        if label:
            label.string = "Тренировок за 30 дней"
        if strong:
            strong.clear()
            strong.append(str(_sessions_last_30_days()))
        if note:
            note.string = "текущий тренировочный ритм"

    # Current work should dominate the page. Benchmarks are useful, but they
    # change rarely, so move the lap chart below the live training context.
    progress = soup.select_one("section.progress-grid")
    if progress:
        chart = progress.select_one("article.chart-wrap")
        side = progress.select_one("aside.side-stack")
        side_cards = side.find_all("article", recursive=False) if side else []
        if chart and side_cards:
            chart_head = chart.select_one(".hub-section-head h2")
            if chart_head:
                chart_head.string = "Тесты · полный круг"
            current = soup.new_tag("section")
            current["class"] = ["current-grid"]
            for card in side_cards:
                current.append(card.extract())
            benchmark = soup.new_tag("section")
            benchmark["class"] = ["benchmark-row"]
            benchmark.append(chart.extract())
            progress.insert_before(current)
            progress.insert_before(benchmark)
            progress.decompose()

    # Section navigation already lives directly under the hero. The old
    # "Next worlds" cards became duplicate navigation once those worlds were
    # implemented.
    bottom = soup.select_one("section.bottom-grid")
    if bottom:
        for article in bottom.find_all("article", recursive=False):
            h2 = article.find("h2")
            if h2 and h2.get_text(" ", strip=True) == "Следующие миры":
                article.decompose()
                break
        classes = list(bottom.get("class") or [])
        if "single" not in classes:
            classes.append("single")
        bottom["class"] = classes

    page = str(soup).replace("v0.50.2", "v0.51")
    page = _append_css(
        page,
        """
/* v0.51: current training first, slow-changing benchmarks second */
.current-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:14px;margin-top:14px}
.current-grid>.hub-card{min-height:0}
.benchmark-row{margin-top:14px}
.benchmark-row .chart-wrap{min-height:0;padding:15px 17px}
.benchmark-row .chart-wrap svg{width:100%;height:185px;display:block}
.benchmark-row .chart-foot{margin-top:4px}
.bottom-grid.single{grid-template-columns:1fr}
@media(max-width:900px){.current-grid{grid-template-columns:1fr}}
@media(max-width:760px){.benchmark-row .chart-wrap svg{height:165px}}
""",
    )
    return page


def render_closet_v51(saved: str | None = None, error: str | None = None) -> str:
    page = _previous_closet(saved=saved, error=error)
    soup = BeautifulSoup(page, "html.parser")
    ready = soup.select_one(".closet-flash.ready")
    if ready:
        ready.decompose()
    return str(soup).replace("v0.50.2", "v0.51")


def render_environment_v51() -> str:
    return _previous_environment().replace("v0.50.2", "v0.51")


core.render_page = render_home_v51
home_v44.render_big_hockey_v44 = render_big_v51
personal_base.render_personal_page = render_personal_v51
closet_v48.render_closet = render_closet_v51
environment_base.render_environment = render_environment_v51
