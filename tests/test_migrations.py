import sqlite3

import pytest

from expense_tracker import db, migrations


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows} - {"sqlite_sequence"}


def test_new_database_is_on_latest_version():
    conn = db.connect(":memory:")
    assert migrations.schema_version(conn) == len(migrations.MIGRATIONS)
    conn.close()


def test_opening_twice_does_not_rerun_migrations(tmp_path):
    path = tmp_path / "expenses.db"
    db.connect(path).close()
    conn = db.connect(path)

    assert migrations.schema_version(conn) == len(migrations.MIGRATIONS)
    conn.close()


def test_failed_migration_rolls_back_completely(monkeypatch):
    conn = sqlite3.connect(":memory:")
    migrations.migrate(conn)
    version_before = migrations.schema_version(conn)

    broken = ["CREATE TABLE half_done (x INTEGER)", "THIS IS NOT SQL"]
    monkeypatch.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS + [broken])

    with pytest.raises(sqlite3.OperationalError):
        migrations.migrate(conn)

    assert migrations.schema_version(conn) == version_before
    assert "half_done" not in table_names(conn)
    conn.close()


def make_v1_database(path):
    """Build a file exactly like the first release made: v1 schema, user_version 0."""
    raw = sqlite3.connect(path)
    for statement in migrations.MIGRATIONS[0]:
        raw.execute(statement)
    raw.executemany(
        "INSERT INTO expenses (amount_cents, category, description, spent_on) VALUES (?, ?, ?, ?)",
        [
            (115000, "rent", "October rent", "2026-09-30"),
            (1250, "food", "Lunch", "2026-09-29"),
            (425, "coffee", "", "2026-09-29"),
            (899, "food", "Groceries", "2026-09-15"),
        ],
    )
    raw.commit()
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    raw.close()


def test_upgrading_a_v1_database_keeps_every_expense(tmp_path):
    path = tmp_path / "old.db"
    make_v1_database(path)

    conn = db.connect(path)
    expenses = sorted(db.list_expenses(conn), key=lambda e: e.id)

    assert migrations.schema_version(conn) == len(migrations.MIGRATIONS)
    rows = [(e.id, e.amount_cents, e.category, e.description, e.spent_on.isoformat()) for e in expenses]
    assert rows == [
        (1, 115000, "rent", "October rent", "2026-09-30"),
        (2, 1250, "food", "Lunch", "2026-09-29"),
        (3, 425, "coffee", "", "2026-09-29"),
        (4, 899, "food", "Groceries", "2026-09-15"),
    ]
    assert db.category_counts(conn) == [("coffee", 1), ("food", 2), ("rent", 1)]

    new_id = db.add_expense(conn, 500, "food", "after upgrade", expenses[0].spent_on)
    assert new_id == 5
    conn.close()


def test_upgraded_database_enforces_foreign_keys(tmp_path):
    path = tmp_path / "old.db"
    make_v1_database(path)
    conn = db.connect(path)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO expenses (amount_cents, category_id, spent_on) VALUES (100, 999, '2026-09-01')"
        )
    conn.close()


def test_refuses_database_from_a_newer_app(tmp_path):
    path = tmp_path / "from_the_future.db"
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 99")
    raw.close()

    with pytest.raises(RuntimeError, match="Update the app"):
        db.connect(path)
