import pytest

from expense_tracker.money import format_cents, parse_amount


@pytest.mark.parametrize(
    "text, cents",
    [
        ("12.50", 1250),
        ("12.5", 1250),
        ("12", 1200),
        ("0.01", 1),
        ("$1,299.99", 129999),
        ("  7.25  ", 725),
        ("12.500", 1250),
        ("1000000", 100_000_000),
    ],
)
def test_parse_amount_accepts_valid_input(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize(
    "text",
    ["", "abc", "0", "0.00", "-5", "12.345", "nan", "inf", "1000000.01", "1.2.3"],
)
def test_parse_amount_rejects_invalid_input(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_adding_amounts_does_not_drift():
    # With floats, ten 0.10s add up to 0.9999999999999999, not 1.0.
    total = sum(parse_amount("0.10") for _ in range(10))
    assert total == 100


@pytest.mark.parametrize(
    "cents, text",
    [(0, "$0.00"), (5, "$0.05"), (1250, "$12.50"), (129999, "$1,299.99"), (-300, "-$3.00")],
)
def test_format_cents(cents, text):
    assert format_cents(cents) == text
