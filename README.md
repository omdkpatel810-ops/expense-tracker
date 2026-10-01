# Expense Tracker

![tests](https://github.com/omdkpatel810-ops/expense-tracker/actions/workflows/tests.yml/badge.svg)

Track your spending from the command line. Expenses are saved in a local SQLite database, so your data stays on your machine and survives restarts.

```text
$ expense add 1150 rent "October rent"
Added #1: $1,150.00 · rent · 2026-09-30 · October rent

$ expense list
ID  Date        Category      Amount  Description
--  ----------  ---------  ---------  ---------------
 1  2026-09-30  rent       $1,150.00  October rent
 4  2026-09-29  coffee         $4.25
 2  2026-09-29  food          $12.50  Lunch at Subway
 3  2026-09-15  transit      $113.00  U-Pass top-up
 5  2026-08-28  groceries     $64.37  Superstore run

Total for 5 expenses: $1,344.12
```

## Features

- **Add expenses** with an amount, category, optional description and date (`today`, `yesterday` or `YYYY-MM-DD`)
- **List expenses** newest first, filtered by month and/or category, with a running total
- **Categories** are normalized, so `Food`, `food` and ` food ` are the same category
- **Clear errors** for bad input, like `error: Amount can have at most 2 decimal places, like 12.99.`

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/omdkpatel810-ops/expense-tracker.git
cd expense-tracker
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
expense --help
```

## Usage

```bash
expense add 12.50 food "Lunch at Subway"              # dated today
expense add 4.25 coffee --date yesterday
expense add 64.37 groceries "Superstore" --date 2026-08-28

expense list                                         # latest 20
expense list --month 2026-09                         # all of September
expense list --month 2026-09 --category food --limit 50
expense categories
```

Data is stored in `~/.expense_tracker/expenses.db`. Set `EXPENSE_DB=/path/to/file.db` or pass `--db` to use a different file.

## How it works

```text
expense_tracker/
  cli.py      reads command-line arguments, prints tables
  parsing.py  checks categories, dates and months typed by the user
  money.py    converts "12.50" to 1250 cents and back
  db.py       the only module that runs SQL
tests/        one test file per module (66 tests)
```

**Money is stored as integer cents.** Floats can't represent most decimal amounts exactly (`0.1 + 0.2 == 0.30000000000000004`), so totals drift as you add up many prices. Whole numbers of cents never drift.

**The schema protects the data, not just the app.** `CHECK` constraints reject a zero or negative amount even if a bug slips past the input checks.

```sql
CREATE TABLE expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL CHECK (length(category) > 0),
    description  TEXT    NOT NULL DEFAULT '',
    spent_on     TEXT    NOT NULL,  -- ISO date, so text order = date order
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_expenses_spent_on ON expenses (spent_on);
CREATE INDEX idx_expenses_category ON expenses (category);
```

**Month filters use a half-open range.** `--month 2026-09` becomes `spent_on >= '2026-09-01' AND spent_on < '2026-10-01'`, which is correct for every month length and lets SQLite use the date index.

**All queries use `?` parameters**, never string formatting, which prevents SQL injection.

## Running the tests

```bash
python -m pytest -v
```

Tests also run automatically on every push with GitHub Actions, on Python 3.10 and 3.13.

## Roadmap

- [x] Add, list and categorize expenses from the command line
- [ ] Delete and edit expenses
- [ ] Normalized schema: categories table, budgets table, migrations
- [ ] Monthly reports and budget alerts
- [ ] Spending charts with matplotlib
