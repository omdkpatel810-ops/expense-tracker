from datetime import date, timedelta

import pytest

from expense_tracker.cli import default_db_path, main


@pytest.fixture
def run(tmp_path, capsys):
    """Run the CLI against a fresh database and return (exit_code, stdout, stderr)."""
    db_file = tmp_path / "test.db"

    def _run(*args):
        code = main(["--db", str(db_file), *args])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def test_add_prints_confirmation(run):
    code, out, _ = run("add", "12.50", "Food", "Lunch at Subway", "--date", "2026-09-30")

    assert code == 0
    assert out.strip() == "Added #1: $12.50 · food · 2026-09-30 · Lunch at Subway"


def test_add_defaults_to_today(run):
    run("add", "5", "coffee")

    _, out, _ = run("list")
    assert date.today().isoformat() in out


def test_add_rejects_bad_amount_without_saving(run):
    code, _, err = run("add", "twelve", "food")

    assert code == 2
    assert "not an amount" in err
    assert "No expenses found" in run("list")[1]


def test_add_rejects_future_date(run):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    code, _, err = run("add", "5", "food", "--date", tomorrow)

    assert code == 2
    assert "future" in err


def test_list_shows_table_and_total(run):
    run("add", "12.50", "food", "Lunch", "--date", "2026-09-29")
    run("add", "1200", "rent", "October rent", "--date", "2026-09-30")

    code, out, _ = run("list")
    lines = out.splitlines()

    assert code == 0
    assert lines[0].split() == ["ID", "Date", "Category", "Amount", "Description"]
    assert "October rent" in lines[2]  # newest first
    assert "Lunch" in lines[3]
    assert lines[-1] == "Total for 2 expenses: $1,212.50"


def test_list_filters_by_month_and_category(run):
    run("add", "10", "food", "August lunch", "--date", "2026-08-31")
    run("add", "20", "food", "September lunch", "--date", "2026-09-01")
    run("add", "30", "transit", "Bus pass", "--date", "2026-09-02")

    _, out, _ = run("list", "--month", "2026-09", "--category", "FOOD")

    assert "September lunch" in out
    assert "August lunch" not in out
    assert "Bus pass" not in out
    assert out.splitlines()[-1] == "Total for 1 expense: $20.00"


def test_list_rejects_bad_month(run):
    code, _, err = run("list", "--month", "September")

    assert code == 2
    assert "YYYY-MM" in err


def test_list_when_empty(run):
    code, out, _ = run("list")

    assert code == 0
    assert "No expenses found" in out


def test_categories(run):
    run("add", "10", "food")
    run("add", "20", "Food")
    run("add", "30", "rent")

    _, out, _ = run("categories")
    rows = [line.split() for line in out.splitlines()[2:]]
    assert rows == [["food", "2"], ["rent", "1"]]


def test_database_from_newer_app_gives_clear_error(tmp_path, capsys):
    import sqlite3

    path = tmp_path / "newer.db"
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 99")
    raw.close()

    code = main(["--db", str(path), "list"])

    assert code == 1
    assert "Update the app" in capsys.readouterr().err


def test_default_db_path_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPENSE_DB", str(tmp_path / "mine.db"))
    assert default_db_path() == tmp_path / "mine.db"


def test_default_db_path_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("EXPENSE_DB", raising=False)
    assert default_db_path().name == "expenses.db"
    assert default_db_path().parent.name == ".expense_tracker"
