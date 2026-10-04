import pytest

from expense_tracker.reports import (
    CLOSE,
    LIMIT_REACHED,
    NO_BUDGET,
    ON_TRACK,
    OVER,
    CategoryReport,
    alert_message,
    build_report,
)

BUDGET = 30000  # $300.00


@pytest.mark.parametrize(
    "spent, status",
    [
        (0, ON_TRACK),
        (23999, ON_TRACK),  # 79.99%: still under the warning line
        (24000, CLOSE),  # exactly 80%
        (29999, CLOSE),
        (30000, LIMIT_REACHED),
        (30001, OVER),
    ],
)
def test_status_boundaries(spent, status):
    assert CategoryReport("food", spent, BUDGET).status == status


def test_no_budget():
    row = CategoryReport("coffee", 425, None)

    assert row.status == NO_BUDGET
    assert row.percent_used is None
    assert row.left_cents is None
    assert not row.needs_alert


def test_percent_used_rounds_down():
    assert CategoryReport("food", 23999, BUDGET).percent_used == 79
    assert CategoryReport("food", 45000, BUDGET).percent_used == 150


def test_left_is_negative_when_over():
    assert CategoryReport("food", 31240, BUDGET).left_cents == -1240


@pytest.mark.parametrize(
    "spent, alert",
    [(23999, False), (24000, True), (29999, True), (30000, False), (30001, True)],
)
def test_needs_alert(spent, alert):
    assert CategoryReport("food", spent, BUDGET).needs_alert is alert


def test_build_report_includes_untouched_budgets_and_sorts_by_spending():
    rows = build_report(
        spending={"food": 24600, "coffee": 425, "rent": 115000},
        budgets={"food": 30000, "rent": 115000, "travel": 50000},
    )

    assert [(r.category, r.spent_cents, r.limit_cents) for r in rows] == [
        ("rent", 115000, 115000),
        ("food", 24600, 30000),
        ("coffee", 425, None),
        ("travel", 0, 50000),
    ]


def test_build_report_empty():
    assert build_report({}, {}) == []


def test_alert_messages():
    month = "October 2026"

    assert alert_message(CategoryReport("food", 24600, BUDGET), month) == (
        "food is at 82% of its $300.00 budget for October 2026, $54.00 left."
    )
    assert alert_message(CategoryReport("food", 30000, BUDGET), month) == (
        "food has used all of its $300.00 budget for October 2026."
    )
    assert alert_message(CategoryReport("food", 31240, BUDGET), month) == (
        "food is $12.40 over its $300.00 budget for October 2026 ($312.40 spent)."
    )
    assert alert_message(CategoryReport("food", 1000, BUDGET), month) == ""
    assert alert_message(CategoryReport("coffee", 1000, None), month) == ""
