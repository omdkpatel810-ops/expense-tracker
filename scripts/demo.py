"""Build a demo database with six months of sample spending, and redraw the README charts.

    python scripts/demo.py                    # creates demo.db, redraws docs/*.png
    EXPENSE_DB=demo.db expense report --month 2026-09

The data is random but seeded, so every run produces the same expenses and
the same charts. It covers May 1 to Oct 5, 2026: a student in Winnipeg
with rent, a U-Pass, a phone plan, groceries, nights out and coffee.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from expense_tracker import charts, db, reports  # noqa: E402
from expense_tracker.parsing import month_label, month_range  # noqa: E402

BUDGETS = {"rent": 115000, "food": 30000, "transit": 11300, "fun": 9000, "phone": 5500}
MONTHS = [date(2026, month, 1) for month in range(5, 11)]
LAST_DAY = date(2026, 10, 5)  # the data stops here, so October is still in progress


def cents(rng: random.Random, low: float, high: float) -> int:
    return round(rng.uniform(low, high) * 100)


def build(path: Path) -> None:
    conn = db.connect(path)
    for category, limit in BUDGETS.items():
        db.set_budget(conn, category, limit)

    rng = random.Random(7)
    for month in MONTHS:
        last = LAST_DAY.day if month.month == LAST_DAY.month else 28
        db.add_expense(conn, 115000, "rent", "Rent", month)
        db.add_expense(conn, 11300, "transit", "U-Pass", month)
        db.add_expense(conn, 5500, "phone", "Phone plan", month.replace(day=2))
        for day in range(2, last + 1, 3):
            shop = rng.choice(["Superstore", "Costco", "No Frills", "Dinner out"])
            db.add_expense(conn, cents(rng, 18, 62), "food", shop, month.replace(day=day))
        for day in rng.sample(range(3, last + 1), k=min(3, last - 2)):
            outing = rng.choice(["Movie night", "Jets game", "Bowling"])
            db.add_expense(conn, cents(rng, 14, 48), "fun", outing, month.replace(day=day))
        for day in rng.sample(range(2, last + 1), k=min(6, last - 1)):
            db.add_expense(conn, cents(rng, 2.5, 6.5), "coffee", "Tim Hortons", month.replace(day=day))
    conn.close()


def draw_charts(path: Path, folder: Path) -> list[Path]:
    conn = db.connect(path)
    budgets = dict(db.list_budgets(conn))

    september = date(2026, 9, 1)
    rows = reports.build_report(
        db.spending_by_category(conn, *month_range(september)), budgets
    )
    saved = [charts.save(charts.budget_chart(rows, month_label(september)), folder / "budget-chart.png")]

    span = (MONTHS[0], month_range(MONTHS[-1])[1])
    for category, name in [(None, "trend-chart.png"), ("food", "food-trend-chart.png")]:
        totals = db.monthly_totals(conn, *span, category=category)
        values = [totals.get(f"{m:%Y-%m}", 0) for m in MONTHS]
        figure = charts.trend_chart(
            MONTHS,
            values,
            category,
            last_month_in_progress=True,
            budget_cents=budgets.get(category) if category else None,
        )
        saved.append(charts.save(figure, folder / name))
    conn.close()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("demo.db"), help="where to create the demo database")
    parser.add_argument("--charts", type=Path, default=Path("docs"), help="folder for the chart images")
    args = parser.parse_args()

    if args.db.exists():
        sys.exit(f"{args.db} already exists. Delete it or pass --db with a new file name.")
    build(args.db)
    for path in draw_charts(args.db, args.charts):
        print(f"Saved {path}")
    print(f"\nDemo database: {args.db}\nTry: EXPENSE_DB={args.db} expense report --month 2026-09")


if __name__ == "__main__":
    main()
