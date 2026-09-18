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
                    "select skill_key,title,level,note,updated_at from personal_hockey_skills order by title"
                ).fetchall()
                goals = conn.execute(
                    """select id,title,category,target_date,note,status,created_at,completed_at
                       from personal_hockey_goals
                       order by case when status='active' then 0 else 1 end,
                                target_date nulls last, created_at desc"""
                ).fetchall()
                homework = conn.execute(
                    """select id,text,source,due_date,status,created_at,completed_at
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
