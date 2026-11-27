"""The planning worksheet's definitions and gates, fixed before any company is scored.

Four operating drivers apply to new-business pipeline created after the as-of date (open deals
and actuals are untouched). For each, the company's own past is read one fiscal creation
quarter at a time, and a quarter is used only if it passes that driver's gate. Six eligible
quarters are needed before any historical setting is offered; with fewer there are no bars,
only a reason. The low and high settings are the means of the lower and upper halves of the
eligible observations (the middle one is left out of both halves when the count is odd). A
setting describes something the company has done; it is never called achievable or likely.

Nothing here reads a company: these are the rules, as constants and small pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from .fiscal import FiscalYear

WIN_RATE = "win_rate"
WON_ARR = "won_arr"
PRODUCTIVITY = "productivity"
CYCLE_DAYS = "cycle_days"
DRIVERS = (WIN_RATE, WON_ARR, PRODUCTIVITY, CYCLE_DAYS)

# The gates. A quarter is a complete fiscal quarter in which deals were created, the first
# one starting on or after the first recorded deal. Conversion (win rate), size and timing
# (cycle) need the whole horizon to have passed since the quarter ended, so a quarter whose
# deals could still win is never used.
REQUIRED_QUARTERS = 6
MIN_CREATED_FOR_CONVERSION = 20  # created deals behind a win rate
MIN_WINS_FOR_SIZE_OR_TIMING = 5  # wins behind a mean size or a mean cycle
# Productivity counts what was created, which is final the day a quarter ends, so it needs no
# waiting. It needs enough created deals that one deal is not a large share of the rate (the
# same twenty as a conversion cohort) and some exposure to divide by: a positive count of ramped
# AE-months (or days, where the capacity term is not adopted).
MIN_CREATED_FOR_PRODUCTIVITY = 20

HISTORY_PROMISES_NOTHING = (
    "Historical settings describe what the company has done. They are not forecasts, they are "
    "not called achievable, and nothing here says they will happen again."
)


@dataclass(frozen=True)
class Quarter:
    """One complete fiscal creation quarter, as observed."""

    label: str
    start: date
    end: date
    created: int
    wins: int  # won within the horizon, by the as-of date
    mature: bool  # the horizon has passed since the quarter ended
    exposure: Decimal  # ramped AE-months (days where capacity is not adopted)
    win_rate: Decimal | None
    won_arr: Decimal | None
    cycle_days: Decimal | None
    productivity: Decimal | None


def quarter_label(start: date, fy_start: date) -> str:
    """``Q3FY25``-style name of the fiscal quarter starting on ``start``, for a fiscal calendar
    one of whose years starts on ``fy_start``."""
    fy = FiscalYear(fy_start)
    while start < fy.start:
        fy = FiscalYear(date(fy.start.year - 1, fy.start.month, fy.start.day))
    while start > fy.end:
        fy = fy.next
    return fy.quarter_key(start)


def value_of(q: Quarter, driver: str) -> Decimal | None:
    return {
        WIN_RATE: q.win_rate,
        WON_ARR: q.won_arr,
        PRODUCTIVITY: q.productivity,
        CYCLE_DAYS: q.cycle_days,
    }[driver]


def eligible(q: Quarter, driver: str) -> tuple[bool, str | None]:
    """Whether ``q`` is used for ``driver``, and if not, the reason in words."""
    if driver == PRODUCTIVITY:
        if q.exposure <= 0:
            return False, "nobody was employed to create pipeline"
        if q.created < MIN_CREATED_FOR_PRODUCTIVITY:
            return False, "too few deals were created for a stable rate"
        return True, None
    if not q.mature:
        return False, "its deals have not had the full horizon to win"
    if driver == WIN_RATE:
        if q.created < MIN_CREATED_FOR_CONVERSION:
            return False, "too few deals were created for a stable win rate"
        return True, None
    if q.wins < MIN_WINS_FOR_SIZE_OR_TIMING:
        return False, "too few wins for a stable mean"
    return True, None


def halves(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Means of the lower and the upper half of ``values``; with an odd count the middle value
    belongs to neither half. At least two values."""
    ordered = sorted(values)
    n = len(ordered) // 2
    if n == 0:
        raise ValueError("halves need at least two values")
    return sum(ordered[:n], Decimal(0)) / n, sum(ordered[-n:], Decimal(0)) / n


@dataclass(frozen=True)
class Settings:
    low: Decimal
    high: Decimal
    minimum: Decimal
    maximum: Decimal
    count: int


def historical_settings(values: list[Decimal]) -> Settings | None:
    """The offered settings, or None when fewer than ``REQUIRED_QUARTERS`` values qualify."""
    if len(values) < REQUIRED_QUARTERS:
        return None
    low, high = halves(values)
    return Settings(low, high, min(values), max(values), len(values))


def scaled_days(samples: tuple[int, ...], scale: Fraction) -> tuple[int, ...]:
    """Each win-time sample multiplied by ``scale`` and rounded up to whole days."""
    return tuple(-(-(d * scale.numerator) // scale.denominator) for d in samples)


def boundary_at_or_after(samples: tuple[int, ...], scale: Fraction) -> Fraction:
    """The smallest scale of at least ``scale`` at which a rounded win time changes. A sample of
    ``d`` days rounds to ``k`` days for every scale in ((k - 1) / d, k / d], so the changes are
    at the scales ``k / d``, and at each the faster timing still holds."""
    return min(
        Fraction(-(-(scale.numerator * d) // scale.denominator), d)
        for d in set(samples)
        if d > 0
    )


def boundary_at_or_before(samples: tuple[int, ...], scale: Fraction) -> Fraction:
    """The largest scale of at most ``scale`` at which a rounded win time changes."""
    return max(
        Fraction((scale.numerator * d) // scale.denominator, d)
        for d in set(samples)
        if d > 0
    )
