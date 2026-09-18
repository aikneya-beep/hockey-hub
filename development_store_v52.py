from __future__ import annotations

from datetime import date
import os
from threading import Lock

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None


SKILL_SEED = (
    ("skating", "Катание"),
    ("puck", "Шайба"),
    ("shooting", "Бросок"),
    ("maneuvers", "Манёвры"),
    ("game_sense", "Игровое мышление"),
    ("physical", "Физика"),
)


class DevelopmentStore:
    def __init__(self, database_url: str | None = None):
        self.database_url = (database_url or os.getenv("DATABASE_URL") or "").strip()
        self._lock = Lock()
        self._schema_ready = False
        self._error: str | None = None

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
        statements = (
            """create table if not exists personal_hockey_skills (
                skill_key text primary key,
                title text not null,
                level integer check (level between 1 and 5),
                note text,
                updated_at timestamptz not null default now()
            )""",
            """create table if not exists personal_hockey_goals (
                id bigserial primary key,
                title text not null,
                category text,
                target_date date,
                note text,
                status text not null default 'active' check (status in ('active','done')),
                created_at timestamptz not null default now(),
                completed_at timestamptz
            )""",
            """create index if not exists personal_hockey_goals_status_idx
               on personal_hockey_goals(status, target_date nulls last)""",
            """create table if not exists personal_hockey_homework (
                id bigserial primary key,
                text text not null,
                source text,
                due_date date,
                status text not null default 'active' check (status in ('active','done')),
                created_at timestamptz not null default now(),
                completed_at timestamptz
            )""",
            """create index if not exists personal_hockey_homework_status_idx
               on personal_hockey_homework(status, due_date nulls last)""",
            """alter table personal_hockey_homework
               add column if not exists session_id bigint references personal_hockey_sessions(id) on delete set null""",
            """create unique index if not exists personal_hockey_homework_session_idx
               on personal_hockey_homework(session_id) where session_id is not null""",
        )
        for statement in statements:
            conn.execute(statement)
        for key, title in SKILL_SEED:
            conn.execute(
                """insert into personal_hockey_skills(skill_key,title)
                   values(%s,%s) on conflict(skill_key) do nothing""",
                (key, title),
            )
        self._schema_ready = True

    def load(self) -> dict:
        if not self.enabled:
            return {"skills": [], "goals": [], "homework": [], "error": "PostgreSQL is not connected"}
        try:
            with self._connect() as conn:
                self._ensure(conn)
                skills = conn.execute(
                    """select skill_key,title,level,note,updated_at
                       from personal_hockey_skills
                       order by case skill_key
                         when 'skating' then 1
                         when 'puck' then 2
                         when 'shooting' then 3
                         when 'maneuvers' then 4
                         when 'game_sense' then 5
                         when 'physical' then 6
                         else 99 end"""
                ).fetchall()
                goals = conn.execute(
                    """select id,title,category,target_date,note,status,created_at,completed_at
                       from personal_hockey_goals
                       order by case when status='active' then 0 else 1 end,
                                target_date nulls last, created_at desc"""
                ).fetchall()
                homework = conn.execute(
                    """select id,text,source,due_date,status,created_at,completed_at,session_id
                       from personal_hockey_homework
                       order by case when status='active' then 0 else 1 end,
                                due_date nulls last, created_at desc"""
                ).fetchall()
                conn.commit()
            self._error = None
            return {
                "skills": [
                    {
                        "key": r[0], "title": r[1], "level": r[2], "note": r[3] or "",
                        "updated_at": r[4].isoformat() if r[4] else None,
                    } for r in skills
                ],
                "goals": [
                    {
                        "id": r[0], "title": r[1], "category": r[2] or "",
                        "target_date": r[3].isoformat() if r[3] else None,
                        "note": r[4] or "", "status": r[5],
                        "created_at": r[6].isoformat() if r[6] else None,
                        "completed_at": r[7].isoformat() if r[7] else None,
                    } for r in goals
                ],
                "homework": [
                    {
                        "id": r[0], "text": r[1], "source": r[2] or "",
                        "due_date": r[3].isoformat() if r[3] else None,
                        "status": r[4],
                        "created_at": r[5].isoformat() if r[5] else None,
                        "completed_at": r[6].isoformat() if r[6] else None,
                        "session_id": r[7],
                    } for r in homework
                ],
                "error": None,
            }
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            print(f"[development-db] load failed: {self._error}", flush=True)
            return {"skills": [], "goals": [], "homework": [], "error": self._error}

    def update_skill(self, key: str, level: int | None, note: str) -> None:
        if key not in {x[0] for x in SKILL_SEED}:
            raise ValueError("unknown skill")
        if level is not None and level not in {1, 2, 3, 4, 5}:
            raise ValueError("level must be 1..5")
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute(
                """update personal_hockey_skills
                   set level=%s,note=%s,updated_at=now()
                   where skill_key=%s""",
                (level, note.strip() or None, key),
            )
            conn.commit()

    def add_goal(self, title: str, category: str, target_date: date | None, note: str) -> int:
        title = title.strip()
        if not title:
            raise ValueError("goal title is empty")
        with self._connect() as conn:
            self._ensure(conn)
            row = conn.execute(
                """insert into personal_hockey_goals(title,category,target_date,note)
                   values(%s,%s,%s,%s) returning id""",
                (title, category.strip() or None, target_date, note.strip() or None),
            ).fetchone()
            conn.commit()
        return int(row[0])

    def add_homework(self, text: str, source: str, due_date: date | None) -> int:
        text = text.strip()
        if not text:
            raise ValueError("homework is empty")
        with self._connect() as conn:
            self._ensure(conn)
            row = conn.execute(
                """insert into personal_hockey_homework(text,source,due_date)
                   values(%s,%s,%s) returning id""",
                (text, source.strip() or None, due_date),
            ).fetchone()
            conn.commit()
        return int(row[0])

    def update_goal(self, item_id: int, title: str, category: str, target_date: date | None, note: str) -> None:
        title = title.strip()
        if not title:
            raise ValueError("goal title is empty")
        with self._connect() as conn:
            self._ensure(conn)
            result = conn.execute(
                """update personal_hockey_goals
                   set title=%s,category=%s,target_date=%s,note=%s
                   where id=%s""",
                (title, category.strip() or None, target_date, note.strip() or None, int(item_id)),
            )
            if result.rowcount == 0:
                raise ValueError("goal not found")
            conn.commit()

    def update_homework(self, item_id: int, text: str, source: str, due_date: date | None) -> None:
        text = text.strip()
        if not text:
            raise ValueError("homework is empty")
        with self._connect() as conn:
            self._ensure(conn)
            result = conn.execute(
                """update personal_hockey_homework
                   set text=%s,source=%s,due_date=%s
                   where id=%s""",
                (text, source.strip() or None, due_date, int(item_id)),
            )
            if result.rowcount == 0:
                raise ValueError("homework not found")
            conn.commit()

    def set_goal_done(self, item_id: int, done: bool) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute(
                """update personal_hockey_goals
                   set status=%s,completed_at=case when %s then now() else null end
                   where id=%s""",
                ("done" if done else "active", done, item_id),
            )
            conn.commit()

    def set_homework_done(self, item_id: int, done: bool) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute(
                """update personal_hockey_homework
                   set status=%s,completed_at=case when %s then now() else null end
                   where id=%s""",
                ("done" if done else "active", done, item_id),
            )
            conn.commit()


    def sync_session_homework(self, session_id: int, text: str, source: str, due_date: date | None = None) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            clean = (text or "").strip()
            if not clean:
                conn.execute("delete from personal_hockey_homework where session_id=%s", (int(session_id),))
            else:
                conn.execute(
                    """insert into personal_hockey_homework(text,source,due_date,status,session_id)
                       values(%s,%s,%s,'active',%s)
                       on conflict(session_id) where session_id is not null
                       do update set text=excluded.text,source=excluded.source,due_date=excluded.due_date,
                                     status='active',completed_at=null""",
                    (clean, (source or "").strip() or None, due_date, int(session_id)),
                )
            conn.commit()

    def delete_goal(self, item_id: int) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute("delete from personal_hockey_goals where id=%s", (int(item_id),))
            conn.commit()

    def delete_homework(self, item_id: int) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute("delete from personal_hockey_homework where id=%s", (int(item_id),))
            conn.commit()
