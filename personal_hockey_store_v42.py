from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
from threading import Lock

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

BASE = Path(__file__).resolve().parent
SEED_PATH = BASE / "personal_hockey_data.json"
SCHEMA_PATH = BASE / "personal_schema.sql"


class PersonalHockeyStore:
    def __init__(self, database_url: str | None = None):
        self.database_url = (database_url or os.getenv("DATABASE_URL") or "").strip()
        self._lock = Lock()
        self._schema_ready = False
        self._error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.database_url and psycopg is not None)

    def _seed(self) -> dict:
        try:
            return json.loads(SEED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"profile": {}, "coach_notes": [], "sessions": [], "tests": []}

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "mode": "postgres" if self.enabled else "seed_read_only",
            "schema_ready": self._schema_ready,
            "error": self._error,
        }

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        return psycopg.connect(self.database_url, connect_timeout=8)

    def _ensure_schema(self, conn) -> None:
        if self._schema_ready:
            return
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                conn.execute(statement)
        self._schema_ready = True

    def _migrate_seed(self, conn) -> None:
        done = conn.execute(
            "select value from personal_hockey_meta where key='seed_v1'"
        ).fetchone()
        if done:
            return
        seed = self._seed()
        for row in seed.get("sessions") or []:
            conn.execute(
                "insert into personal_hockey_sessions(session_date,session_type,focus,note) values(%s,%s,%s,%s)",
                (row.get("date"), row.get("type") or "Тренировка", row.get("focus") or [], row.get("note") or None),
            )
        for row in seed.get("coach_notes") or []:
            conn.execute(
                "insert into personal_hockey_coach_notes(note_date,text) values(%s,%s)",
                (row.get("date"), row.get("text") or ""),
            )
        for row in seed.get("tests") or []:
            conn.execute(
                "insert into personal_hockey_tests(test_date,metric,rink,start_mode,direction,seconds) values(%s,%s,%s,%s,%s,%s)",
                (
                    row.get("date"), row.get("metric") or "Тест", row.get("rink"), row.get("start"),
                    row.get("direction"), row.get("seconds"),
                ),
            )
        conn.execute(
            "insert into personal_hockey_meta(key,value) values('seed_v1','imported') on conflict(key) do nothing"
        )

    def _prepare(self, conn) -> None:
        self._ensure_schema(conn)
        self._migrate_seed(conn)

    def load(self) -> dict:
        seed = self._seed()
        if not self.enabled:
            return {**seed, "storage": self.status()}
        try:
            with self._connect() as conn:
                self._prepare(conn)
                sessions = conn.execute(
                    "select id,session_date,session_type,focus,wellbeing,load,note,homework from personal_hockey_sessions order by session_date desc,id desc"
                ).fetchall()
                notes = conn.execute(
                    "select note_date,text,session_id from personal_hockey_coach_notes order by note_date desc,id desc"
                ).fetchall()
                tests = conn.execute(
                    "select test_date,metric,rink,start_mode,direction,seconds,session_id from personal_hockey_tests order by test_date,id"
                ).fetchall()
                conn.commit()
            self._error = None
            return {
                "profile": seed.get("profile") or {},
                "sessions": [
                    {
                        "id": r[0], "date": r[1].isoformat(), "type": r[2], "focus": list(r[3] or []),
                        "wellbeing": r[4], "load": r[5], "note": r[6] or "", "homework": r[7] or "",
                    }
                    for r in sessions
                ],
                "coach_notes": [
                    {"date": r[0].isoformat(), "text": r[1], "session_id": r[2]} for r in notes
                ],
                "tests": [
                    {
                        "date": r[0].isoformat(), "metric": r[1], "rink": r[2], "start": r[3],
                        "direction": r[4], "seconds": float(r[5]) if r[5] is not None else None, "session_id": r[6],
                    }
                    for r in tests
                ],
                "storage": self.status(),
            }
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            print(f"[personal-db] load failed: {self._error}", flush=True)
            return {**seed, "storage": self.status()}

    @staticmethod
    def _score(value: int | None) -> int | None:
        if value is None:
            return None
        return max(1, min(10, int(value)))
    def update_session(
        self,
        session_id: int,
        *,
        session_date: date,
        session_type: str,
        focus: list[str],
        wellbeing: int | None,
        load: int | None,
        note: str,
        homework: str,
        coach_note: str,
        lap_1: float | None,
        lap_2: float | None,
    ) -> None:
        if not self.enabled:
            raise RuntimeError("PostgreSQL is not connected to the web service")
        with self._connect() as conn:
            self._prepare(conn)
            result = conn.execute(
                """update personal_hockey_sessions
                   set session_date=%s,session_type=%s,focus=%s,wellbeing=%s,load=%s,note=%s,homework=%s
                   where id=%s""",
                (
                    session_date, session_type.strip() or "Тренировка", focus,
                    self._score(wellbeing), self._score(load),
                    note.strip() or None, homework.strip() or None, int(session_id),
                ),
            )
            if result.rowcount == 0:
                raise ValueError("Тренировка не найдена")

            conn.execute(
                "delete from personal_hockey_coach_notes where session_id=%s",
                (int(session_id),),
            )
            if coach_note.strip():
                conn.execute(
                    "insert into personal_hockey_coach_notes(note_date,text,session_id) values(%s,%s,%s)",
                    (session_date, coach_note.strip(), int(session_id)),
                )

            conn.execute(
                "delete from personal_hockey_tests where session_id=%s and metric='Полный круг'",
                (int(session_id),),
            )
            for direction, seconds in (("Направление 1", lap_1), ("Направление 2", lap_2)):
                if seconds is None:
                    continue
                conn.execute(
                    """insert into personal_hockey_tests(
                           test_date,metric,rink,start_mode,direction,seconds,session_id
                       ) values(%s,'Полный круг','60×30 м','с места',%s,%s,%s)""",
                    (session_date, direction, float(seconds), int(session_id)),
                )
            conn.commit()
        self._error = None

    def add_session(
        self,
        *,
        session_date: date,
        session_type: str,
        focus: list[str],
        wellbeing: int | None,
        load: int | None,
        note: str,
        homework: str,
        coach_note: str,
        lap_1: float | None,
        lap_2: float | None,
    ) -> int:
        if not self.enabled:
            raise RuntimeError("PostgreSQL is not connected to the web service")
        with self._connect() as conn:
            self._prepare(conn)
            session_id = conn.execute(
                "insert into personal_hockey_sessions(session_date,session_type,focus,wellbeing,load,note,homework) values(%s,%s,%s,%s,%s,%s,%s) returning id",
                (
                    session_date, session_type.strip() or "Тренировка", focus,
                    self._score(wellbeing), self._score(load), note.strip() or None, homework.strip() or None,
                ),
            ).fetchone()[0]
            if coach_note.strip():
                conn.execute(
                    "insert into personal_hockey_coach_notes(note_date,text,session_id) values(%s,%s,%s)",
                    (session_date, coach_note.strip(), session_id),
                )
            for direction, seconds in (("Направление 1", lap_1), ("Направление 2", lap_2)):
                if seconds is None:
                    continue
                conn.execute(
                    "insert into personal_hockey_tests(test_date,metric,rink,start_mode,direction,seconds,session_id) values(%s,'Полный круг','60×30 м','с места',%s,%s,%s)",
                    (session_date, direction, float(seconds), session_id),
                )
            conn.commit()
        self._error = None
        return int(session_id)
