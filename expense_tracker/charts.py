"""Draw spending charts as PNG images with matplotlib.

Charts use matplotlib's Figure class directly instead of pyplot, so there is
no global state and no GUI window: drawing works the same in a terminal, in
tests and on a server.

Design rules, so every chart reads the same way:
  - One series color (blue). Amber and red only ever mean "close to limit"
    and "over budget", and always come with a text label, so color is
    never the only signal.
  - Thin bars, hairline gridlines and quiet axes, so the data is the
    loudest thing on the page.
  - Labels are measured before saving and the axis is widened to fit them,
    so a label is never cut off at the edge of the image.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from expense_tracker.money import format_cents
from expense_tracker.parsing import MONTH_NAMES, month_label
from expense_tracker.reports import CLOSE, OVER, CategoryReport

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES = "#2a78d6"
TRACK = "#cde2fb"  # a lighter step of the series blue: the part of the budget not yet spent
WARNING = "#fab219"
CRITICAL = "#d03b3b"

STATUS_FILL = {CLOSE: WARNING, OVER: CRITICAL}
STATUS_TAG = {CLOSE: "⚠ close to limit", OVER: "✕ over budget"}

DPI = 200
BAR_THICKNESS = 0.42  # fraction of each row; the rest is breathing room
LABEL_GAP_POINTS = 8

dollars = FuncFormatter(lambda value, _position: f"${value:,.0f}")


def budget_chart(rows: list[CategoryReport], month: str) -> Figure:
    """One horizontal bar per category, drawn like a progress meter.

    The light track is the monthly budget, the fill is what's been spent and a
    thin tick marks where the budget ends, so an overspend shows as a fill
    that runs past the tick. Categories without a budget get a fill only.
    """
    if not rows:
        raise ValueError("There's nothing to chart for this month.")

    fig, ax = _new_chart(width=8, height=1.6 + 0.48 * len(rows))
    _title(
        ax,
        f"Spending vs budget · {month}",
        "Fill is what you've spent. Light track and tick mark the monthly budget.",
    )

    positions = list(range(len(rows)))[::-1]  # first row (biggest spending) at the top
    labels = []
    for y, row in zip(positions, rows):
        spent = row.spent_cents / 100
        limit = None if row.limit_cents is None else row.limit_cents / 100
        if limit is not None:
            ax.barh(y, limit, height=BAR_THICKNESS, color=TRACK, zorder=1)
        ax.barh(y, spent, height=BAR_THICKNESS, color=STATUS_FILL.get(row.status, SERIES), zorder=2)
        if limit is not None:
            ax.plot([limit, limit], [y - 0.3, y + 0.3], color=INK_SECONDARY, linewidth=1.2, zorder=3)

        end = max(spent, limit or 0)
        labels.append(
            ax.annotate(
                _budget_label(row),
                xy=(end, y),
                xytext=(LABEL_GAP_POINTS, 0),
                textcoords="offset points",
                va="center",
                fontsize=9,
                color=INK if row.needs_alert else INK_SECONDARY,
                fontweight="bold" if row.needs_alert else "normal",
                parse_math=False,  # "$5 of $10" must not be read as a math formula
            )
        )

    ax.set_yticks(positions, labels=[row.category for row in rows])
    ax.xaxis.set_major_formatter(dollars)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
    ax.set_ylim(-0.6, len(rows) - 0.4)
    _style_axes(ax, value_axis="x")
    _fit_labels_horizontally(fig, ax, labels)
    return fig


def trend_chart(
    months: list[date],
    totals_cents: list[int],
    category: str | None = None,
    last_month_in_progress: bool = False,
) -> Figure:
    """One column per month. Only the latest month and the highest month are labeled."""
    if len(months) != len(totals_cents) or not months:
        raise ValueError("months and totals must be the same, non-empty length")

    fig, ax = _new_chart(width=8, height=4.2)
    what = f"Monthly spending on {category}" if category else "Monthly spending"
    span = f"{month_label(months[0])} to {month_label(months[-1])}"
    note = f" · {month_label(months[-1])} is still in progress" if last_month_in_progress else ""
    _title(ax, what, span + note)

    values = [cents / 100 for cents in totals_cents]
    xs = list(range(len(months)))
    ax.bar(xs, values, width=0.24, color=SERIES, zorder=2)  # thin columns, air between them

    peak = max(range(len(values)), key=lambda i: values[i])
    for i in sorted({peak, len(values) - 1}):
        text = format_cents(totals_cents[i])
        if i == len(values) - 1 and last_month_in_progress:
            text += " so far"
        ax.annotate(
            text,
            xy=(i, values[i]),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK,
            parse_math=False,
        )

    ax.set_xticks(xs, labels=[_month_tick(m, first=(i == 0)) for i, m in enumerate(months)])
    ax.yaxis.set_major_formatter(dollars)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
    ax.set_ylim(0, max(max(values), 1) * 1.18)  # headroom for the value labels
    ax.set_xlim(-0.6, len(months) - 0.4)
    _style_axes(ax, value_axis="y")
    return fig


def save(fig: Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    return path


def _budget_label(row: CategoryReport) -> str:
    if row.limit_cents is None:
        return f"{format_cents(row.spent_cents)} · no budget"
    text = f"{format_cents(row.spent_cents)} of {format_cents(row.limit_cents)} · {row.percent_used}%"
    if row.status in STATUS_TAG:
        text += f"   {STATUS_TAG[row.status]}"
    return text


def _month_tick(month: date, first: bool) -> str:
    short = MONTH_NAMES[month.month - 1][:3]
    return f"{short}\n{month.year}" if first or month.month == 1 else short


def _new_chart(width: float, height: float):
    fig = Figure(figsize=(width, height), dpi=DPI, facecolor=SURFACE, layout="constrained")
    FigureCanvasAgg(fig)  # attach a renderer so labels can be measured before saving
    ax = fig.add_subplot()
    ax.set_facecolor(SURFACE)
    return fig, ax


def _title(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", pad=24, fontsize=13, fontweight="bold", color=INK, parse_math=False)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom", parse_math=False)


def _style_axes(ax, value_axis: str) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.spines["bottom"].set_linewidth(1)
    ax.tick_params(length=0, labelsize=9, colors=MUTED)
    ax.tick_params(axis="x" if value_axis == "y" else "y", labelcolor=INK_SECONDARY)
    ax.grid(axis=value_axis, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _fit_labels_horizontally(fig: Figure, ax, labels) -> None:
    """Widen the x axis until every end-of-bar label fits inside the chart.

    A label's width is fixed in pixels, but its starting point moves as the
    axis is rescaled, so solve for the axis maximum X that makes the widest
    label end inside the plot: end/X * W + label_width <= W.
    """
    renderer = fig.canvas.get_renderer()
    for _ in range(2):  # a second pass settles any layout shift from the new tick labels
        fig.draw_without_rendering()  # runs the layout so axes sizes are final
        plot_width = ax.get_window_extent(renderer).width * 0.98
        needed = 0.0
        for label in labels:
            bar_end = label.xy[0]
            label_px = label.get_window_extent(renderer).width + LABEL_GAP_POINTS * fig.dpi / 72
            if label_px >= plot_width:
                continue
            needed = max(needed, bar_end * plot_width / (plot_width - label_px))
        ax.set_xlim(0, max(needed, 1))
