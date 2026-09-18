from __future__ import annotations

from datetime import date
import os

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None


def season_for_date(value: date) -> str:
    start = value.year if value.month >= 7 else value.year - 1
    return f"{start}/{str(start + 1)[-2:]}"


class MemoryStore:
    def __init__(self, database_url: str | None = None):
        self.database_url = (database_url or os.getenv("DATABASE_URL") or "").strip()
        self._schema_ready = False

    @property
    def enabled(self) -> bool:
        return bool(self.database_url and psycopg is not None)

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        return psycopg.connect(self.database_url, connect_timeout=8)

    def _ensure(self, conn) -> None:
        if self._schema_ready:
            return
        conn.execute(
            """create table if not exists personal_hockey_memories (
                id bigserial primary key,
                match_date date not null,
                season text not null,
                competition text,
                home_team text not null,
                away_team text not null,
                home_score integer check (home_score >= 0),
                away_score integer check (away_score >= 0),
                arena text,
                sector text,
                seat text,
                companions text,
                note text,
                ticket_ref text,
                photo_refs text,
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now()
            )"""
        )
        conn.execute(
            """create index if not exists personal_hockey_memories_season_date_idx
               on personal_hockey_memories(season, match_date desc, id desc)"""
        )
        self._schema_ready = True

    def load(self, season: str | None = None) -> dict:
        if not self.enabled:
            return {"matches": [], "seasons": [], "error": "PostgreSQL is not connected"}
        try:
            with self._connect() as conn:
                self._ensure(conn)
                seasons = [
                    row[0]
                    for row in conn.execute(
                        """select distinct season
                           from personal_hockey_memories
                           order by season desc"""
                    ).fetchall()
                ]
                if season:
                    rows = conn.execute(
                        """select id,match_date,season,competition,home_team,away_team,
                                  home_score,away_score,arena,sector,seat,companions,note,
                                  ticket_ref,photo_refs,created_at
                           from personal_hockey_memories
                           where season=%s
                           order by match_date desc,id desc""",
                        (season,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """select id,match_date,season,competition,home_team,away_team,
                                  home_score,away_score,arena,sector,seat,companions,note,
                                  ticket_ref,photo_refs,created_at
                           from personal_hockey_memories
                           order by match_date desc,id desc"""
                    ).fetchall()
                conn.commit()
            return {
                "matches": [
                    {
                        "id": r[0],
                        "match_date": r[1].isoformat(),
                        "season": r[2],
                        "competition": r[3] or "",
                        "home_team": r[4],
                        "away_team": r[5],
                        "home_score": r[6],
                        "away_score": r[7],
                        "arena": r[8] or "",
                        "sector": r[9] or "",
                        "seat": r[10] or "",
                        "companions": r[11] or "",
                        "note": r[12] or "",
                        "ticket_ref": r[13] or "",
                        "photo_refs": r[14] or "",
                        "created_at": r[15].isoformat() if r[15] else None,
                    }
                    for r in rows
                ],
                "seasons": seasons,
                "error": None,
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"[memory-db] load failed: {error}", flush=True)
            return {"matches": [], "seasons": [], "error": error}

    def add_match(
        self,
        *,
        match_date: date,
        home_team: str,
        away_team: str,
        competition: str = "",
        home_score: int | None = None,
        away_score: int | None = None,
        arena: str = "",
        sector: str = "",
        seat: str = "",
        companions: str = "",
        note: str = "",
        season: str = "",
        ticket_ref: str = "",
        photo_refs: str = "",
    ) -> int:
        home_team = home_team.strip()
        away_team = away_team.strip()
        if not home_team or not away_team:
            raise ValueError("Обе команды обязательны")
        if (home_score is None) != (away_score is None):
            raise ValueError("Счёт нужно указать целиком")
        resolved_season = season.strip() or season_for_date(match_date)
        with self._connect() as conn:
            self._ensure(conn)
            row = conn.execute(
                """insert into personal_hockey_memories(
                       match_date,season,competition,home_team,away_team,
                       home_score,away_score,arena,sector,seat,companions,note,
                       ticket_ref,photo_refs
                   ) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   returning id""",
                (
                    match_date,
                    resolved_season,
                    competition.strip() or None,
                    home_team,
                    away_team,
                    home_score,
                    away_score,
                    arena.strip() or None,
                    sector.strip() or None,
                    seat.strip() or None,
                    companions.strip() or None,
                    note.strip() or None,
                    ticket_ref.strip() or None,
                    photo_refs.strip() or None,
                ),
            ).fetchone()
            conn.commit()
        return int(row[0])

    def delete_match(self, item_id: int) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute("delete from personal_hockey_memories where id=%s", (item_id,))
            conn.commit()
