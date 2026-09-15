from datetime import datetime
import re

import app_v16 as prev
import app_v13 as spb
import app_v10 as ui
import app_v05 as core

REGULAR_START = datetime(2026, 9, 5, tzinfo=core.MOSCOW)
SKA_GAMES_URL = "https://www.ska.ru/championship/games/"


def fetch_ska_primary(api_base, league, wanted_name):
    if wanted_name != "СКА":
        return prev.fetch_khl(api_base, league, wanted_name)
    try:
        games = core.fetch_ska_site(SKA_GAMES_URL, "СКА", "КХЛ")
        games = [g for g in games if g.start_at >= REGULAR_START]
        if not games:
            raise ValueError("официальный сайт СКА не вернул матчи текущей регулярки")
        finished = [g for g in games if g.status == "finished"]
        print("[verify] SKA site: " + "; ".join(
            f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}"
            for g in finished[-10:]
        ), flush=True)
        return games
    except Exception as exc:
        print(f"[verify] SKA site failed: {type(exc).__name__}: {exc}; fallback to KHL API", flush=True)
        return prev.fetch_khl(api_base, league, wanted_name)


core.fetch_khl = fetch_ska_primary
core.fetch_spbhl = spb.fetch_spbhl_v13
core.app.version = "0.17.0"


def render_page():
    page = ui.render_page_v10()
    return re.sub(r"ХОККЕЙНЫЙ АГРЕГАТОР · v\d+\.\d+", "ХОККЕЙНЫЙ АГРЕГАТОР · v0.17", page, count=1)


core.render_page = render_page
app = core.app
