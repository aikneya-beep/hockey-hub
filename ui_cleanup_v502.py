from __future__ import annotations

import app_v05 as core
import personal_hockey_v42 as personal_base
import closet_v48


_previous_home = core.render_page
_previous_personal = personal_base.render_personal_page
_previous_closet = closet_v48.render_closet


def _rename_everywhere(page: str) -> str:
    page = page.replace("ТЁМА И КОМАНДЫ · ЭСКУЛАП", "МОЯ ХОККЕЙНАЯ СРЕДА · ЭСКУЛАП")
    page = page.replace("Тёма и команды", "Моя хоккейная среда")
    page = page.replace("тёма и команды", "моя хоккейная среда")
    return page


def render_home_v502() -> str:
    page = _previous_home()
    page = _rename_everywhere(page)
    page = page.replace("Hockey Hub · v0.45 · персональный briefing", "Hockey Hub · v0.50.2 · персональный briefing", 1)
    page = page.replace("HOCKEY HUB · V0.45 · ПЕРСОНАЛЬНЫЙ BRIEFING", "HOCKEY HUB · V0.50.2 · ПЕРСОНАЛЬНЫЙ BRIEFING", 1)
    page = page.replace(
        "Личные тренировки и прогресс перенесём сюда после включения авторизации.",
        "Личные тренировки, прогресс, среда, шкаф и память доступны после входа.",
    )
    return page


def render_personal_v502(saved: bool = False, error: str | None = None) -> str:
    page = _previous_personal(saved=saved, error=error)
    page = _rename_everywhere(page)
    page = page.replace("Личный хоккей · v0.50", "Личный хоккей · v0.50.2", 1)
    page = page.replace("Личный хоккей · v0.48.1", "Личный хоккей · v0.50.2", 1)
    return page


def render_closet_v502(saved: str | None = None, error: str | None = None) -> str:
    page = _previous_closet(saved=saved, error=error)
    page = _rename_everywhere(page)
    page = page.replace("Мой хоккей · v0.50", "Мой хоккей · v0.50.2", 1)
    page = page.replace("Мой хоккей · v0.48.1", "Мой хоккей · v0.50.2", 1)
    return page


core.render_page = render_home_v502
personal_base.render_personal_page = render_personal_v502
closet_v48.render_closet = render_closet_v502
