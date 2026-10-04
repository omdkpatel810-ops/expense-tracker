"""Monthly report logic: how much of each budget is used, and what needs a warning.

Everything here is a pure function of numbers passed in. Nothing reads the
database or prints, so the rules are easy to test and reuse.
All money is integer cents, so percentages are worked out with integer math
and there are no float rounding surprises at the 80% and 100% boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from expense_tracker.money import format_cents

WARN_AT_PERCENT = 80

ON_TRACK = "on track"
CLOSE = "close to limit"
LIMIT_REACHED = "limit reached"
OVER = "over budget"
NO_BUDGET = "no budget"

# Landing exactly on the limit isn't an alert: fixed bills like rent are
# budgeted at their exact amount, and warning about them every month
# would teach people to ignore warnings.
ALERT_STATUSES = (OVER, CLOSE)


@dataclass(frozen=True)
class CategoryReport:
    category: str
    spent_cents: int
    limit_cents: int | None  # None when the category has no budget

    @property
    def status(self) -> str:
        if self.limit_cents is None:
            return NO_BUDGET
        if self.spent_cents > self.limit_cents:
            return OVER
        if self.spent_cents == self.limit_cents:
            return LIMIT_REACHED
        if self.spent_cents * 100 >= self.limit_cents * WARN_AT_PERCENT:
            return CLOSE
        return ON_TRACK

    @property
    def percent_used(self) -> int | None:
        """Whole percent of the budget used, rounded down (79.99% shows as 79%)."""
        if self.limit_cents is None:
            return None
        return self.spent_cents * 100 // self.limit_cents

    @property
    def left_cents(self) -> int | None:
        """Money left in the budget. Negative when over budget."""
        if self.limit_cents is None:
            return None
        return self.limit_cents - self.spent_cents

    @property
    def needs_alert(self) -> bool:
        return self.status in ALERT_STATUSES


def build_report(spending: dict[str, int], budgets: dict[str, int]) -> list[CategoryReport]:
    """Combine one month's spending with the budgets, biggest spending first.

    A category shows up if it had spending this month or has a budget, so a
    budget you haven't touched yet still appears with $0.00 spent.
    """
    names = set(spending) | set(budgets)
    rows = [CategoryReport(name, spending.get(name, 0), budgets.get(name)) for name in names]
    return sorted(rows, key=lambda row: (-row.spent_cents, row.category))


def alert_message(row: CategoryReport, month: str) -> str:
    """One sentence explaining a budget alert, or "" if the row doesn't need one."""
    if row.limit_cents is None:
        return ""
    limit = format_cents(row.limit_cents)
    if row.status == OVER:
        return (
            f"{row.category} is {format_cents(-row.left_cents)} over its {limit} budget "
            f"for {month} ({format_cents(row.spent_cents)} spent)."
        )
    if row.status == LIMIT_REACHED:
        return f"{row.category} has used all of its {limit} budget for {month}."
    if row.status == CLOSE:
        return (
            f"{row.category} is at {row.percent_used}% of its {limit} budget for {month}, "
            f"{format_cents(row.left_cents)} left."
        )
    return ""
