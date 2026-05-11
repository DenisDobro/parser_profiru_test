from __future__ import annotations

import sqlite3
from pathlib import Path

from profiru_orders_watcher.models import Order


class OrderStorage:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    fingerprint TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    collected_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def exists(self, order: Order) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM orders WHERE fingerprint = ? LIMIT 1",
                (order.fingerprint,),
            ).fetchone()
        return row is not None

    def save(self, order: Order) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO orders (fingerprint, source, title, url, collected_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order.fingerprint,
                    order.source,
                    order.title,
                    order.url,
                    order.collected_at.isoformat(),
                ),
            )
            conn.commit()
