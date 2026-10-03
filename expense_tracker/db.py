"""Everything that reads or writes the SQLite database lives in this file.

Keeping SQL in one place means the rest of the app never builds queries
itself, and swapping storage later only touches this module.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from expense_tracker import migrations


@dataclass(frozen=True)
class Expense:
    id: int
    amount_cents: int
    category: str
    description: str
    spent_on: date


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database at `path`, creating it or upgrading its schema if needed."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite leaves foreign keys unchecked unless asked
    try:
        migrations.migrate(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def add_expense(
    conn: sqlite3.Connection,
    amount_cents: int,
    category: str,
    description: str,
    spent_on: date,
) -> int:
    """Save one expense and return its new id. Creates the category if it's new."""
    with conn:  # one transaction: commits on success, rolls back on error
        category_id = _category_id(conn, category)
        cursor = conn.execute(
            "INSERT INTO expenses (amount_cents, category_id, description, spent_on) "
            "VALUES (?, ?, ?, ?)",
            (amount_cents, category_id, description, spent_on.isoformat()),
        )
    return cursor.lastrowid


def _category_id(conn: sqlite3.Connection, name: str) -> int:
    """Return the id for a category name, creating the category if it doesn't exist."""
    conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    return row["id"]


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
        conditions.append("c.name = ?")
        params.append(category)
    if start is not None:
        conditions.append("e.spent_on >= ?")
        params.append(start.isoformat())
    if end is not None:
        conditions.append("e.spent_on < ?")
        params.append(end.isoformat())

    sql = (
        "SELECT e.id, e.amount_cents, c.name AS category, e.description, e.spent_on "
        "FROM expenses AS e JOIN categories AS c ON c.id = e.category_id"
    )
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY e.spent_on DESC, e.id DESC"
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
    """Return every category with how many expenses it has (including zero)."""
    rows = conn.execute(
        "SELECT c.name, COUNT(e.id) AS n "
        "FROM categories AS c LEFT JOIN expenses AS e ON e.category_id = c.id "
        "GROUP BY c.id ORDER BY c.name"
    ).fetchall()
    return [(row["name"], row["n"]) for row in rows]
