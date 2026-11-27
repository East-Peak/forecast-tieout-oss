"""Goal 2D: ranges stretched by the model's own past misses.

The thresholds and the adoption rule are declared in ``stretch_rules``. Here are the
computation and the rolling scorer, as pure functions: the as-of date is always an
argument, and a fold counts toward a forecast dated D only if its whole horizon had
ended by D.

A past fold's range is (p10, p90) about its median. The factor a fold would have needed
on a side is how far that side would have had to stretch for the actual to fall inside
(1 if it already did). The factor in use on a side is the smallest that would have put
at least ``SIDE_COVERAGE`` of the eligible folds inside, so it is never below 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date
from statistics import median

from .backtest import Fold
from .fiscal import add_months
from .forecast import Spread
from .stretch_rules import (
    HORIZONS,
    MIN_ELIGIBLE_FOLDS,
    side_rank,
)

INFINITE = math.inf


@dataclass(frozen=True)
class Factors:
    """The two factors in use. A side is None when no finite factor would have held 90% of the
    eligible folds (a past miss fell on a side with no width): that side keeps its simulated edge."""

    lower: float | None
    upper: float | None
    eligible: int  # the past folds they were learned from

    @property
    def learned(self) -> bool:
        return self.eligible >= MIN_ELIGIBLE_FOLDS


@dataclass(frozen=True)
class ScoredFold:
    """One scored past date: where the actual fell against each range, and the factors used."""

    cutoff: date
    inside_simulated: bool
    inside_stretched: bool
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class HorizonStretch:
    """One tested horizon: the rolling score and the factors in use at the as-of date."""

    horizon: int
    scored: int
    inside_simulated: int
    inside_stretched: int
    median_width_simulated: float | None
    median_width_stretched: float | None
    factors: Factors
    detail: tuple[ScoredFold, ...] = ()


def needed(fold: Fold) -> tuple[float, float]:
    """The (lower, upper) factor this fold's range would have needed for its actual to fall
    inside: 1 when it already did, infinite when the side has no width to stretch."""
    if fold.range80 is None or fold.median is None:
        raise ValueError("a fold without a range needed nothing")
    low, high = fold.range80
    mid, actual = fold.median, float(fold.actual)

    def side(edge: float, outside: bool, distance: float) -> float:
        if not outside:
            return 1.0
        width = abs(mid - edge)
        return distance / width if width > 0 else INFINITE

    return (
        side(low, actual < low, mid - actual),
        side(high, actual > high, actual - mid),
    )


def eligible_folds(folds: list[Fold], horizon: int, as_of: date) -> list[Fold]:
    """The folds at ``horizon`` that had a range and whose whole horizon had ended by ``as_of``."""
    return [
        f
        for f in folds
        if f.horizon == horizon
        and f.range80 is not None
        and f.median is not None
        and add_months(f.cutoff, f.horizon) <= as_of
    ]


def _smallest_holding(required: list[float]) -> float | None:
    ranked = sorted(required)
    rank = ranked[side_rank(len(ranked)) - 1]
    return rank if math.isfinite(rank) else None


def factors_from(eligible: list[Fold]) -> Factors:
    """The factors that would have put at least 90% of ``eligible`` inside, side by side.
    Fewer than five folds learn nothing: the factors stay at 1."""
    if len(eligible) < MIN_ELIGIBLE_FOLDS:
        return Factors(1.0, 1.0, len(eligible))
    pairs = [needed(f) for f in eligible]
    return Factors(
        _smallest_holding([p[0] for p in pairs]),
        _smallest_holding([p[1] for p in pairs]),
        len(eligible),
    )


def factors_at(folds: list[Fold], horizon: int, as_of: date) -> Factors:
    return factors_from(eligible_folds(folds, horizon, as_of))


def _stretch_side(edge: float, mid: float, factor: float | None) -> float:
    distance = mid - edge if edge <= mid else edge - mid
    if distance == 0 or factor is None or factor == 1.0:
        return (
            edge  # no width to stretch, or nothing to stretch by: keep the edge exact
        )
    return mid - factor * distance if edge <= mid else mid + factor * distance


def floored(low: float, mid: float, factors: Factors) -> bool:
    """Whether stretching this lower edge would have taken it below zero (and so was floored)."""
    return _stretch_side(low, mid, factors.lower) < 0


def stretch_range(
    low: float, mid: float, high: float, factors: Factors
) -> tuple[float, float]:
    """The range stretched away from its median; the lower edge is floored at zero, since
    bookings cannot be negative."""
    return (
        max(0.0, _stretch_side(low, mid, factors.lower)),
        _stretch_side(high, mid, factors.upper),
    )


def stretch_spread_with_floors(
    spread: Spread, factors: Factors
) -> tuple[Spread, tuple[bool, bool]]:
    """Both ranges of a simulated spread, stretched by the same factors about its median, and
    whether the 80% and the 95% lower edge had to be floored at zero."""

    def edges(low: float, high: float) -> tuple[float, float]:
        return stretch_range(low, spread.p50, high, factors)

    p10, p90 = edges(spread.p10, spread.p90)
    p2_5, p97_5 = edges(spread.p2_5, spread.p97_5)
    flags = (
        floored(spread.p10, spread.p50, factors),
        floored(spread.p2_5, spread.p50, factors),
    )
    return replace(spread, p2_5=p2_5, p10=p10, p90=p90, p97_5=p97_5), flags


def stretch_spread(spread: Spread, factors: Factors) -> Spread:
    return stretch_spread_with_floors(spread, factors)[0]


def horizon_for(as_of: date, end: date) -> tuple[int, bool]:
    """The tested horizon whose factors a range ending at ``end`` uses: the smallest that
    reaches ``end`` from ``as_of``; beyond six months, the six-month one (and True)."""
    months = 1
    while add_months(as_of, months) < end:
        months += 1
    for h in HORIZONS:
        if months <= h:
            return h, False
    return HORIZONS[-1], True


def score_horizon(folds: list[Fold], horizon: int, as_of: date) -> HorizonStretch:
    """Roll through the folds at ``horizon``: each is stretched with the factors learned
    from the folds eligible at its own date, and is scored only if there are at least five.
    The simulated range is counted on the same folds. The factors in use at ``as_of`` are
    learned from every fold eligible then."""
    inside_sim = inside_str = 0
    detail: list[ScoredFold] = []
    width_sim: list[float] = []
    width_str: list[float] = []
    for f in sorted(
        (f for f in folds if f.horizon == horizon and f.range80 is not None),
        key=lambda f: f.cutoff,
    ):
        if f.median is None:
            continue
        past = eligible_folds(folds, horizon, f.cutoff)
        if len(past) < MIN_ELIGIBLE_FOLDS:
            continue
        low, high = f.range80
        used = factors_from(past)
        new_low, new_high = stretch_range(low, f.median, high, used)
        actual = float(f.actual)
        held_sim, held_str = low <= actual <= high, new_low <= actual <= new_high
        inside_sim += held_sim
        inside_str += held_str
        detail.append(ScoredFold(f.cutoff, held_sim, held_str, used.lower, used.upper))
        width_sim.append(high - low)
        width_str.append(new_high - new_low)
    return HorizonStretch(
        horizon,
        len(width_sim),
        inside_sim,
        inside_str,
        median(width_sim) if width_sim else None,
        median(width_str) if width_str else None,
        factors_at(folds, horizon, as_of),
        tuple(detail),
    )
