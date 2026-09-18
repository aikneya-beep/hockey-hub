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
        conn.execute(
            """create table if not exists personal_hockey_memory_photos (
                id bigserial primary key,
                memory_id bigint not null references personal_hockey_memories(id) on delete cascade,
                mime_type text not null,
                image_data bytea not null,
                width integer,
                height integer,
                original_name text,
                created_at timestamptz not null default now()
            )"""
        )
        conn.execute(
            """create index if not exists personal_hockey_memory_photos_memory_idx
               on personal_hockey_memory_photos(memory_id, id)"""
        )
        self._schema_ready = True

    @staticmethod
    def _validate_match(home_team: str, away_team: str, home_score: int | None, away_score: int | None) -> tuple[str, str]:
        home = home_team.strip()
        away = away_team.strip()
        if not home or not away:
            raise ValueError("Обе команды обязательны")
        if (home_score is None) != (away_score is None):
            raise ValueError("Счёт нужно указать целиком")
        if home_score is not None and (home_score < 0 or away_score is None or away_score < 0):
            raise ValueError("Некорректный счёт")
        return home, away

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

                ids = [int(r[0]) for r in rows]
                photos_by_memory: dict[int, list[dict]] = {item_id: [] for item_id in ids}
                if ids:
                    photo_rows = conn.execute(
                        """select id,memory_id,width,height,original_name,created_at
                           from personal_hockey_memory_photos
                           where memory_id = any(%s)
                           order by memory_id,id""",
                        (ids,),
                    ).fetchall()
                    for p in photo_rows:
                        photos_by_memory.setdefault(int(p[1]), []).append(
                            {
                                "id": int(p[0]),
                                "width": p[2],
                                "height": p[3],
                                "original_name": p[4] or "",
                                "created_at": p[5].isoformat() if p[5] else None,
                            }
                        )
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
                        "photos": photos_by_memory.get(int(r[0]), []),
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
        home, away = self._validate_match(home_team, away_team, home_score, away_score)
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
                    home,
                    away,
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

    def update_match(
        self,
        item_id: int,
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
    ) -> None:
        home, away = self._validate_match(home_team, away_team, home_score, away_score)
        with self._connect() as conn:
            self._ensure(conn)
            result = conn.execute(
                """update personal_hockey_memories
                   set match_date=%s,season=%s,competition=%s,home_team=%s,away_team=%s,
                       home_score=%s,away_score=%s,arena=%s,sector=%s,seat=%s,
                       companions=%s,note=%s,updated_at=now()
                   where id=%s""",
                (
                    match_date,
                    season_for_date(match_date),
                    competition.strip() or None,
                    home,
                    away,
                    home_score,
                    away_score,
                    arena.strip() or None,
                    sector.strip() or None,
                    seat.strip() or None,
                    companions.strip() or None,
                    note.strip() or None,
                    int(item_id),
                ),
            )
            if result.rowcount == 0:
                raise ValueError("Воспоминание не найдено")
            conn.commit()

    def add_photo(
        self,
        memory_id: int,
        *,
        mime_type: str,
        image_data: bytes,
        width: int,
        height: int,
        original_name: str = "",
        max_photos: int = 20,
    ) -> int:
        with self._connect() as conn:
            self._ensure(conn)
            exists = conn.execute(
                "select 1 from personal_hockey_memories where id=%s",
                (int(memory_id),),
            ).fetchone()
            if not exists:
                raise ValueError("Воспоминание не найдено")
            count = conn.execute(
                "select count(*) from personal_hockey_memory_photos where memory_id=%s",
                (int(memory_id),),
            ).fetchone()[0]
            if int(count) >= max_photos:
                raise ValueError(f"К одному воспоминанию можно добавить не больше {max_photos} фотографий")
            row = conn.execute(
                """insert into personal_hockey_memory_photos(
                       memory_id,mime_type,image_data,width,height,original_name
                   ) values(%s,%s,%s,%s,%s,%s) returning id""",
                (int(memory_id), mime_type, image_data, int(width), int(height), original_name.strip() or None),
            ).fetchone()
            conn.commit()
        return int(row[0])

    def create_match_with_photos(
        self, *, match_date: date, home_team: str, away_team: str, competition: str = "",
        home_score: int | None = None, away_score: int | None = None, arena: str = "",
        sector: str = "", seat: str = "", companions: str = "", note: str = "",
        photos: list[dict] | None = None, max_photos: int = 20,
    ) -> int:
        home, away = self._validate_match(home_team, away_team, home_score, away_score)
        photos = photos or []
        if len(photos) > max_photos:
            raise ValueError(f"К одному воспоминанию можно добавить не больше {max_photos} фотографий")
        with self._connect() as conn:
            self._ensure(conn)
            row = conn.execute(
                """insert into personal_hockey_memories(
                       match_date,season,competition,home_team,away_team,
                       home_score,away_score,arena,sector,seat,companions,note
                   ) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   returning id""",
                (
                    match_date, season_for_date(match_date), competition.strip() or None, home, away,
                    home_score, away_score, arena.strip() or None, sector.strip() or None,
                    seat.strip() or None, companions.strip() or None, note.strip() or None,
                ),
            ).fetchone()
            memory_id = int(row[0])
            for p in photos:
                conn.execute(
                    """insert into personal_hockey_memory_photos(
                           memory_id,mime_type,image_data,width,height,original_name
                       ) values(%s,%s,%s,%s,%s,%s)""",
                    (
                        memory_id, p["mime_type"], p["image_data"], int(p["width"]), int(p["height"]),
                        (p.get("original_name") or "").strip() or None,
                    ),
                )
            conn.commit()
        return memory_id

    def update_match_with_photos(
        self, item_id: int, *, match_date: date, home_team: str, away_team: str,
        competition: str = "", home_score: int | None = None, away_score: int | None = None,
        arena: str = "", sector: str = "", seat: str = "", companions: str = "", note: str = "",
        delete_photo_ids: list[int] | None = None, photos: list[dict] | None = None, max_photos: int = 20,
    ) -> None:
        home, away = self._validate_match(home_team, away_team, home_score, away_score)
        delete_photo_ids = [int(x) for x in (delete_photo_ids or [])]
        photos = photos or []
        with self._connect() as conn:
            self._ensure(conn)
            existing_ids = [
                int(r[0]) for r in conn.execute(
                    "select id from personal_hockey_memory_photos where memory_id=%s",
                    (int(item_id),),
                ).fetchall()
            ]
            delete_photo_ids = [x for x in delete_photo_ids if x in existing_ids]
            remaining = len(existing_ids) - len(delete_photo_ids)
            if remaining + len(photos) > max_photos:
                raise ValueError(f"После сохранения будет больше {max_photos} фотографий")

            result = conn.execute(
                """update personal_hockey_memories
                   set match_date=%s,season=%s,competition=%s,home_team=%s,away_team=%s,
                       home_score=%s,away_score=%s,arena=%s,sector=%s,seat=%s,
                       companions=%s,note=%s,updated_at=now()
                   where id=%s""",
                (
                    match_date, season_for_date(match_date), competition.strip() or None, home, away,
                    home_score, away_score, arena.strip() or None, sector.strip() or None,
                    seat.strip() or None, companions.strip() or None, note.strip() or None, int(item_id),
                ),
            )
            if result.rowcount == 0:
                raise ValueError("Воспоминание не найдено")
            if delete_photo_ids:
                conn.execute(
                    "delete from personal_hockey_memory_photos where memory_id=%s and id = any(%s)",
                    (int(item_id), delete_photo_ids),
                )
            for p in photos:
                conn.execute(
                    """insert into personal_hockey_memory_photos(
                           memory_id,mime_type,image_data,width,height,original_name
                       ) values(%s,%s,%s,%s,%s,%s)""",
                    (
                        int(item_id), p["mime_type"], p["image_data"], int(p["width"]), int(p["height"]),
                        (p.get("original_name") or "").strip() or None,
                    ),
                )
            conn.commit()

    def get_photo(self, photo_id: int) -> dict | None:
        with self._connect() as conn:
            self._ensure(conn)
            row = conn.execute(
                """select id,memory_id,mime_type,image_data,width,height,original_name,created_at
                   from personal_hockey_memory_photos where id=%s""",
                (int(photo_id),),
            ).fetchone()
        if not row:
            return None
        return {
            "id": int(row[0]),
            "memory_id": int(row[1]),
            "mime_type": row[2],
            "image_data": bytes(row[3]),
            "width": row[4],
            "height": row[5],
            "original_name": row[6] or "",
            "created_at": row[7].isoformat() if row[7] else None,
        }

    def delete_photo(self, photo_id: int) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute("delete from personal_hockey_memory_photos where id=%s", (int(photo_id),))
            conn.commit()

    def delete_match(self, item_id: int) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute("delete from personal_hockey_memories where id=%s", (item_id,))
            conn.commit()
