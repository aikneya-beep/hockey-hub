from __future__ import annotations

from datetime import datetime
import time

import requests

import app_v23 as prev
import app_v20 as seeded
import app_v19 as khlbase
import app_v05 as core

core.app.version = "0.24.0"

SOFA_BASE = "https://api.sofascore.com/api/v1"
SOFA_TOURNAMENT_ID = 268
SOFA_SEASON_YEAR = "26/27"
SOFA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
}

_SOFA_CACHE: dict[str, tuple[float, object]] = {}


def _cached_json(key: str, url: str, ttl: int = 600) -> dict:
    cached = _SOFA_CACHE.get(key)
    if cached and time.time() - cached[0] < ttl:
        return cached[1]  # type: ignore[return-value]
    resp = requests.get(url, headers=SOFA_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _SOFA_CACHE[key] = (time.time(), data)
    return data


def _sofa_season_id() -> int:
    data = _cached_json(
        "seasons",
        f"{SOFA_BASE}/unique-tournament/{SOFA_TOURNAMENT_ID}/seasons",
        3600,
    )
    seasons = data.get("seasons") or []
    season = next(
        (s for s in seasons if str(s.get("year") or "") == SOFA_SEASON_YEAR),
        None,
    )
    if season is None:
        season = next(
            (s for s in seasons if SOFA_SEASON_YEAR in str(s.get("name") or "")),
            None,
        )
    if not season or season.get("id") is None:
        raise ValueError("Sofascore: не найден сезон КХЛ 26/27")
    return int(season["id"])


def _sofa_standings_payload() -> tuple[int, dict, dict]:
    season_id = _sofa_season_id()
    payload = _cached_json(
        f"standings-{season_id}",
        f"{SOFA_BASE}/unique-tournament/{SOFA_TOURNAMENT_ID}/season/{season_id}/standings/total",
        300,
    )
    standings = payload.get("standings") or []
    selected = None
    ska_row = None
    for block in standings:
        rows = block.get("rows") or []
        for row in rows:
            team = row.get("team") or {}
            code = str(team.get("nameCode") or team.get("nameCodeInternational") or "").upper()
            name = str(team.get("name") or "").casefold()
            slug = str(team.get("slug") or "").casefold()
            if code == "SKA" or name in {"ska", "ска"} or slug in {"ska", "ska-st-petersburg", "ska-saint-petersburg"}:
                selected = block
                ska_row = row
                break
        if selected:
            break
    if not selected or not ska_row:
        raise ValueError("Sofascore: СКА не найден в таблице КХЛ")
    return season_id, selected, ska_row


def _ru_team(name: str) -> str:
    raw = core.compact(name)
    aliases = {
        "SKA St. Petersburg": "СКА",
        "SKA Saint Petersburg": "СКА",
        "SKA": "СКА",
        "Lada Togliatti": "Лада",
        "Dynamo Moscow": "Динамо М",
        "Spartak Moscow": "Спартак",
        "HC Sochi": "ХК Сочи",
        "Sochi": "ХК Сочи",
        "Shanghai Dragons": "Драконы",
        "Traktor Chelyabinsk": "Трактор",
        "Barys Astana": "Барыс",
        "CSKA Moscow": "ЦСКА",
        "Admiral Vladivostok": "Адмирал",
        "Severstal Cherepovets": "Северсталь",
        "Lokomotiv Yaroslavl": "Локомотив",
        "Torpedo Nizhny Novgorod": "Торпедо",
        "Dinamo Minsk": "Динамо Мн",
        "Dynamo Minsk": "Динамо Мн",
    }
    return aliases.get(raw, raw)


def _sofa_recent_ska() -> list[core.Game]:
    season_id, _block, ska_row = _sofa_standings_payload()
    team_id = int((ska_row.get("team") or {})["id"])
    games: list[core.Game] = []

    for page in range(0, 5):
        payload = _cached_json(
            f"ska-last-{team_id}-{page}",
            f"{SOFA_BASE}/team/{team_id}/events/last/{page}",
            180,
        )
        events = payload.get("events") or []
        for event in events:
            if int((event.get("season") or {}).get("id") or 0) != season_id:
                continue
            unique_id = int((((event.get("tournament") or {}).get("uniqueTournament") or {}).get("id")) or 0)
            if unique_id and unique_id != SOFA_TOURNAMENT_ID:
                continue
            start_ts = event.get("startTimestamp")
            if not start_ts:
                continue
            start_at = datetime.fromtimestamp(int(start_ts), core.MOSCOW)
            if start_at < khlbase.REGULAR_START:
                continue
            status_type = str((event.get("status") or {}).get("type") or "").casefold()
            if status_type not in {"finished", "inprogress"}:
                continue
            hs_obj = event.get("homeScore") or {}
            as_obj = event.get("awayScore") or {}
            hs = hs_obj.get("current")
            aw = as_obj.get("current")
            if hs is None or aw is None:
                continue
            decision = None
            norm_h = hs_obj.get("normaltime")
            norm_a = as_obj.get("normaltime")
            if status_type == "finished" and norm_h is not None and norm_a is not None and (int(hs) != int(norm_h) or int(aw) != int(norm_a)):
                decision = "OT"
            event_id = str(event.get("id"))
            slug = str(event.get("slug") or "")
            source_url = f"https://www.sofascore.com/{slug}/{event_id}" if slug else "https://www.sofascore.com/ice-hockey/tournament/russia/khl/268"
            games.append(
                core.Game(
                    "sofascore_khl",
                    f"sofa-{event_id}",
                    "КХЛ",
                    _ru_team(str((event.get("homeTeam") or {}).get("name") or "?")),
                    _ru_team(str((event.get("awayTeam") or {}).get("name") or "?")),
                    start_at,
                    "finished" if status_type == "finished" else "live",
                    int(hs),
                    int(aw),
                    decision,
                    source_url=source_url,
                )
            )
        if not payload.get("hasNextPage"):
            break

    # Keep only SKA games and deduplicate by date/matchup.
    best: dict[tuple, core.Game] = {}
    for g in games:
        if "СКА" not in (g.home_team, g.away_team):
            continue
        key = (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold())
        best[key] = g
    result = sorted(best.values(), key=lambda g: g.start_at)
    if not result:
        raise ValueError("Sofascore: нет завершённых матчей СКА текущего сезона")
    return result


def fetch_khl_v24(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    if wanted_name != "СКА":
        return seeded.fetch_khl_v20(api_base, league, wanted_name)

    # Official KHL internal API remains best for the future schedule.
    automatic = khlbase.fetch_khl_v19(api_base, league, wanted_name)
    by_key: dict[tuple, core.Game] = {
        (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold()): g for g in automatic
    }
    sofa_ok = False
    try:
        recent = _sofa_recent_ska()
        sofa_ok = True
        for g in recent:
            key = (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold())
            current = by_key.get(key)
            if current is None or current.status != "finished":
                by_key[key] = g
    except Exception as exc:
        print(f"[ska] Sofascore results fallback failed: {type(exc).__name__}: {exc}", flush=True)
        # Last-resort verified seeds. They are only used if the automatic source is unavailable.
        for g in seeded.stable._seeded_ska_results():
            key = (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold())
            current = by_key.get(key)
            if current is None or current.status != "finished":
                by_key[key] = g

    games = sorted(by_key.values(), key=lambda g: g.start_at)
    finished = [g for g in games if g.status == "finished"]
    print(
        f"[verify] SKA v24 sofa={sofa_ok} games={len(games)} finished={len(finished)}: "
        + "; ".join(f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}" for g in finished[-8:]),
        flush=True,
    )
    return games


core.fetch_khl = fetch_khl_v24

_old_standings = khlbase._fetch_khl_standings


def sofa_khl_standings_v24() -> dict:
    try:
        _season_id, block, _ska_row = _sofa_standings_payload()
        rows_out = []
        for row in block.get("rows") or []:
            team = row.get("team") or {}
            name = _ru_team(str(team.get("name") or team.get("shortName") or "?"))
            rows_out.append([
                str(row.get("position") or ""),
                name,
                str(row.get("matches") or 0),
                str(row.get("wins") or 0),
                str(row.get("losses") or 0),
                f"{row.get('scoresFor') or 0}:{row.get('scoresAgainst') or 0}",
                str(row.get("points") or 0),
            ])
        if not any(r[1] == "СКА" for r in rows_out):
            raise ValueError("Sofascore: в выбранной таблице нет СКА")
        title = str(block.get("name") or "Западная конференция")
        if "Western" in title:
            title = "Западная конференция"
        return {
            "title": title,
            "headers": ["М", "Команда", "И", "В", "П", "Ш", "О"],
            "rows": rows_out,
            "source": "https://www.sofascore.com/ice-hockey/tournament/russia/khl/268",
            "note": "автоматические данные Sofascore",
        }
    except Exception as exc:
        print(f"[standings] Sofascore KHL failed: {type(exc).__name__}: {exc}", flush=True)
        return _old_standings()


khlbase._fetch_khl_standings = sofa_khl_standings_v24
# Throw away any table cached before this override.
khlbase.STANDINGS_CACHE.pop("ska", None)

_old_team_page = khlbase.render_team_page


def render_team_page_v24(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.23", "v0.24")


khlbase.render_team_page = render_team_page_v24


def render_page_v24() -> str:
    return prev.render_page_v23().replace("v0.23", "v0.24", 1)


core.render_page = render_page_v24
app = core.app
