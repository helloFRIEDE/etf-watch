"""SQLite persistence for holdings."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Holding

_SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT NOT NULL,
    shares   REAL NOT NULL,
    avg_cost REAL NOT NULL,
    note     TEXT NOT NULL DEFAULT ''
);
"""


class HoldingStore:
    """CRUD for holdings. Use path=':memory:' in tests."""

    def __init__(self, path: str | Path = "data/portfolio.db") -> None:
        path = str(path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_holding(row: sqlite3.Row) -> Holding:
        return Holding(
            id=row["id"],
            symbol=row["symbol"],
            shares=row["shares"],
            avg_cost=row["avg_cost"],
            note=row["note"],
        )

    def add(self, holding: Holding) -> Holding:
        cur = self._conn.execute(
            "INSERT INTO holdings (symbol, shares, avg_cost, note) VALUES (?, ?, ?, ?)",
            (holding.symbol, holding.shares, holding.avg_cost, holding.note),
        )
        self._conn.commit()
        holding.id = cur.lastrowid
        return holding

    def get(self, holding_id: int) -> Holding | None:
        row = self._conn.execute(
            "SELECT * FROM holdings WHERE id = ?", (holding_id,)
        ).fetchone()
        return self._row_to_holding(row) if row else None

    def list(self) -> list[Holding]:
        rows = self._conn.execute("SELECT * FROM holdings ORDER BY id").fetchall()
        return [self._row_to_holding(r) for r in rows]

    def update(self, holding: Holding) -> None:
        if holding.id is None:
            raise ValueError("更新需要持股 id")
        cur = self._conn.execute(
            "UPDATE holdings SET symbol = ?, shares = ?, avg_cost = ?, note = ? WHERE id = ?",
            (holding.symbol, holding.shares, holding.avg_cost, holding.note, holding.id),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"找不到持股 id={holding.id}")

    def delete(self, holding_id: int) -> None:
        cur = self._conn.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))
        self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"找不到持股 id={holding_id}")
