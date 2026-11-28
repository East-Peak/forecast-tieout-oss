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
from .capacity import creation_text
from .fit import Timing
from .forecast import EXISTING, Forecast, Inflow, Lift, model_forecast
from .plan import NEXT_12, REST_OF_FY
from .roster import Member
from .worksheet_rules import (
    CYCLE_DAYS,
    PRECISION,
    PRODUCTIVITY,
    WIN_RATE,
    WON_ARR,
    boundary_at_or_after,
    boundary_at_or_before,
    round_up,
    scaled_days,
)

ZERO = Decimal(0)
ONE = Decimal(1)

SOLVES = "solves"
CANNOT = "cannot_close_alone"
COVERED = "already_at_or_ahead"
BOUNDED_AT_ONE = "bounded_at_one"
NO_EFFECT = "no_effect_in_the_year"
ZERO_DAYS_SHORT = "short_even_at_zero_days"
NO_SLOPE = Decimal(
    "1e-9"
)  # dollars a unit: below this a driver moves nothing, it is only rounding


# ------------------------------------------------------------------ the overrides


def timing_mean(t: Timing) -> Decimal | None:
    """Mean days of a win-time distribution: each sample once, or by its weight. None when there
    is no evidence (no samples, or no weight)."""
    weights = t.weights if t.weights is not None else (ONE,) * len(t.samples)
    total = sum(weights, ZERO)
    if not t.samples or total <= 0:
        return None
    return sum((Decimal(d) * w for d, w in zip(t.samples, weights)), ZERO) / total


def current_value(g: Ground, driver: str) -> Decimal | None:
    """The fitted value of ``driver`` now (None for a cycle with no win-time evidence)."""
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
    return _with_new(g, mean_won_arr=max(value, ZERO))


def with_productivity(g: Ground, value: Decimal) -> Ground:
    """Created deals per ramped AE-month where the capacity term is in use, else organic deals
    created per day. Never below zero."""
    value = max(value, ZERO)
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
    current = current_value(g, CYCLE_DAYS)
    if not current:
        raise ValueError(
            "a cycle of no days, or with no evidence, cannot be scaled to a setting"
        )
    return with_cycle_scale(g, Fraction(value) / Fraction(current))


def realized_cycle(g: Ground, scale: Fraction) -> Decimal:
    """The mean win time after ``scale`` and the rounding up."""
    return timing_mean(with_cycle_scale(g, scale).model.new_pipeline.timing)  # type: ignore[return-value]


# ------------------------------------------------------------------ the probe


def lift_under(lift: Lift | None, g: Ground, adjusted: Ground) -> Lift | None:
    """The actions' ``lift`` over ``g`` as ``adjusted`` (an override of ``g``) leaves it: their
    points are added to the pooled win rate it has, each day's rate held between zero and one,
    and the organic creation they act on is what it now is (programs' is changed by no driver)."""
    if not lift:
        return lift
    lift = lift.rebased(adjusted.model.new_pipeline.win_rate)
    if adjusted.model.new_pipeline.timing is not g.model.new_pipeline.timing:
        lift = lift.with_timing(adjusted.model.new_pipeline.timing)
    was, now = current_value(g, PRODUCTIVITY), current_value(adjusted, PRODUCTIVITY)
    return lift.scaled(now / was) if was and now is not None else lift


class Probe:
    """Forecasts of one scenario in force (a roster with planned hires and program pipeline) as
    its drivers are moved. Figures are what the report shows: a shown total is the sum of its
    months each to the cent; the fiscal-year figure is exact, as the existing solves use it."""

    def __init__(
        self,
        g: Ground,
        hires: Sequence[Member] = (),
        inflows: Sequence[Inflow] = (),
        lift: Lift | None = None,
    ) -> None:
        self.g = g
        self.hires, self.inflows = tuple(hires), tuple(inflows)
        self.lift = lift  # the driver actions in force
        self.scenario = Scenario(g)
        self._creation = self.scenario.creation(self.hires)
        self.base = self._run(g.model, self._creation, None, self.lift)
        self._shown_base = self.shown(self.base)

    def _run(self, model, creation, existing=None, lift=None) -> Forecast:
        g = self.g
        return model_forecast(
            model, g.pop, g.as_of, g.windows,
            creation=creation, inflows=self.inflows, existing=existing,
            lift=lift,
        )  # fmt: skip

    def with_lift(self, lift: Lift | None) -> Forecast:
        """This probe's scenario with ``lift`` in place of the one it was made with; open deals
        are reused."""
        return self._run(
            self.g.model, self._creation, self.base.components[EXISTING], lift
        )

    def forecast(self, adjusted: Ground) -> Forecast:
        """The forecast for ``adjusted`` (a ground made by the overrides above) with this probe's
        hires and program pipeline. What a driver cannot touch is reused, not recomputed: open
        deals are the baseline's, and the roster's ramped AE-months are projected once, with
        creation per day being the fitted rate times them (the very product ``project`` forms)."""
        creation = self._creation
        if creation is not None and adjusted.cap.fit.rate != self.g.cap.fit.rate:
            rate = adjusted.cap.fit.rate
            creation = replace(
                creation,
                per_day=tuple(rate * x for x in creation.ramped_ae_months),
                text=creation_text(rate),
            )
        return self._run(
            adjusted.model,
            creation,
            self.base.components[EXISTING],
            lift_under(self.lift, self.g, adjusted),
        )

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
    if slope <= NO_SLOPE:
        return Needed(CANNOT, current, base, NO_EFFECT)
    needed = current + (target - base) / slope
    if upper is not None and needed > upper:
        return Needed(CANNOT, upper, at_probe, BOUNDED_AT_ONE)
    return Needed(SOLVES, needed, fy_at(needed))


def round_solution(
    fy_at: Callable[[Decimal], Decimal],
    solved: Needed,
    driver: str,
    target: Decimal,
    upper: Decimal | None = None,
) -> Needed:
    """``solved`` with its value written to the driver's places, rounded up, and its bookings
    and overshoot recomputed from that written value, so that entering the number shown reaches
    the target. Anything but a solve is returned as it is."""
    if solved.outcome != SOLVES:
        return solved
    unit = Decimal(1).scaleb(-PRECISION[driver])
    value = round_up(solved.value, driver)
    while True:
        capped = value if upper is None else min(value, upper)
        achieved = fy_at(capped)
        if achieved >= target or capped == upper:
            break
        value += unit
    return Needed(SOLVES, capped, achieved, overshoot=achieved - target)


def solve_cycle(
    fy_at_scale: Callable[[Fraction], Decimal],
    samples: tuple[int, ...],
    target: Decimal,
) -> Needed:
    """The largest scale of the win-time ``samples`` that takes fiscal-year bookings to
    ``target``. Rounding up to whole days makes bookings a step function of the scale, so there
    is no exact root: the answer is the largest step that reaches the target, with what it
    overshoots by. Bookings never rise as the scale does, so the search narrows a scale that
    reaches the target and one that does not until no step lies between them."""
    base = fy_at_scale(Fraction(1))
    if base >= target:
        return Needed(COVERED, None, base, scale=Fraction(1))
    zero = fy_at_scale(Fraction(0))
    if zero < target:
        return Needed(CANNOT, None, zero, ZERO_DAYS_SHORT, scale=Fraction(0))
    lo, hi = Fraction(0), Fraction(1)  # lo reaches the target, hi does not
    reached = {lo: zero}
    while True:
        mid = (lo + hi) / 2
        step = boundary_at_or_after(samples, mid)
        if not lo < step < hi:
            step = boundary_at_or_before(samples, mid)
            if not lo < step < hi:
                break
        value = fy_at_scale(step)
        if value >= target:
            lo, reached[step] = step, value
        else:
            hi = step
    return Needed(SOLVES, None, reached[lo], overshoot=reached[lo] - target, scale=lo)
