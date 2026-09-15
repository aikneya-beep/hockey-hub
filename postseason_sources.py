from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup


SEASON = "2026/2027"
PLAYOFF_PAGES = {
    "ska_vmf": "https://vmf.ska.ru/championship/playoff/",
    "ska_1946": "https://1946.ska.ru/championship/playoff/",
    "academy": "https://junior.ska.ru/championship/playoff/",
}

_CACHE: dict[str, tuple[float, dict]] = {}


def probe_playoff_page(team_key: str, team_name: str) -> dict:
    """Check whether the SKA-family site has published this season's playoff page.

    The team sites retain old playoff brackets for years, so seeing the word
    "Плей-офф" is not enough. We only trust the page when the current season is
    present and the tracked team appears in the bracket content.
    """
    url = PLAYOFF_PAGES.get(team_key)
    if not url:
        return {"active": False, "url": None, "reason": "no_probe"}

    cached = _CACHE.get(team_key)
    if cached and time.time() - cached[0] < 900:
        return cached[1]

    try:
        response = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 HockeyHub", "Accept-Language": "ru-RU,ru;q=0.9"},
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.stripped_strings)
        active = SEASON in text and team_name.casefold() in text.casefold()
        result = {
            "active": active,
            "url": url,
            "reason": "current_season_team_in_bracket" if active else "current_bracket_not_published",
        }
    except Exception as exc:
        result = {
            "active": False,
            "url": url,
            "reason": f"{type(exc).__name__}: {exc}"[:180],
        }

    _CACHE[team_key] = (time.time(), result)
    return result
