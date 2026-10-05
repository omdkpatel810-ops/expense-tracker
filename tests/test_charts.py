from datetime import date

import matplotlib.colors as mcolors
import pytest

from expense_tracker import charts
from expense_tracker.reports import build_report

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def october_rows():
    return build_report(
        spending={"rent": 115000, "food": 25275, "fun": 9350, "coffee": 425},
        budgets={"rent": 115000, "food": 30000, "fun": 8000, "travel": 50000},
    )


def bar_colors(ax):
    """Fill color of every bar, from bottom of the drawing order to top."""
    return [mcolors.to_hex(patch.get_facecolor()) for patch in ax.patches]


def test_budget_chart_puts_biggest_spending_at_the_top(october_rows):
    ax = charts.budget_chart(october_rows, "October 2026").axes[0]

    ticks = sorted(ax.get_yticklabels(), key=lambda t: t.get_position()[1], reverse=True)
    assert [t.get_text() for t in ticks] == ["rent", "food", "fun", "coffee", "travel"]


def test_budget_chart_colors_mean_status(october_rows):
    ax = charts.budget_chart(october_rows, "October 2026").axes[0]
    colors = bar_colors(ax)

    # Budgeted rows draw a track and then a fill; coffee (no budget) draws only a fill.
    assert colors == [
        charts.TRACK, charts.SERIES,  # rent: exactly on budget
        charts.TRACK, charts.WARNING,  # food: 84%
        charts.TRACK, charts.CRITICAL,  # fun: over
        charts.SERIES,  # coffee: no budget
        charts.TRACK, charts.SERIES,  # travel: nothing spent yet
    ]


def test_budget_chart_never_uses_color_alone(october_rows):
    ax = charts.budget_chart(october_rows, "October 2026").axes[0]
    labels = [text.get_text() for text in ax.texts]

    assert "$252.75 of $300.00 · 84%   ⚠ close to limit" in labels
    assert "$93.50 of $80.00 · 116%   ✕ over budget" in labels
    assert "$4.25 · no budget" in labels


def test_budget_chart_labels_fit_inside_the_plot(october_rows):
    fig = charts.budget_chart(october_rows, "October 2026")
    ax = fig.axes[0]
    renderer = fig.canvas.get_renderer()
    fig.draw_without_rendering()

    plot_right = ax.get_window_extent(renderer).x1
    for label in ax.texts:
        if label.get_text().startswith("$"):
            assert label.get_window_extent(renderer).x1 <= plot_right + 1, label.get_text()


def test_budget_chart_needs_rows():
    with pytest.raises(ValueError):
        charts.budget_chart([], "October 2026")


def test_trend_chart_labels_only_the_peak_and_latest_month():
    months = [date(2026, m, 1) for m in range(5, 11)]
    totals = [148230, 162410, 139875, 171050, 158600, 161350]

    ax = charts.trend_chart(months, totals, last_month_in_progress=True).axes[0]

    assert len(ax.patches) == 6
    assert [t.get_text() for t in ax.texts if t.get_text().startswith("$")] == [
        "$1,710.50",
        "$1,613.50 so far",
    ]
    assert [t.get_text() for t in ax.get_xticklabels()] == [
        "May\n2026", "Jun", "Jul", "Aug", "Sep", "Oct",
    ]


def test_trend_chart_shows_year_on_january():
    months = [date(2026, 12, 1), date(2027, 1, 1)]
    ax = charts.trend_chart(months, [100, 200]).axes[0]

    assert [t.get_text() for t in ax.get_xticklabels()] == ["Dec\n2026", "Jan\n2027"]


def test_trend_chart_title_names_the_category():
    ax = charts.trend_chart([date(2026, 10, 1)], [500], category="food").axes[0]

    assert ax.get_title(loc="left") == "Monthly spending on food"


def test_dollar_signs_are_not_read_as_math(october_rows):
    ax = charts.budget_chart(october_rows, "October 2026").axes[0]

    assert all(not text.get_parse_math() for text in ax.texts)


def test_save_writes_a_png(tmp_path, october_rows):
    path = charts.save(charts.budget_chart(october_rows, "October 2026"), tmp_path / "out" / "c.png")

    data = path.read_bytes()
    assert data.startswith(PNG_SIGNATURE)
    assert len(data) > 10_000
