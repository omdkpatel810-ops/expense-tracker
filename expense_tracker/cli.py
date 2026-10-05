"""The command-line interface: reads arguments, calls the database, prints results.

    expense add 12.50 food "Lunch at Subway"
    expense list --month 2026-09
    expense categories
    expense budget set food 300
    expense report --month 2026-10
    expense chart budget
    expense chart trend --months 12
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from expense_tracker import db, reports
from expense_tracker.money import format_cents, parse_amount
from expense_tracker.parsing import (
    month_label,
    month_range,
    months_back,
    parse_category,
    parse_date,
    parse_month,
)

MAX_DESCRIPTION_LENGTH = 200
DESCRIPTION_COLUMN_WIDTH = 40


def default_db_path() -> Path:
    """Use $EXPENSE_DB if it's set, otherwise ~/.expense_tracker/expenses.db."""
    override = os.environ.get("EXPENSE_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".expense_tracker" / "expenses.db"


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense",
        description="Track your spending from the command line.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="database file to use (default: $EXPENSE_DB or ~/.expense_tracker/expenses.db)",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add = commands.add_parser("add", help="record an expense")
    add.add_argument("amount", help="how much you spent, e.g. 12.50")
    add.add_argument("category", help="what kind of spending, e.g. food, rent, transit")
    add.add_argument("description", nargs="?", default="", help="what it was for (optional)")
    add.add_argument(
        "--date",
        default="today",
        help="when you spent it: YYYY-MM-DD, 'today' or 'yesterday' (default: today)",
    )

    show = commands.add_parser("list", help="show expenses, newest first")
    show.add_argument("--category", help="only show this category")
    show.add_argument("--month", help="only show this month, as YYYY-MM")
    show.add_argument(
        "--limit", type=positive_int, default=20, help="how many to show (default: 20)"
    )

    commands.add_parser("categories", help="show your categories and their budgets")

    budget = commands.add_parser("budget", help="set or show monthly budgets")
    budget_actions = budget.add_subparsers(dest="budget_action", required=True, metavar="ACTION")
    budget_set = budget_actions.add_parser("set", help="set a monthly limit for a category")
    budget_set.add_argument("category", help="e.g. food")
    budget_set.add_argument("amount", help="monthly limit, e.g. 300")
    budget_actions.add_parser("list", help="show every monthly budget")

    report = commands.add_parser("report", help="a month's spending against your budgets")
    report.add_argument("--month", help="month to report on, as YYYY-MM (default: this month)")

    chart = commands.add_parser("chart", help="save a spending chart as an image")
    chart_kinds = chart.add_subparsers(dest="chart_kind", required=True, metavar="KIND")
    budget_chart = chart_kinds.add_parser("budget", help="one month's spending against each budget")
    budget_chart.add_argument("--month", help="YYYY-MM (default: this month)")
    budget_chart.add_argument("--output", type=Path, help="file to save (.png, .svg or .pdf)")
    trend_chart = chart_kinds.add_parser("trend", help="total spending for each recent month")
    trend_chart.add_argument(
        "--months", type=positive_int, default=6, help="how many months, up to 36 (default: 6)"
    )
    trend_chart.add_argument("--category", help="only count this category")
    trend_chart.add_argument("--output", type=Path, help="file to save (.png, .svg or .pdf)")

    return parser


def cmd_add(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    amount_cents = parse_amount(args.amount)
    category = parse_category(args.category)
    spent_on = parse_date(args.date)
    description = " ".join(args.description.split())
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer.")

    new_id = db.add_expense(conn, amount_cents, category, description, spent_on)

    details = [format_cents(amount_cents), category, spent_on.isoformat()]
    if description:
        details.append(description)
    print(f"Added #{new_id}: " + " · ".join(details))
    warn_if_over_budget(conn, category, spent_on)
    return 0


def warn_if_over_budget(conn: sqlite3.Connection, category: str, day: date) -> None:
    """After an expense is added, warn if its category is now close to or over budget."""
    limit_cents = dict(db.list_budgets(conn)).get(category)
    if limit_cents is None:
        return
    start, end = month_range(day)
    spent_cents = db.spending_by_category(conn, start, end, category=category).get(category, 0)
    row = reports.CategoryReport(category, spent_cents, limit_cents)
    if row.needs_alert:
        print("! " + reports.alert_message(row, month_label(start)))


def cmd_list(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    category = parse_category(args.category) if args.category else None
    start, end = parse_month(args.month) if args.month else (None, None)

    expenses = db.list_expenses(conn, category=category, start=start, end=end, limit=args.limit)
    if not expenses:
        print("No expenses found.")
        print('Add one with: expense add 12.50 food "Lunch"')
        return 0

    rows = [
        (
            str(e.id),
            e.spent_on.isoformat(),
            e.category,
            format_cents(e.amount_cents),
            shorten(e.description, DESCRIPTION_COLUMN_WIDTH),
        )
        for e in expenses
    ]
    print_table(("ID", "Date", "Category", "Amount", "Description"), rows, right_aligned={0, 3})

    total = sum(e.amount_cents for e in expenses)
    noun = "expense" if len(expenses) == 1 else "expenses"
    print(f"\nTotal for {len(expenses)} {noun}: {format_cents(total)}")
    return 0


def cmd_categories(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    summaries = db.category_summaries(conn)
    if not summaries:
        print("No categories yet. They're created when you add an expense or set a budget.")
        return 0
    rows = [
        (
            s.name,
            str(s.expense_count),
            "-" if s.monthly_limit_cents is None else format_cents(s.monthly_limit_cents),
        )
        for s in summaries
    ]
    print_table(("Category", "Expenses", "Monthly budget"), rows, right_aligned={1, 2})
    return 0


def cmd_budget(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.budget_action == "set":
        category = parse_category(args.category)
        limit_cents = parse_amount(args.amount)
        db.set_budget(conn, category, limit_cents)
        print(f"Budget set: {category} · {format_cents(limit_cents)} per month")
        return 0

    budgets = db.list_budgets(conn)
    if not budgets:
        print("No budgets yet. Set one with: expense budget set food 300")
        return 0
    rows = [(name, format_cents(cents)) for name, cents in budgets]
    print_table(("Category", "Monthly limit"), rows, right_aligned={1})
    total = sum(cents for _, cents in budgets)
    print(f"\nTotal budgeted: {format_cents(total)} per month")
    return 0


def shorten(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def print_table(headers, rows, right_aligned=frozenset()) -> None:
    """Print rows in aligned columns. Columns in `right_aligned` line up on the right."""
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows)]

    def format_row(cells):
        parts = []
        for i, (cell, width) in enumerate(zip(cells, widths)):
            parts.append(cell.rjust(width) if i in right_aligned else cell.ljust(width))
        return "  ".join(parts).rstrip()

    print(format_row(headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(format_row(row))


def cmd_report(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    start, end = parse_month(args.month) if args.month else month_range(date.today())
    label = month_label(start)

    rows = reports.build_report(
        db.spending_by_category(conn, start, end),
        dict(db.list_budgets(conn)),
    )
    if not rows:
        print(f"Nothing to report for {label}: no spending and no budgets.")
        print("Set a budget with: expense budget set food 300")
        return 0

    def money_or_dash(cents: int | None) -> str:
        return "-" if cents is None else format_cents(cents)

    table = [
        (
            row.category,
            format_cents(row.spent_cents),
            money_or_dash(row.limit_cents),
            money_or_dash(row.left_cents),
            "-" if row.percent_used is None else f"{row.percent_used}%",
            row.status,
        )
        for row in rows
    ]
    print(f"Spending report: {label}\n")
    print_table(
        ("Category", "Spent", "Budget", "Left", "Used", "Status"),
        table,
        right_aligned={1, 2, 3, 4},
    )

    print(f"\nTotal spent: {format_cents(sum(row.spent_cents for row in rows))}")
    budgeted = [row for row in rows if row.limit_cents is not None]
    if budgeted:
        spent = sum(row.spent_cents for row in budgeted)
        limit = sum(row.limit_cents for row in budgeted)
        print(
            f"Budgeted categories: {format_cents(spent)} of {format_cents(limit)} "
            f"({spent * 100 // limit}%)"
        )

    alerts = [row for row in rows if row.needs_alert]
    if alerts:
        print("\nAlerts")
        for row in alerts:
            print("  ! " + reports.alert_message(row, label))
    elif budgeted:
        print(f"\nNo alerts. Every budget is under {reports.WARN_AT_PERCENT}%.")
    return 0


CHART_FORMATS = {".png", ".svg", ".pdf"}
MAX_TREND_MONTHS = 36


def cmd_chart(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.output is not None and args.output.suffix.lower() not in CHART_FORMATS:
        raise ValueError("Use a .png, .svg or .pdf file name for --output.")

    # matplotlib takes a moment to import, so it's only loaded when drawing a chart.
    from expense_tracker import charts

    if args.chart_kind == "budget":
        start, end = parse_month(args.month) if args.month else month_range(date.today())
        rows = reports.build_report(
            db.spending_by_category(conn, start, end),
            dict(db.list_budgets(conn)),
        )
        if not rows:
            print(f"Nothing to chart for {month_label(start)}: no spending and no budgets.")
            return 0
        figure = charts.budget_chart(rows, month_label(start))
        path = args.output or Path(f"budget-{start:%Y-%m}.png")
    else:
        if args.months > MAX_TREND_MONTHS:
            raise ValueError(f"--months can be at most {MAX_TREND_MONTHS}.")
        category = parse_category(args.category) if args.category else None
        months = months_back(date.today(), args.months)
        totals = db.monthly_totals(conn, months[0], month_range(months[-1])[1], category=category)
        values = [totals.get(f"{month:%Y-%m}", 0) for month in months]
        span = f"{month_label(months[0])} and {month_label(months[-1])}"
        if not any(values):
            what = f"{category} spending" if category else "spending"
            print(f"No {what} between {span}, so there's nothing to chart.")
            return 0
        budget = dict(db.list_budgets(conn)).get(category) if category else None
        figure = charts.trend_chart(
            months, values, category, last_month_in_progress=True, budget_cents=budget
        )
        slug = f"-{re.sub(r'[^a-z0-9]+', '-', category).strip('-')}" if category else ""
        path = args.output or Path(f"trend{slug}-{months[0]:%Y-%m}-to-{months[-1]:%Y-%m}.png")

    charts.save(figure, path)
    print(f"Saved chart to {path}")
    return 0


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "categories": cmd_categories,
    "budget": cmd_budget,
    "report": cmd_report,
    "chart": cmd_chart,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db or default_db_path()

    try:
        conn = db.connect(db_path)
    except (sqlite3.Error, OSError, RuntimeError) as error:
        print(f"error: couldn't open the database at {db_path}: {error}", file=sys.stderr)
        return 1

    try:
        return COMMANDS[args.command](conn, args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        conn.close()
