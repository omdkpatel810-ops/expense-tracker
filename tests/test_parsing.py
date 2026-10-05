from datetime import date

import pytest

from expense_tracker.parsing import (
    month_label,
    month_range,
    months_back,
    parse_category,
    parse_date,
    parse_month,
)

TODAY = date(2026, 9, 30)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("food", "food"),
        ("  Food ", "food"),
        ("Eating   Out", "eating out"),
        ("bills & utilities", "bills & utilities"),
        ("co-op fees", "co-op fees"),
    ],
)
def test_parse_category_normalizes(text, expected):
    assert parse_category(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "food!", "-rent", "a" * 31])
def test_parse_category_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_category(text)


def test_parse_date_keywords():
    assert parse_date("today", today=TODAY) == TODAY
    assert parse_date("Yesterday", today=TODAY) == date(2026, 9, 29)


def test_parse_date_iso():
    assert parse_date("2026-09-01", today=TODAY) == date(2026, 9, 1)


@pytest.mark.parametrize("text", ["2026-10-01", "30/09/2026", "2026-02-30", "soon"])
def test_parse_date_rejects_future_and_bad_dates(text):
    with pytest.raises(ValueError):
        parse_date(text, today=TODAY)


def test_parse_month_returns_half_open_range():
    assert parse_month("2026-09") == (date(2026, 9, 1), date(2026, 10, 1))


def test_parse_month_rolls_over_the_year():
    assert parse_month("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))


def test_month_range_from_any_day():
    assert month_range(date(2026, 10, 4)) == (date(2026, 10, 1), date(2026, 11, 1))
    assert month_range(date(2026, 12, 31)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_months_back_crosses_the_year():
    assert months_back(date(2027, 2, 14), 4) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    ]


def test_month_label():
    assert month_label(date(2026, 10, 4)) == "October 2026"


@pytest.mark.parametrize("text", ["2026-13", "2026-00", "Sept", "2026-9", "26-09"])
def test_parse_month_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_month(text)
