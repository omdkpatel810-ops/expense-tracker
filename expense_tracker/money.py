"""Convert between what people type ("12.50") and what we store (1250 cents).

Why cents? Floats can't store most decimal amounts exactly:
0.1 + 0.2 == 0.30000000000000004 in Python. Add up thousands of float
prices and the total slowly drifts. Integers never drift, so every amount
is stored as a whole number of cents and only turned back into dollars
when it's printed.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_DOLLARS = Decimal("1000000")
ONE_CENT = Decimal("0.01")


def parse_amount(text: str) -> int:
    """Turn input like "12.5" or "$1,299.99" into cents (1250, 129999).

    Raises ValueError with a message the user can act on.
    """
    cleaned = text.strip().replace("$", "").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"'{text}' is not an amount. Use a number like 12.50.") from None

    if not value.is_finite():
        raise ValueError(f"'{text}' is not an amount. Use a number like 12.50.")
    if value <= 0:
        raise ValueError("Amount must be more than $0.00.")
    if value > MAX_DOLLARS:
        raise ValueError("Amount must be $1,000,000.00 or less.")
    if value != value.quantize(ONE_CENT):
        raise ValueError("Amount can have at most 2 decimal places, like 12.99.")

    return int(value * 100)


def format_cents(cents: int) -> str:
    """Format 129999 as "$1,299.99"."""
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{remainder:02d}"
