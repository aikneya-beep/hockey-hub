from datetime import datetime
import re

import app_v16 as api
import app_v13 as spb
import app_v10 as ui
import app_v05 as core


SKA_RESULTS = [
    ("2026-09-05 17:00", "СКА", "Лада", 4, 3, "OT", "https://www.khl.ru/news/2026/09/05/565166.html"),
    ("2026-09-07 19:30", "СКА", "Динамо М", 5, 3, None, "https://www.khl.ru/news/2026/09/07/565427.html"),
    ("2026-09-09 19:30", "СКА", "Лада", 2, 1, "OT", "https://www.khl.ru/news/2026/09/09/565539.html"),
    ("2026-09-10 19:30", "Спартак", "СКА", 3, 1, None, "https://www.khl.ru/news/2026/09/10/565586.html"),
    ("2026-09-12 17:00", "ХК Сочи", "СКА", 0, 1, None, "https://www.khl.ru/news/2026/09/12/565661.html"),
]


def _seeded_ska_results():
    games = []
    for raw_dt, home, away, hs, aw, decision, url in SKA_RESULTS:
        dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M").replace(tzinfo=core.MOSCOW)
        games.append(core.Game(
            "khl_verified",
            core.make_id(raw_dt, home, away),
            "КХЛ",
            home,
            away,
            dt,
            "finished",
            hs,
            aw,
            decision,
            None,
            url,
        ))
    return games


def fetch_khl_v18(api_base, league, wanted_name):
    games = api.fetch_khl(api_base, league, wanted_name)
    if wanted_name != "СКА":
        return games

    # events_v2 currently gives us the SKA schedule reliably, but not recent
    # completed matches. Merge a small verified seed for already played games.
    # A live API game for the same matchup/date wins only if it is finished.
    seeded = _seeded_ska_results()
    existing_keys = {
        (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold()): g
        for g in games
    }
    for seed in seeded:
        key = (seed.start_at.date(), seed.home_team.casefold(), seed.away_team.casefold())
        current = existing_keys.get(key)
        if current is None or current.status != "finished":
            games.append(seed)
    games.sort(key=lambda g: g.start_at)
    return games


core.fetch_khl = fetch_khl_v18
core.fetch_spbhl = spb.fetch_spbhl_v13
core.app.version = "0.18.0"


def render_page():
    page = ui.render_page_v10()
    return re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.18", page, count=1)


core.render_page = render_page
app = core.app
