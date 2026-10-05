"""Turn what people type on the command line into clean, checked values.

Every function here either returns a valid value or raises ValueError with
a message that tells the user how to fix their input.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

MAX_CATEGORY_LENGTH = 30
CATEGORY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 &-]*$")
MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def parse_category(text: str) -> str:
    """Normalize a category so "  Eating   Out " and "eating out" match."""
    category = " ".join(text.split()).lower()
    if not category:
        raise ValueError("Category can't be empty. Try something like food or rent.")
    if len(category) > MAX_CATEGORY_LENGTH:
        raise ValueError(f"Category must be {MAX_CATEGORY_LENGTH} characters or fewer.")
    if not CATEGORY_PATTERN.match(category):
        raise ValueError("Category can only use letters, numbers, spaces, '-' and '&'.")
    return category


def parse_date(text: str, today: date | None = None) -> date:
    """Accept "today", "yesterday" or a YYYY-MM-DD date that isn't in the future.

    `today` can be passed in so tests don't depend on the real clock.
    """
    today = today or date.today()
    word = text.strip().lower()
    if word == "today":
        return today
    if word == "yesterday":
        return today - timedelta(days=1)

    try:
        parsed = date.fromisoformat(word)
    except ValueError:
        raise ValueError(f"'{text}' is not a date. Use YYYY-MM-DD, 'today' or 'yesterday'.") from None
    if parsed > today:
        raise ValueError("Date can't be in the future.")
    return parsed


def parse_month(text: str) -> tuple[date, date]:
    """Turn "2026-09" into (2026-09-01, 2026-10-01): start included, end excluded.

    A half-open range like this works for every month length and lets the
    database use its index on the date column.
    """
    match = MONTH_PATTERN.match(text.strip())
    if not match:
        raise ValueError(f"'{text}' is not a month. Use YYYY-MM, like 2026-09.")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"'{text}' is not a month. Months go from 01 to 12.")
    return month_range(date(year, month, 1))


def month_range(day: date) -> tuple[date, date]:
    """Return (first day of day's month, first day of the next month)."""
    start = day.replace(day=1)
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, end


def months_back(day: date, count: int) -> list[date]:
    """First days of the `count` months ending with day's month, oldest first.

    months_back(2026-10-05, 3) -> [2026-08-01, 2026-09-01, 2026-10-01]
    """
    index = day.year * 12 + (day.month - 1)  # months since year 0, so wrapping years is easy
    return [date(i // 12, i % 12 + 1, 1) for i in range(index - count + 1, index + 1)]


def month_label(day: date) -> str:
    """Format a date's month for people, like "October 2026"."""
    return f"{MONTH_NAMES[day.month - 1]} {day.year}"
