from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import os
from pathlib import Path
from threading import Lock

try:
    import psycopg
except Exception:  # pragma: no cover - app can still run without DB configured
    psycopg = None


@dataclass
class MirrorStatus:
    enabled: bool
    connected: bool = False
    schema_ready: bool = False
    last_sync_at: str | None = None
    games_written: int = 0
    teams_written: int = 0
    error: str | None = None


class HockeyStorage:
    """Best-effort PostgreSQL mirror.

    Production UI remains backed by the existing in-process cache until mirror
    data has been verified. DATABASE_URL is the only switch needed to enable it.
    """

    def __init__(self, database_url: str | None = None):
        self.database_url = (database_url or os.getenv("DATABASE_URL") or "").strip()
        self._lock = Lock()
        self._status = MirrorStatus(enabled=bool(self.database_url))

    @classmethod
    def from_env(cls) -> "HockeyStorage":
        return cls()

    def status(self) -> dict:
        with self._lock:
            return asdict(self._status)

    def _set_error(self, exc: Exception) -> None:
        with self._lock:
            self._status.connected = False
            self._status.error = f"{type(exc).__name__}: {exc}"

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        return psycopg.connect(self.database_url, connect_timeout=8)

    def ensure_schema(self, conn) -> None:
        if self._status.schema_ready:
            return
        sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        # schema.sql intentionally contains only plain DDL, so splitting on
        # semicolons keeps this compatible with psycopg's extended protocol.
        for statement in (chunk.strip() for chunk in sql.split(";")):
            if statement:
                conn.execute(statement)
        self._status.schema_ready = True

    @staticmethod
    def _season_name() -> str:
        return "2026/2027"

    @staticmethod
    def _stage_name(league: str) -> str:
        return "Регулярный сезон"

    def mirror(self, teams, games) -> dict:
        if not self.database_url:
            return self.status()

        try:
            with self._connect() as conn:
                self.ensure_schema(conn)
                with self._lock:
                    self._status.connected = True
                    self._status.error = None

                leagues = sorted({t.league for t in teams} | {g.league for g in games})
                for league in leagues:
                    conn.execute(
                        "insert into leagues(code,name) values(%s,%s) "
                        "on conflict(code) do update set name=excluded.name",
                        (league, league),
                    )

                team_count = 0
                for team in teams:
                    conn.execute(
                        "insert into teams(key,name,league_code,source) values(%s,%s,%s,%s) "
                        "on conflict(key) do update set name=excluded.name, league_code=excluded.league_code, source=excluded.source",
                        (team.key, team.name, team.league, team.source),
                    )
                    team_count += 1

                season_ids: dict[str, int] = {}
                stage_ids: dict[str, int] = {}
                for league in leagues:
                    season_id = conn.execute(
                        "insert into seasons(league_code,name) values(%s,%s) "
                        "on conflict(league_code,name) do update set name=excluded.name returning id",
                        (league, self._season_name()),
                    ).fetchone()[0]
                    season_ids[league] = season_id
                    stage_id = conn.execute(
                        "insert into stages(season_id,name,kind) values(%s,%s,'regular') "
                        "on conflict(season_id,name) do update set kind=excluded.kind returning id",
                        (season_id, self._stage_name(league)),
                    ).fetchone()[0]
                    stage_ids[league] = stage_id

                game_count = 0
                for game in games:
                    arena_id = None
                    arena_text = (game.arena or "").strip() or None
                    if arena_text:
                        # Empty string instead of NULL makes the unique key stable.
                        arena_id = conn.execute(
                            "insert into arenas(name,city,source) values(%s,'',%s) "
                            "on conflict(name,city) do update set source=coalesce(excluded.source,arenas.source) returning id",
                            (arena_text, game.source),
                        ).fetchone()[0]

                    conn.execute(
                        "insert into games(source,source_game_id,league_code,season_id,stage_id,home_team,away_team,start_at,status,home_score,away_score,decision,arena_id,arena_text,source_url,updated_at) "
                        "values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
                        "on conflict(source,source_game_id) do update set "
                        "league_code=excluded.league_code, season_id=excluded.season_id, stage_id=excluded.stage_id, "
                        "home_team=excluded.home_team, away_team=excluded.away_team, start_at=excluded.start_at, status=excluded.status, "
                        "home_score=excluded.home_score, away_score=excluded.away_score, decision=excluded.decision, "
                        "arena_id=excluded.arena_id, arena_text=excluded.arena_text, source_url=excluded.source_url, updated_at=now()",
                        (
                            game.source,
                            str(game.source_game_id),
                            game.league,
                            season_ids.get(game.league),
                            stage_ids.get(game.league),
                            game.home_team,
                            game.away_team,
                            game.start_at,
                            game.status,
                            game.home_score,
                            game.away_score,
                            game.decision,
                            arena_id,
                            arena_text,
                            game.source_url,
                        ),
                    )
                    game_count += 1

                conn.commit()
                with self._lock:
                    self._status.connected = True
                    self._status.schema_ready = True
                    self._status.last_sync_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                    self._status.games_written = game_count
                    self._status.teams_written = team_count
                    self._status.error = None
                print(f"[storage] mirrored teams={team_count} games={game_count}", flush=True)
        except Exception as exc:
            self._set_error(exc)
            print(f"[storage] mirror failed: {type(exc).__name__}: {exc}", flush=True)
        return self.status()
