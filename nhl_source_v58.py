from __future__ import annotations

from datetime import datetime, timezone
import json
import threading
import time
from typing import Any

import requests


STATS_BASE = "https://api.nhle.com/stats/rest/en"
WEB_BASE = "https://api-web.nhle.com/v1"

_session = requests.Session()
_session.headers.update({
    "User-Agent": "HockeyHub/0.58 (+personal hockey dashboard)",
    "Accept": "application/json",
})

_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: int, loader):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = loader()
    with _lock:
        _cache[key] = (now, value)
    return value


def _get(url: str, *, params: dict | None = None, timeout: int = 12) -> dict:
    response = _session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def season_id_for_date(now: datetime) -> int:
    year = now.year
    start = year if now.month >= 7 else year - 1
    return int(f"{start}{start + 1}")


def previous_season_id(season_id: int) -> int:
    start = int(str(season_id)[:4]) - 1
    return int(f"{start}{start + 1}")


def _stats(report: str, season_id: int, limit: int = 100) -> list[dict]:
    params = {
        "isAggregate": "false",
        "isGame": "false",
        "sort": json.dumps([{"property": "points", "direction": "DESC"}], separators=(",", ":")),
        "start": 0,
        "limit": limit,
        "cayenneExp": f'seasonId={season_id} and nationalityCode="RUS"',
    }
    payload = _get(f"{STATS_BASE}/{report}", params=params)
    return payload.get("data") or []


def russian_stats(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    current = season_id_for_date(now)

    def load():
        errors: list[str] = []
        skaters: list[dict] = []
        goalies: list[dict] = []
        used = current

        try:
            skaters = _stats("skater/summary", current)
        except Exception as exc:
            errors.append(f"current skaters: {type(exc).__name__}: {exc}")

        try:
            goalies = _stats("goalie/summary", current)
        except Exception as exc:
            errors.append(f"current goalies: {type(exc).__name__}: {exc}")

        if not skaters and not goalies:
            used = previous_season_id(current)
            try:
                skaters = _stats("skater/summary", used)
            except Exception as exc:
                errors.append(f"previous skaters: {type(exc).__name__}: {exc}")
            try:
                goalies = _stats("goalie/summary", used)
            except Exception as exc:
                errors.append(f"previous goalies: {type(exc).__name__}: {exc}")

        return {
            "season_id": used,
            "current_season_id": current,
            "is_current": used == current,
            "skaters": skaters,
            "goalies": goalies,
            "errors": errors,
        }

    return _cached(f"rus-stats-{current}", 60 * 60 * 4, load)


def _team_abbr(value: str | None) -> str:
    if not value:
        return ""
    # Stats sometimes returns comma-separated teams after a trade.
    return value.split(",")[-1].strip().upper()


def player_rows(stats_payload: dict) -> list[dict]:
    rows: list[dict] = []

    for row in stats_payload.get("skaters") or []:
        rows.append({
            "id": row.get("playerId"),
            "name": row.get("skaterFullName") or row.get("playerName") or "—",
            "team": _team_abbr(row.get("teamAbbrevs") or row.get("teamAbbrev")),
            "position": row.get("positionCode") or "",
            "kind": "skater",
            "gp": row.get("gamesPlayed"),
            "goals": row.get("goals"),
            "assists": row.get("assists"),
            "points": row.get("points"),
            "plus_minus": row.get("plusMinus"),
        })

    for row in stats_payload.get("goalies") or []:
        rows.append({
            "id": row.get("playerId"),
            "name": row.get("goalieFullName") or row.get("playerName") or "—",
            "team": _team_abbr(row.get("teamAbbrevs") or row.get("teamAbbrev")),
            "position": "G",
            "kind": "goalie",
            "gp": row.get("gamesPlayed"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "ot_losses": row.get("otLosses"),
            "save_pct": row.get("savePct"),
            "gaa": row.get("goalsAgainstAverage"),
            "shutouts": row.get("shutouts"),
        })

    rows.sort(
        key=lambda x: (
            0 if x["kind"] == "skater" else 1,
            -(x.get("points") or 0) if x["kind"] == "skater" else -(x.get("wins") or 0),
            x.get("name") or "",
        )
    )
    return rows


def club_schedule(team: str, season_id: int) -> list[dict]:
    team = (team or "").strip().upper()
    if not team:
        return []

    def load():
        try:
            payload = _get(f"{WEB_BASE}/club-schedule-season/{team}/{season_id}")
            return payload.get("games") or []
        except Exception as exc:
            print(f"[nhl] schedule {team}: {type(exc).__name__}: {exc}", flush=True)
            return []

    return _cached(f"schedule-{team}-{season_id}", 60 * 30, load)


def _game_start(game: dict) -> datetime | None:
    raw = game.get("startTimeUTC")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def next_game(team: str, season_id: int, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    games = club_schedule(team, season_id)
    candidates = []
    for game in games:
        start = _game_start(game)
        state = game.get("gameState") or ""
        if start and start >= now and state not in {"FINAL", "OFF"}:
            candidates.append((start, game))
    return min(candidates, key=lambda x: x[0])[1] if candidates else None


def recent_game(team: str, season_id: int, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    games = club_schedule(team, season_id)
    candidates = []
    for game in games:
        start = _game_start(game)
        state = game.get("gameState") or ""
        if start and start <= now and state in {"FINAL", "OFF"}:
            candidates.append((start, game))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def team_context(players: list[dict], current_season_id: int, now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now(timezone.utc)
    teams = sorted({p.get("team") for p in players if p.get("team")})
    contexts: dict[str, dict] = {}

    # Keep first render bounded: schedule requests are done only once per unique team.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def load(team: str):
        return team, next_game(team, current_season_id, now), recent_game(team, current_season_id, now)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(load, team) for team in teams]
        for future in as_completed(futures):
            try:
                team, nxt, recent = future.result()
                contexts[team] = {"next": nxt, "recent": recent}
            except Exception as exc:
                print(f"[nhl] team context: {type(exc).__name__}: {exc}", flush=True)

    return contexts


def load_russians(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stats = russian_stats(now)
    players = player_rows(stats)
    contexts = team_context(players, stats["current_season_id"], now)
    return {
        **stats,
        "players": players,
        "teams": contexts,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }
