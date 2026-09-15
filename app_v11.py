from __future__ import annotations

from datetime import datetime, timedelta
import re

import requests
from bs4 import BeautifulSoup

import app_v10 as prev
import app_v05 as core


# --- KHL: only league games + resilient finished-state parsing ----------------
def fetch_khl_v11(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {
        "User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    response = requests.get(f"{api_base}/teams_v2.json", params=params, headers=headers, timeout=25)
    response.raise_for_status()
    raw_teams = core.unwrap_list(response.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    wanted = next((x for x in teams if core.team_name(x).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((x for x in teams if wanted_name.casefold() in core.team_name(x).casefold()), None)
    if wanted is None or wanted.get("id") is None:
        raise ValueError(f"команда {wanted_name} не найдена в KHL API")

    now = datetime.now(core.MOSCOW)
    common_query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(days=90)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": str(wanted["id"]),
        "order_direction": "asc",
    }

    games_by_id: dict[str, core.Game] = {}
    seen_raw_ids: set[str] = set()

    for page in range(1, 15):
        query = {**common_query, "page": page}
        response = requests.get(f"{api_base}/events_v2.json", params=query, headers=headers, timeout=25)
        response.raise_for_status()
        raw_events = core.unwrap_list(response.json(), ("data", "events", "items"))
        if not raw_events:
            break
        events = [x.get("event", x) if isinstance(x, dict) else x for x in raw_events]
        new_on_page = 0

        for event in events:
            if not isinstance(event, dict) or event.get("type_id") not in (None, 24):
                continue
            # Internal KHL API marks friendlies / preseason tournament games this way.
            # The hub is about league play, so do not mix them with KHL results.
            if event.get("not_regular") is True:
                continue

            event_id = event.get("id") or event.get("khl_id")
            raw_time = event.get("start_at") or event.get("event_start_at")
            if event_id is None or raw_time is None:
                continue
            event_key = str(event_id)
            if event_key in seen_raw_ids:
                continue
            seen_raw_ids.add(event_key)
            new_on_page += 1

            if isinstance(raw_time, str) and raw_time.isdigit():
                raw_time = int(raw_time)
            if isinstance(raw_time, (int, float)):
                timestamp = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
                start_at = datetime.fromtimestamp(timestamp, core.MOSCOW)
            else:
                start_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                start_at = start_at.replace(tzinfo=core.MOSCOW) if start_at.tzinfo is None else start_at.astimezone(core.MOSCOW)

            home_score, away_score = core.parse_score(event.get("score"))
            state = str(event.get("game_state_key") or "").casefold()
            if state == "finished":
                status = "finished"
            elif state == "in_progress":
                status = "live"
            else:
                # Defensive fallback: some list responses have stale/missing state,
                # while the final score is already present. Do not treat the API's
                # scheduled placeholder 0:0 as a played game.
                has_real_score = (
                    home_score is not None
                    and away_score is not None
                    and (home_score != 0 or away_score != 0)
                )
                status = "finished" if start_at < now - timedelta(hours=4) and has_real_score else "scheduled"

            if status == "scheduled":
                home_score = None
                away_score = None

            scores = event.get("scores") or {}
            decision = (
                "SO" if isinstance(scores, dict) and scores.get("bullitt")
                else "OT" if isinstance(scores, dict) and scores.get("overtime")
                else None
            )
            khl_id = event.get("khl_id")
            source_url = f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None

            games_by_id[event_key] = core.Game(
                "khl_api",
                event_key,
                league,
                core.team_name(event.get("team_a") or {}),
                core.team_name(event.get("team_b") or {}),
                start_at,
                status,
                home_score,
                away_score,
                decision,
                core.compact(event.get("location") or "") or None,
                source_url,
            )

        if new_on_page == 0:
            break

    games = sorted(games_by_id.values(), key=lambda game: game.start_at)
    if not games:
        raise ValueError(f"KHL API не вернул матчи {wanted_name}")
    return games


# --- SPbHL: score is not reliably the last table cell -------------------------
def fetch_spbhl_v11(url: str) -> list[core.Game]:
    response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    score_cell_re = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*([А-ЯA-Z]{0,3})\s*$")
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
        score_match = None
        for cell in cells:
            candidate = core.compact(cell.get_text(" ", strip=True))
            match = score_cell_re.match(candidate)
            if match:
                score_match = match
                break

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
    return games


core.fetch_khl = fetch_khl_v11
core.fetch_spbhl = fetch_spbhl_v11
core.app.version = "0.11.0"

# Keep the v0.10 UI, only bump its visible version label.
_original_render = core.render_page

def render_page_v11() -> str:
    return _original_render().replace("v0.10", "v0.11", 1)

core.render_page = render_page_v11
app = core.app
