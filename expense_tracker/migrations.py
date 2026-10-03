"""Database schema versions, applied in order.

Every database file remembers which version it's on in SQLite's built-in
`user_version` number (0 for a brand-new file). When the app opens a
database it runs each migration newer than that number, so someone with
an old file is upgraded automatically and keeps all their data.

Rules for changing the schema:
  - Never edit a migration that has already shipped. Add a new one.
  - Each migration runs inside one transaction, so it applies completely
    or not at all. A crash halfway can't leave a half-upgraded database.
"""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[list[str]] = [
    # 1. The first schema: one table, with the category name stored on every expense.
    #    IF NOT EXISTS because files created before migrations existed already have it.
    [
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            category     TEXT    NOT NULL CHECK (length(category) > 0),
            description  TEXT    NOT NULL DEFAULT '',
            spent_on     TEXT    NOT NULL,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_expenses_spent_on ON expenses (spent_on)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category)",
    ],
]


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    """Bring the database up to the latest schema and return that version number."""
    latest = len(MIGRATIONS)
    version = schema_version(conn)
    if version > latest:
        raise RuntimeError(
            f"this database uses schema version {version}, but this copy of the app "
            f"only knows up to version {latest}. Update the app to open it."
        )

    previous_mode = conn.isolation_level
    conn.isolation_level = None  # we send BEGIN and COMMIT ourselves
    try:
        for number in range(version + 1, latest + 1):
            conn.execute("BEGIN IMMEDIATE")  # take the write lock before changing anything
            try:
                for statement in MIGRATIONS[number - 1]:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {number}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.isolation_level = previous_mode
    return latest
