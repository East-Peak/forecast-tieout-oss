"""The four operating drivers as pure overrides of the fitted records, the probe that measures
them around the scenario in force, and the solves behind "needed alone".

An override takes a ``Ground`` and returns an adjusted copy; nothing is changed in place, so
one prepared company serves any number of worksheets, and the same functions can later carry a
visitor's own assumption into a plan. Only pipeline created after the as-of date feels a driver:
open deals and actuals are read from the same fitted records as before.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction

from .actions import Ground, Scenario
from .fit import Timing
from .forecast import Forecast, Inflow
from .plan import NEXT_12, REST_OF_FY
from .roster import Member
from .worksheet_rules import CYCLE_DAYS, PRODUCTIVITY, WIN_RATE, WON_ARR, scaled_days

ZERO = Decimal(0)
ONE = Decimal(1)

SOLVES = "solves"
CANNOT = "cannot_close_alone"
COVERED = "already_at_or_ahead"
BOUNDED_AT_ONE = "bounded_at_one"
NO_EFFECT = "no_effect_in_the_year"
ZERO_DAYS_SHORT = "short_even_at_zero_days"


# ------------------------------------------------------------------ the overrides


def timing_mean(t: Timing) -> Decimal:
    """Mean days of a win-time distribution: each sample once, or by its weight."""
    weights = t.weights if t.weights is not None else (ONE,) * len(t.samples)
    total = sum(weights, ZERO)
    return sum((Decimal(d) * w for d, w in zip(t.samples, weights)), ZERO) / total


def current_value(g: Ground, driver: str) -> Decimal:
    new = g.model.new_pipeline
    if driver == WIN_RATE:
        return new.win_rate
    if driver == WON_ARR:
        return new.mean_won_arr
    if driver == PRODUCTIVITY:
        return g.cap.fit.rate if g.cap.adopted else new.created_per_day
    return timing_mean(new.timing)


def _with_new(g: Ground, **changes) -> Ground:
    return replace(
        g, model=replace(g.model, new_pipeline=replace(g.model.new_pipeline, **changes))
    )


def with_win_rate(g: Ground, value: Decimal) -> Ground:
    """Win probability of every deal created from now on, clipped to zero and one."""
    return _with_new(g, win_rate=min(max(value, ZERO), ONE))


def with_won_arr(g: Ground, value: Decimal) -> Ground:
    """Mean won ARR per new win; creation counts and the program dollars-to-deals conversion
    (which use the mean created amount) are unchanged."""
    return _with_new(g, mean_won_arr=value)


def with_productivity(g: Ground, value: Decimal) -> Ground:
    """Created deals per ramped AE-month where the capacity term is in use, else organic deals
    created per day."""
    if g.cap.adopted:
        return replace(g, cap=replace(g.cap, fit=replace(g.cap.fit, rate=value)))
    return _with_new(g, created_per_day=value)


def with_cycle_scale(g: Ground, scale: Fraction) -> Ground:
    """Each win-time sample multiplied by ``scale`` and rounded up to whole days; weights,
    probability and size are unchanged."""
    timing = g.model.new_pipeline.timing
    return _with_new(
        g, timing=replace(timing, samples=scaled_days(timing.samples, scale))
    )


def with_setting(g: Ground, driver: str, value: Decimal) -> Ground:
    """``g`` with ``driver`` at ``value`` (cycle: the mean days wanted, reached by scaling)."""
    if driver == WIN_RATE:
        return with_win_rate(g, value)
    if driver == WON_ARR:
        return with_won_arr(g, value)
    if driver == PRODUCTIVITY:
        return with_productivity(g, value)
    return with_cycle_scale(g, Fraction(value) / Fraction(current_value(g, CYCLE_DAYS)))


def realized_cycle(g: Ground, scale: Fraction) -> Decimal:
    """The mean win time after ``scale`` and the rounding up."""
    return timing_mean(with_cycle_scale(g, scale).model.new_pipeline.timing)


# ------------------------------------------------------------------ the probe


class Probe:
    """Forecasts of one scenario in force (a roster with planned hires and program pipeline) as
    its drivers are moved. Figures are what the report shows: a shown total is the sum of its
    months each to the cent; the fiscal-year figure is exact, as the existing solves use it."""

    def __init__(
        self, g: Ground, hires: Sequence[Member] = (), inflows: Sequence[Inflow] = ()
    ) -> None:
        self.g = g
        self.hires, self.inflows = tuple(hires), tuple(inflows)
        self.scenario = Scenario(g)
        self.base = self.scenario.forecast(self.hires, self.inflows)
        self._shown_base = self.shown(self.base)

    def forecast(self, adjusted: Ground) -> Forecast:
        return Scenario(adjusted).forecast(self.hires, self.inflows)

    def shown(self, f: Forecast) -> dict[str, Decimal]:
        return self.scenario.bookings(f)

    def fiscal_year(self, f: Forecast) -> Decimal:
        return self.scenario.fiscal_year(f)

    def change(self, f: Forecast) -> dict[str, Decimal]:
        now = self.shown(f)
        return {w: now[w] - self._shown_base[w] for w in (REST_OF_FY, NEXT_12)}


# ------------------------------------------------------------------ the solves


@dataclass(frozen=True)
class Needed:
    outcome: str  # SOLVES, CANNOT or COVERED
    value: Decimal | None  # setting at which ``achieved`` is reached
    achieved: Decimal  # fiscal-year bookings expected at ``value``
    reason: str | None = None
    overshoot: Decimal | None = (
        None  # a stepped solve: what it reaches beyond the target
    )
    scale: Fraction | None = (
        None  # a cycle solve: the largest scale that reaches the target
    )


def solve_linear(
    fy_at: Callable[[Decimal], Decimal],
    current: Decimal,
    target: Decimal,
    upper: Decimal | None,
) -> Needed:
    """The value of a driver, alone, that takes fiscal-year bookings to ``target``. Bookings
    are affine in each of these drivers, so one probe fixes the line; the answer is then put
    back through the forward function. ``upper`` bounds the value (a win rate cannot pass one)."""
    base = fy_at(current)
    if base >= target:
        return Needed(COVERED, current, base)
    if upper is not None and current >= upper:
        return Needed(CANNOT, current, base, BOUNDED_AT_ONE)
    probe = upper if upper is not None else (current * 2 if current > 0 else ONE)
    at_probe = fy_at(probe)
    slope = (at_probe - base) / (probe - current)
    if slope <= 0:
        return Needed(CANNOT, current, base, NO_EFFECT)
    needed = current + (target - base) / slope
    if upper is not None and needed > upper:
        return Needed(CANNOT, upper, at_probe, BOUNDED_AT_ONE)
    return Needed(SOLVES, needed, fy_at(needed))


def solve_cycle(
    fy_at_scale: Callable[[Fraction], Decimal], steps: list[Fraction], target: Decimal
) -> Needed:
    """The largest scale of the win-time samples that takes fiscal-year bookings to ``target``.
    Rounding up to whole days makes bookings a step function of the scale, so there is no exact
    root: the answer is the largest step that reaches the target, with what it overshoots by.
    ``steps`` are every scale at which a rounded day changes, ascending from zero to one."""
    base = fy_at_scale(Fraction(1))
    if base >= target:
        return Needed(COVERED, None, base, scale=Fraction(1))
    zero = fy_at_scale(Fraction(0))
    if zero < target:
        return Needed(CANNOT, None, zero, ZERO_DAYS_SHORT, scale=Fraction(0))
    lo, hi = 0, len(steps) - 1  # steps[lo] reaches the target; steps[hi] does not
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if fy_at_scale(steps[mid]) >= target:
            lo = mid
        else:
            hi = mid
    achieved = fy_at_scale(steps[lo])
    return Needed(SOLVES, None, achieved, overshoot=achieved - target, scale=steps[lo])
