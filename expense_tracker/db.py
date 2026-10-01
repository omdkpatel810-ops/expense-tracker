"""Everything that reads or writes the SQLite database lives in this file.

Keeping SQL in one place means the rest of the app never builds queries
itself, and swapping storage later only touches this module.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL CHECK (length(category) > 0),
    description  TEXT    NOT NULL DEFAULT '',
    spent_on     TEXT    NOT NULL,  -- ISO date like 2026-09-30, so text order = date order
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_expenses_spent_on ON expenses (spent_on);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category);
"""


@dataclass(frozen=True)
class Expense:
    id: int
    amount_cents: int
    category: str
    description: str
    spent_on: date


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database at `path`, creating the file and tables if needed."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_expense(
    conn: sqlite3.Connection,
    amount_cents: int,
    category: str,
    description: str,
    spent_on: date,
) -> int:
    """Save one expense and return its new id."""
    with conn:  # commits on success, rolls back on error
        cursor = conn.execute(
            "INSERT INTO expenses (amount_cents, category, description, spent_on) "
            "VALUES (?, ?, ?, ?)",
            (amount_cents, category, description, spent_on.isoformat()),
        )
    return cursor.lastrowid


def list_expenses(
    conn: sqlite3.Connection,
    category: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[Expense]:
    """Return expenses newest first, optionally filtered.

    `start` is included and `end` is excluded, so (Sep 1, Oct 1) means all of September.
    Values are always passed as ? parameters, never pasted into the SQL string,
    which is what prevents SQL injection.
    """
    conditions: list[str] = []
    params: list[object] = []
    if category is not None:
        conditions.append("category = ?")
        params.append(category)
    if start is not None:
        conditions.append("spent_on >= ?")
        params.append(start.isoformat())
    if end is not None:
        conditions.append("spent_on < ?")
        params.append(end.isoformat())

    sql = "SELECT id, amount_cents, category, description, spent_on FROM expenses"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY spent_on DESC, id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        Expense(
            id=row["id"],
            amount_cents=row["amount_cents"],
            category=row["category"],
            description=row["description"],
            spent_on=date.fromisoformat(row["spent_on"]),
        )
        for row in rows
    ]


def category_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Return every category used so far with how many expenses it has."""
    rows = conn.execute(
        "SELECT category, COUNT(*) AS n FROM expenses GROUP BY category ORDER BY category"
    ).fetchall()
    return [(row["category"], row["n"]) for row in rows]
