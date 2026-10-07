"""Time the app's real queries on a large database, with different indexes.

    python scripts/benchmark.py              # 100,000 expenses, 15 runs per query
    python scripts/benchmark.py --rows 500000 --runs 25

It builds a throwaway database (about 3 years of expenses across 12
categories) with the current schema and times each query several times,
reporting the median. Then it drops the covering index and times again,
then drops the date index too and times a third time.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import random
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from expense_tracker import db  # noqa: E402
from expense_tracker.cli import main  # noqa: E402

CATEGORIES = [
    "rent", "food", "transit", "fun", "phone", "coffee",
    "books", "gym", "clothes", "gifts", "travel", "health",
]
FIRST_DAY = date(2024, 1, 1)
LAST_DAY = date(2026, 9, 30)
MONTH = (date(2026, 9, 1), date(2026, 10, 1))
YEAR = (date(2025, 10, 1), date(2026, 10, 1))


def build(path: Path, rows: int) -> None:
    conn = db.connect(path)
    span = (LAST_DAY - FIRST_DAY).days
    rng = random.Random(42)
    with conn:
        for name in CATEGORIES:
            conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        ids = [row[0] for row in conn.execute("SELECT id FROM categories")]
        conn.executemany(
            "INSERT INTO expenses (amount_cents, category_id, description, spent_on) "
            "VALUES (?, ?, '', ?)",
            (
                (
                    rng.randint(100, 20000),
                    rng.choice(ids),
                    (FIRST_DAY + timedelta(days=rng.randint(0, span))).isoformat(),
                )
                for _ in range(rows)
            ),
        )
    conn.close()


def median_ms(fn, runs: int) -> float:
    fn()  # warm up the page cache
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def time_queries(path: Path, runs: int) -> dict[str, float]:
    conn = db.connect(path)
    quiet = io.StringIO()

    def full_report():
        with contextlib.redirect_stdout(quiet):
            main(["--db", str(path), "report", "--month", "2026-09"])

    results = {
        "Monthly report totals (one month)": median_ms(
            lambda: db.spending_by_category(conn, *MONTH), runs
        ),
        "List one month, newest 20": median_ms(
            lambda: db.list_expenses(conn, start=MONTH[0], end=MONTH[1], limit=20), runs
        ),
        "12-month trend totals": median_ms(lambda: db.monthly_totals(conn, *YEAR), runs),
        "`expense report` end to end": median_ms(full_report, runs),
    }
    conn.close()
    return results


def query_plan(path: Path) -> str:
    conn = db.connect(path)
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT c.name, SUM(e.amount_cents) FROM expenses AS e "
        "JOIN categories AS c ON c.id = e.category_id "
        "WHERE e.spent_on >= ? AND e.spent_on < ? GROUP BY c.id",
        [MONTH[0].isoformat(), MONTH[1].isoformat()],
    ).fetchall()
    conn.close()
    return "\n".join(f"  {row[3]}" for row in plan)


def main_benchmark() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--runs", type=int, default=15)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "benchmark.db"
        started = time.perf_counter()
        build(path, args.rows)
        print(f"Built {args.rows:,} expenses in {time.perf_counter() - started:.1f} s\n")
        print("Query plan for the monthly report:\n" + query_plan(path) + "\n")

        current = time_queries(path, args.runs)
        drop_index(path, "idx_expenses_month_totals")
        date_index_only = time_queries(path, args.runs)
        drop_index(path, "idx_expenses_spent_on")
        no_index = time_queries(path, args.runs)

    print(f"Median of {args.runs} runs, {args.rows:,} expenses\n")
    print("| Query | No date index | Date index only | Date + covering index | Speedup |")
    print("|---|---:|---:|---:|---:|")
    for name, best in current.items():
        slow = no_index[name]
        print(
            f"| {name} | {slow:.2f} ms | {date_index_only[name]:.2f} ms "
            f"| **{best:.2f} ms** | {slow / best:.1f}x |"
        )


def drop_index(path: Path, name: str) -> None:
    conn = db.connect(path)
    conn.execute(f"DROP INDEX {name}")
    conn.close()


if __name__ == "__main__":
    main_benchmark()
