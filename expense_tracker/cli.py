"""The command-line interface: reads arguments, calls the database, prints results.

    expense add 12.50 food "Lunch at Subway"
    expense list --month 2026-09
    expense categories
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from expense_tracker import db
from expense_tracker.money import format_cents, parse_amount
from expense_tracker.parsing import parse_category, parse_date, parse_month

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

    commands.add_parser("categories", help="show the categories you've used")

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
    return 0


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
    counts = db.category_counts(conn)
    if not counts:
        print("No categories yet. They're created when you add an expense.")
        return 0
    print_table(("Category", "Expenses"), [(name, str(n)) for name, n in counts], right_aligned={1})
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


COMMANDS = {"add": cmd_add, "list": cmd_list, "categories": cmd_categories}


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
