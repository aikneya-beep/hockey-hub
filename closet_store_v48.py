from __future__ import annotations

from datetime import date
from decimal import Decimal
import os

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None


SCHEMA_SQL = """
create table if not exists personal_hockey_gear (
    id bigserial primary key,
    category text not null,
    name text not null,
    brand text,
    model text,
    color text,
    status text not null default 'active',
    condition text not null default 'в игре',
    purchased_on date,
    purchase_price numeric(12,2),
    last_service_on date,
    next_service_on date,
    notes text,
    created_at timestamptz not null default now()
);
create index if not exists personal_hockey_gear_category_idx on personal_hockey_gear(category);
create index if not exists personal_hockey_gear_service_idx on personal_hockey_gear(next_service_on);

create table if not exists personal_hockey_wishlist (
    id bigserial primary key,
    category text not null,
    name text not null,
    brand text,
    target_price numeric(12,2),
    current_price numeric(12,2),
    currency text not null default 'RUB',
    store text,
    url text,
    status text not null default 'watching',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists personal_hockey_wishlist_status_idx on personal_hockey_wishlist(status);
"""


class ClosetStore:
    def __init__(self, database_url: str | None = None):
        self.database_url = (database_url or os.getenv("DATABASE_URL") or "").strip()
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

    def _ensure_schema(self, conn) -> None:
        if self._schema_ready:
            return
        for statement in (part.strip() for part in SCHEMA_SQL.split(";")):
            if statement:
                conn.execute(statement)
        self._schema_ready = True

    def _migrate_seed(self, conn) -> None:
        done = conn.execute("select value from personal_hockey_meta where key='closet_seed_v1'").fetchone()
        if done:
            return
        seeds = [
            ("Коньки", "Коньки", "Bauer", None, "чёрный", "active", "в игре", None, None, None, None, "Модель пока не указана."),
            ("Защита", "Основной комплект защиты", "Soyuz", None, "чёрный + синие акценты", "active", "в игре", None, None, None, None, "Основная защитная экипировка; позже разложим по отдельным слотам."),
            ("Сумки и аксессуары", "Хоккейный баул", "KUBAITE", None, "чёрный", "active", "новый", None, Decimal("5326.00"), None, None, "Чёрный баул; модель пока не указана."),
        ]
        for row in seeds:
            conn.execute(
                """insert into personal_hockey_gear(
                    category,name,brand,model,color,status,condition,purchased_on,purchase_price,last_service_on,next_service_on,notes
                ) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                row,
            )
        conn.execute(
            "insert into personal_hockey_meta(key,value) values('closet_seed_v1','imported') on conflict(key) do nothing"
        )

    def _prepare(self, conn) -> None:
        self._ensure_schema(conn)
        self._migrate_seed(conn)

    def status(self) -> dict:
        return {"enabled": self.enabled, "schema_ready": self._schema_ready, "error": self._error}

    def load(self) -> dict:
        if not self.enabled:
            return {"items": [], "wishlist": [], "storage": self.status()}
        try:
            with self._connect() as conn:
                self._prepare(conn)
                items = conn.execute(
                    """select id,category,name,brand,model,color,status,condition,purchased_on,purchase_price,last_service_on,next_service_on,notes
                    from personal_hockey_gear order by category,name,id"""
                ).fetchall()
                wishlist = conn.execute(
                    """select id,category,name,brand,target_price,current_price,currency,store,url,status,notes
                    from personal_hockey_wishlist order by case when status='watching' then 0 else 1 end,created_at desc"""
                ).fetchall()
                conn.commit()
            self._error = None
            return {
                "items": [
                    {
                        "id": r[0], "category": r[1], "name": r[2], "brand": r[3], "model": r[4], "color": r[5],
                        "status": r[6], "condition": r[7], "purchased_on": r[8].isoformat() if r[8] else None,
                        "purchase_price": float(r[9]) if r[9] is not None else None,
                        "last_service_on": r[10].isoformat() if r[10] else None,
                        "next_service_on": r[11].isoformat() if r[11] else None, "notes": r[12] or "",
                    }
                    for r in items
                ],
                "wishlist": [
                    {
                        "id": r[0], "category": r[1], "name": r[2], "brand": r[3],
                        "target_price": float(r[4]) if r[4] is not None else None,
                        "current_price": float(r[5]) if r[5] is not None else None,
                        "currency": r[6], "store": r[7], "url": r[8], "status": r[9], "notes": r[10] or "",
                    }
                    for r in wishlist
                ],
                "storage": self.status(),
            }
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            print(f"[closet-db] load failed: {self._error}", flush=True)
            return {"items": [], "wishlist": [], "storage": self.status()}

    @staticmethod
    def _money(value: str | float | None) -> float | None:
        if value in (None, ""):
            return None
        number = float(str(value).replace(",", "."))
        if number < 0 or number > 100_000_000:
            raise ValueError("некорректная цена")
        return number

    def add_item(
        self, *, category: str, name: str, brand: str, model: str, color: str, condition: str,
        purchased_on: date | None, purchase_price: str | float | None, next_service_on: date | None, notes: str,
    ) -> int:
        if not self.enabled:
            raise RuntimeError("PostgreSQL is not connected")
        if not name.strip():
            raise ValueError("название вещи обязательно")
        with self._connect() as conn:
            self._prepare(conn)
            item_id = conn.execute(
                """insert into personal_hockey_gear(
                    category,name,brand,model,color,condition,purchased_on,purchase_price,next_service_on,notes
                ) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                (
                    category.strip() or "Другое", name.strip(), brand.strip() or None, model.strip() or None,
                    color.strip() or None, condition.strip() or "в игре", purchased_on,
                    self._money(purchase_price), next_service_on, notes.strip() or None,
                ),
            ).fetchone()[0]
            conn.commit()
        self._error = None
        return int(item_id)

    def add_wishlist(
        self, *, category: str, name: str, brand: str, target_price: str | float | None,
        current_price: str | float | None, store: str, url: str, notes: str,
    ) -> int:
        if not self.enabled:
            raise RuntimeError("PostgreSQL is not connected")
        if not name.strip():
            raise ValueError("название позиции обязательно")
        with self._connect() as conn:
            self._prepare(conn)
            item_id = conn.execute(
                """insert into personal_hockey_wishlist(
                    category,name,brand,target_price,current_price,store,url,notes
                ) values(%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                (
                    category.strip() or "Другое", name.strip(), brand.strip() or None,
                    self._money(target_price), self._money(current_price), store.strip() or None,
                    url.strip() or None, notes.strip() or None,
                ),
            ).fetchone()[0]
            conn.commit()
        self._error = None
        return int(item_id)
