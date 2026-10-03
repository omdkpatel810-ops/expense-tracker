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


def test_refuses_database_from_a_newer_app(tmp_path):
    path = tmp_path / "from_the_future.db"
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 99")
    raw.close()

    with pytest.raises(RuntimeError, match="Update the app"):
        db.connect(path)
