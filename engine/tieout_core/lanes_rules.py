"""The swimlane grid's definitions, gates and status rules, fixed before any company is scored.

A lane is a row of eight columns, each with an actual, a forecast and a goal. This module holds
what is the same for every company: the columns and what their goals are called, the thresholds
that make a cell "behind", and the minimum denominators below which a ratio has no status. The
core writes the status of every cell; the screen does no arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

BEHIND_AT_OR_BELOW = Decimal("0.95")  # forecast over goal; behind at or below this
BEHIND_AT_OR_ABOVE = Decimal("1.05")  # cycle days are reversed: longer is worse
RATIO_PLACES = Decimal("0.0001")
COUNT = Decimal("0.0001")  # expected deals are written to four places

# The one place a "too small to judge" count is defined. A win rate needs this many deals in its
# creation cohort; an average won size or a cycle needs this many wins behind it.
MIN_COHORT = 20
MIN_WINS = 5
# A segment's own deal size is used only where this many observations stand behind it; below
# that the pooled figure stands in, and the row says so.
MIN_SEGMENT_WINS = 10
MIN_SEGMENT_CREATED = 10

UNASSIGNED = "unassigned"

BEHIND, ON_TRACK, NONE = "behind", "on_track", "none"
REASONS = {
    "no_goal": "There is no goal here, or it is zero, so there is nothing to compare with.",
    "not_modeled": "This figure is not modeled for this period.",
    "too_few": "Too few observations stand behind this ratio for a stable comparison.",
    "vacuous": "For a period that has begun the forecast is the recorded fact, which is also the "
    "basis the goal was frozen from, so the comparison carries no information.",
}


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    unit: str  # deals, ARR, rate or days
    goal_label: str
    places: int  # decimal places a figure in this column is written to
    compared: str = "forecast"  # which figure is held against the goal
    reversed: bool = False  # a larger figure is worse
    minimum: int | None = None  # smallest denominator that gets a status
    judged: bool = True  # False: no status is ever given, and the reason says why


COLUMNS = (
    Column("open", "Open at start", "deals", "frozen opening basis", 0, judged=False),
    Column("created", "Created deals", "deals", "derived requirement", 4),
    Column("created_arr", "Created pipeline", "ARR", "derived requirement", 2),
    Column(
        "win_rate",
        "Win rate, 365 days",
        "rate",
        "plan-start assumption",
        4,
        "actual",
        False,
        MIN_COHORT,
    ),
    Column(
        "cycle",
        "Cycle",
        "days",
        "model-implied benchmark",
        2,
        "forecast",
        True,
        MIN_WINS,
    ),
    Column("won", "Won deals", "deals", "target-equivalent wins", 4),
    Column(
        "avg_won_arr",
        "Average won ARR",
        "ARR",
        "model-implied benchmark",
        2,
        "forecast",
        False,
        MIN_WINS,
    ),
    Column("bookings", "Bookings", "ARR", "entered target", 2),
)
COLUMN = {c.key: c for c in COLUMNS}
RATIO_COLUMNS = ("win_rate", "cycle", "avg_won_arr")


def status(
    column: Column,
    compared: Decimal | None,
    goal: Decimal | None,
    denominator: int | Decimal | None = None,
) -> tuple[str, str | None, Decimal | None]:
    """(status, why there is none, figure over goal) for one cell."""
    if not column.judged:
        return NONE, "vacuous", None
    if (
        column.minimum is not None
        and denominator is not None
        and denominator < column.minimum
    ):
        return NONE, "too_few", None
    if compared is None:
        return NONE, "not_modeled", None
    if not goal:
        return NONE, "no_goal", None
    ratio = compared / goal  # judged exactly; only the figure shown is rounded
    behind = (
        ratio >= BEHIND_AT_OR_ABOVE if column.reversed else ratio <= BEHIND_AT_OR_BELOW
    )
    return (BEHIND if behind else ON_TRACK), None, ratio.quantize(RATIO_PLACES)


def segment_key(segment: str) -> str:
    """A deal's or a person's segment as a lane's key; a blank one is the unassigned lane."""
    return segment or UNASSIGNED
