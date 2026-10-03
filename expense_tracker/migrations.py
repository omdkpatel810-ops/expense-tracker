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
    # 2. Categories get their own table. Each name is stored once and every
    #    expense points to it by id (a foreign key), so a category can be
    #    renamed with one UPDATE and budgets can refer to it.
    #    SQLite can't add a foreign key to an existing table, so the expenses
    #    table is rebuilt: create the new shape, copy the rows, swap the names.
    [
        """
        CREATE TABLE categories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL UNIQUE CHECK (length(name) > 0),
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """,
        "INSERT INTO categories (name) SELECT DISTINCT category FROM expenses ORDER BY category",
        """
        CREATE TABLE expenses_new (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            category_id  INTEGER NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
            description  TEXT    NOT NULL DEFAULT '',
            spent_on     TEXT    NOT NULL
                         CHECK (spent_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
            created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """,
        """
        INSERT INTO expenses_new (id, amount_cents, category_id, description, spent_on, created_at)
        SELECT e.id, e.amount_cents, c.id, e.description, e.spent_on, e.created_at
        FROM expenses AS e
        JOIN categories AS c ON c.name = e.category
        """,
        "DROP TABLE expenses",
        "ALTER TABLE expenses_new RENAME TO expenses",
        "CREATE INDEX idx_expenses_spent_on ON expenses (spent_on)",
        "CREATE INDEX idx_expenses_category_id ON expenses (category_id)",
    ],
    # 3. A monthly spending limit per category. category_id is the primary key,
    #    so a category can have at most one budget.
    [
        """
        CREATE TABLE budgets (
            category_id         INTEGER PRIMARY KEY
                                REFERENCES categories (id) ON DELETE CASCADE,
            monthly_limit_cents INTEGER NOT NULL CHECK (monthly_limit_cents > 0),
            updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """,
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
