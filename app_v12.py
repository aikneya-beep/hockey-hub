from __future__ import annotations

from datetime import datetime
import re

import requests
from bs4 import BeautifulSoup

import app_v11 as prev
import app_v10 as ui
import app_v06 as khl_v06
import app_v05 as core


KHL_2026_REGULAR_START = datetime(2026, 9, 5, 0, 0, tzinfo=core.MOSCOW)


def fetch_khl_v12(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    # Use the stable paginated parser from v0.6. The `not_regular` field used in
    # v0.11 was not sufficiently documented for us to treat it as a preseason
    # flag. For the current KHL season we instead use the official regular-season
    # start date (2026-09-05), which cleanly removes August preseason games.
    games = khl_v06.fetch_khl_paginated(api_base, league, wanted_name)
    if league == "КХЛ" and wanted_name == "СКА":
        games = [g for g in games if g.start_at >= KHL_2026_REGULAR_START]
    if not games:
        raise ValueError(f"KHL API не вернул матчи {wanted_name} после фильтра сезона")
    recent = [g for g in games if g.status == "finished"][-5:]
    if recent:
        print(
            "[verify] SKA results: " + "; ".join(
                f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}"
                for g in recent
            ),
            flush=True,
        )
    return games


def fetch_spbhl_v12(url: str) -> list[core.Game]:
    response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    score_re = re.compile(r"(\d+)\s*:\s*(\d+)\s*([А-ЯA-Z]{0,3})")
    games: list[core.Game] = []

    for row in soup.find_all("tr"):
        row_text = core.compact(row.get_text(" ", strip=True))
        if "Эскулап" not in row_text:
            continue

        date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", row_text)
        time_match = re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", row_text)
        if not date_match or not time_match:
            continue

        match_link = next(
            (a for a in row.find_all("a", href=True) if "Эскулап" in core.compact(a.get_text(" ", strip=True))),
            None,
        )
        teams_text = core.compact(match_link.get_text(" ", strip=True)) if match_link else ""
        parts = re.split(r"\s+-\s+", teams_text, maxsplit=1)
        if len(parts) != 2:
            continue
        home, away = parts

        cells = row.find_all("td")
        # СПбХЛ table columns are: tournament, round, no, date, time, arena,
        # teams, result. Therefore only the final cell is the result; scanning all
        # cells mistakes e.g. 21:30 for a hockey score.
        result_text = core.compact(cells[-1].get_text(" ", strip=True)) if cells else ""
        score_match = score_re.search(result_text)
        home_score = int(score_match.group(1)) if score_match else None
        away_score = int(score_match.group(2)) if score_match else None
        suffix = score_match.group(3).upper() if score_match else ""
        decision = "SO" if suffix in {"ПБ", "Б", "SO"} else "OT" if suffix in {"ОТ", "OT"} else None

        number = core.compact(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else ""
        arena = core.compact(cells[5].get_text(" ", strip=True)) if len(cells) >= 6 else None
        date_text = date_match.group(0)
        time_text = time_match.group(0)
        start_at = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=core.MOSCOW)
        game_url = requests.compat.urljoin(url, match_link["href"]) if match_link else url
        game_id = number or core.make_id(date_text, time_text, home, away)

        games.append(
            core.Game(
                "spbhl",
                f"spbhl-{game_id}",
                "СПбХЛ",
                home,
                away,
                start_at,
                "finished" if score_match else "scheduled",
                home_score,
                away_score,
                decision,
                arena or None,
                game_url,
            )
        )

    if not games:
        raise ValueError("не удалось распознать матчи Эскулапа")

    recent = [g for g in games if g.status == "finished"][-5:]
    if recent:
        print(
            "[verify] Eskulap results: " + "; ".join(
                f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}"
                for g in recent
            ),
            flush=True,
        )
    return games


core.fetch_khl = fetch_khl_v12
core.fetch_spbhl = fetch_spbhl_v12
core.app.version = "0.12.0"


def render_page_v12() -> str:
    # Call the v0.10 UI explicitly instead of relying on a chain of mutable
    # module-level render functions. This guarantees the visible version bump.
    return ui.render_page_v10().replace("v0.10", "v0.12", 1)


core.render_page = render_page_v12
app = core.app
