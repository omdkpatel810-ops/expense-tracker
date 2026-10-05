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

    run("budget", "set", "rent", "1150")

    _, out, _ = run("categories")
    rows = [line.split() for line in out.splitlines()[2:]]
    assert rows == [["food", "2", "-"], ["rent", "1", "$1,150.00"]]


def test_budget_set_and_list(run):
    code, out, _ = run("budget", "set", "Food", "300")
    assert code == 0
    assert out.strip() == "Budget set: food · $300.00 per month"

    run("budget", "set", "transit", "113")
    run("budget", "set", "food", "250")  # replaces the first food budget

    _, out, _ = run("budget", "list")
    lines = out.splitlines()
    assert [line.split() for line in lines[2:4]] == [["food", "$250.00"], ["transit", "$113.00"]]
    assert lines[-1] == "Total budgeted: $363.00 per month"


def test_budget_list_when_empty(run):
    _, out, _ = run("budget", "list")
    assert "No budgets yet" in out


def test_budget_rejects_bad_amount(run):
    code, _, err = run("budget", "set", "food", "-20")

    assert code == 2
    assert "error:" in err


def test_report_shows_budgets_totals_and_alerts(run):
    run("budget", "set", "food", "300")
    run("budget", "set", "rent", "1150")
    run("budget", "set", "travel", "500")
    run("add", "1150", "rent", "October rent", "--date", "2026-10-01")
    run("add", "200", "food", "Groceries", "--date", "2026-10-02")
    run("add", "46", "food", "Dinner out", "--date", "2026-10-03")
    run("add", "4.25", "coffee", "--date", "2026-10-03")
    run("add", "999", "food", "Last month", "--date", "2026-09-30")

    code, out, _ = run("report", "--month", "2026-10")
    lines = out.splitlines()

    assert code == 0
    assert lines[0] == "Spending report: October 2026"
    assert lines[2].split() == ["Category", "Spent", "Budget", "Left", "Used", "Status"]
    rows = [line.split(maxsplit=5) for line in lines[4:8]]
    assert rows == [
        ["rent", "$1,150.00", "$1,150.00", "$0.00", "100%", "limit reached"],
        ["food", "$246.00", "$300.00", "$54.00", "82%", "close to limit"],
        ["coffee", "$4.25", "-", "-", "-", "no budget"],
        ["travel", "$0.00", "$500.00", "$500.00", "0%", "on track"],
    ]
    assert "Total spent: $1,400.25" in out
    assert "Budgeted categories: $1,396.00 of $1,950.00 (71%)" in out
    assert "  ! food is at 82% of its $300.00 budget for October 2026, $54.00 left." in lines
    assert not any(line.startswith("  ! rent") for line in lines)  # exactly on budget is fine


def test_report_without_alerts(run):
    run("budget", "set", "food", "300")
    run("add", "20", "food", "--date", "2026-10-02")

    _, out, _ = run("report", "--month", "2026-10")

    assert "No alerts. Every budget is under 80%." in out


def test_report_defaults_to_this_month(run):
    run("add", "7", "coffee")

    _, out, _ = run("report")

    assert out.splitlines()[0] == "Spending report: " + date.today().strftime("%B %Y")
    assert "coffee" in out


def test_report_when_nothing_to_show(run):
    code, out, _ = run("report", "--month", "2026-10")

    assert code == 0
    assert "Nothing to report for October 2026" in out


def test_report_rejects_bad_month(run):
    code, _, err = run("report", "--month", "Oct")

    assert code == 2
    assert "YYYY-MM" in err


def test_add_warns_when_category_gets_close_to_budget(run):
    run("budget", "set", "food", "300")
    _, quiet, _ = run("add", "200", "food", "--date", "2026-10-02")
    _, warned, _ = run("add", "46", "food", "--date", "2026-10-03")

    assert "!" not in quiet
    assert warned.splitlines()[1] == (
        "! food is at 82% of its $300.00 budget for October 2026, $54.00 left."
    )


def test_add_warns_when_over_budget(run):
    run("budget", "set", "food", "300")
    run("add", "300", "food", "--date", "2026-10-02")
    _, out, _ = run("add", "12.40", "food", "--date", "2026-10-03")

    assert "! food is $12.40 over its $300.00 budget for October 2026 ($312.40 spent)." in out


def test_add_does_not_warn_when_landing_exactly_on_budget(run):
    run("budget", "set", "rent", "1150")
    _, out, _ = run("add", "1150", "rent", "--date", "2026-10-01")

    assert "!" not in out


def test_add_checks_the_budget_for_the_expense_month(run):
    run("budget", "set", "food", "300")
    run("add", "290", "food", "--date", "2026-09-15")
    _, out, _ = run("add", "5", "food", "--date", "2026-10-01")  # new month, fresh budget

    assert "!" not in out


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def months_ago(n):
    """A date n months before today, on the 1st (always a valid date)."""
    today = date.today()
    index = today.year * 12 + today.month - 1 - n
    return date(index // 12, index % 12 + 1, 1)


def test_chart_budget_saves_png(run, tmp_path):
    run("budget", "set", "food", "300")
    run("add", "250", "food", "--date", "2026-10-02")
    out_file = tmp_path / "charts" / "october.png"

    code, out, _ = run("chart", "budget", "--month", "2026-10", "--output", str(out_file))

    assert code == 0
    assert out.strip() == f"Saved chart to {out_file}"
    assert out_file.read_bytes().startswith(PNG_SIGNATURE)


def test_chart_budget_default_file_name(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("add", "12", "food", "--date", "2026-10-02")

    _, out, _ = run("chart", "budget", "--month", "2026-10")

    assert out.strip() == "Saved chart to budget-2026-10.png"
    assert (tmp_path / "budget-2026-10.png").exists()


def test_chart_budget_with_nothing_to_show(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, _ = run("chart", "budget", "--month", "2026-10")

    assert code == 0
    assert "Nothing to chart for October 2026" in out
    assert list(tmp_path.glob("*.png")) == []


def test_chart_trend_default_file_name(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("add", "100", "food", "--date", months_ago(2).isoformat())
    run("add", "50", "food")

    code, out, _ = run("chart", "trend", "--months", "3")

    expected = f"trend-{months_ago(2):%Y-%m}-to-{date.today():%Y-%m}.png"
    assert code == 0
    assert out.strip() == f"Saved chart to {expected}"
    assert (tmp_path / expected).read_bytes().startswith(PNG_SIGNATURE)


def test_chart_trend_for_one_category(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("add", "40", "Eating Out")

    _, out, _ = run("chart", "trend", "--category", "eating out")

    assert out.strip().startswith("Saved chart to trend-eating-out-")


def test_chart_trend_with_no_spending(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run("add", "40", "food")

    code, out, _ = run("chart", "trend", "--category", "travel")

    assert code == 0
    assert "No travel spending between" in out
    assert list(tmp_path.glob("*.png")) == []


def test_chart_rejects_unknown_file_type(run, tmp_path):
    code, _, err = run("chart", "budget", "--output", str(tmp_path / "chart.jpg"))

    assert code == 2
    assert ".png, .svg or .pdf" in err


def test_chart_trend_rejects_too_many_months(run):
    code, _, err = run("chart", "trend", "--months", "120")

    assert code == 2
    assert "at most 36" in err


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
