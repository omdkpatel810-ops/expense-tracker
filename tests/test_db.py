import sqlite3
from datetime import date

import pytest

from expense_tracker import db


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()


def test_add_then_list_returns_the_expense(conn):
    new_id = db.add_expense(conn, 1250, "food", "Lunch", date(2026, 9, 30))

    [expense] = db.list_expenses(conn)
    assert expense == db.Expense(new_id, 1250, "food", "Lunch", date(2026, 9, 30))


def test_list_is_newest_first(conn):
    db.add_expense(conn, 100, "food", "older", date(2026, 9, 1))
    db.add_expense(conn, 200, "food", "newer", date(2026, 9, 20))
    db.add_expense(conn, 300, "food", "same day, added later", date(2026, 9, 20))

    descriptions = [e.description for e in db.list_expenses(conn)]
    assert descriptions == ["same day, added later", "newer", "older"]


def test_filter_by_category(conn):
    db.add_expense(conn, 100, "food", "", date(2026, 9, 1))
    db.add_expense(conn, 200, "rent", "", date(2026, 9, 1))

    assert [e.category for e in db.list_expenses(conn, category="rent")] == ["rent"]


def test_filter_by_date_range_includes_start_and_excludes_end(conn):
    db.add_expense(conn, 100, "food", "aug 31", date(2026, 8, 31))
    db.add_expense(conn, 200, "food", "sep 1", date(2026, 9, 1))
    db.add_expense(conn, 300, "food", "sep 30", date(2026, 9, 30))
    db.add_expense(conn, 400, "food", "oct 1", date(2026, 10, 1))

    september = db.list_expenses(conn, start=date(2026, 9, 1), end=date(2026, 10, 1))
    assert [e.description for e in september] == ["sep 30", "sep 1"]


def test_limit(conn):
    for day in range(1, 6):
        db.add_expense(conn, 100, "food", "", date(2026, 9, day))

    assert len(db.list_expenses(conn, limit=2)) == 2


def test_database_rejects_zero_amount(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.add_expense(conn, 0, "food", "", date(2026, 9, 1))


def test_category_counts(conn):
    db.add_expense(conn, 100, "rent", "", date(2026, 9, 1))
    db.add_expense(conn, 100, "food", "", date(2026, 9, 1))
    db.add_expense(conn, 100, "food", "", date(2026, 9, 2))

    assert db.category_counts(conn) == [("food", 2), ("rent", 1)]


def test_each_category_name_is_stored_once(conn):
    db.add_expense(conn, 100, "food", "", date(2026, 9, 1))
    db.add_expense(conn, 200, "food", "", date(2026, 9, 2))

    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1


def test_database_rejects_unknown_category_id(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO expenses (amount_cents, category_id, spent_on) VALUES (100, 42, '2026-09-01')"
        )


def test_database_rejects_badly_formatted_date(conn):
    db.add_expense(conn, 100, "food", "", date(2026, 9, 1))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO expenses (amount_cents, category_id, spent_on) VALUES (100, 1, 'Sept 1')"
        )


def test_data_is_saved_to_disk(tmp_path):
    path = tmp_path / "nested" / "expenses.db"

    first = db.connect(path)
    db.add_expense(first, 999, "transit", "Bus pass", date(2026, 9, 1))
    first.close()

    second = db.connect(path)
    assert [e.description for e in db.list_expenses(second)] == ["Bus pass"]
    second.close()
