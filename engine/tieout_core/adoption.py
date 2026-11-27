"""The adoption test for the capacity term (declared in ``capacity_rules``).

Scored on created-pipeline dollars, at 3 and 6 months, on the same folds as
the back-test. The per-rep rate is fitted only from data before each cutoff
(deals created and the roster known then) and applied to the ramped AE-months
that actually occurred. It asks whether headcount explains pipeline,
conditional on realized staffing; it is not a forecast back-test.

Three outcomes: adopted, not shown, unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from . import capacity_rules as rules
from .backtest import fold_cutoffs
from .capacity import CapacityFit, fit_capacity
from .capacity_config import CapacityConfig
from .figures import number
from .fiscal import add_months, month_windows
from .fit import DEFAULT_PARAMS, FitParams
from .history import as_known_at, creation_amounts
from .records import Dataset
from .roster import RampCurve, ramped_ae_months


def _percent1(share) -> str:
    """A share as a percent to one place, from the figure the report states (four places), half
    away from zero: the same words the screen reads out of that figure."""
    shown = Decimal(number(share, 4)) * 100
    return f"{shown.quantize(Decimal('0.1'), ROUND_HALF_UP)}%"


ADOPTED, NOT_SHOWN, UNAVAILABLE = "adopted", "not shown", "unavailable"
PLACES = Decimal("1e-10")


@dataclass(frozen=True)
class AdoptionFold:
    cutoff: date
    horizon: int  # months
    actual: Decimal  # pipeline dollars created in the window
    flat: Decimal  # trailing created dollars per day times the window's days
    capacity: (
        Decimal  # trailing dollars per ramped AE-month times realized ramped AE-months
    )


@dataclass(frozen=True)
class HorizonResult:
    horizon: int
    folds: int
    mae_flat: Decimal
    mae_capacity: Decimal
    improvement: Decimal  # (flat - capacity) / flat


@dataclass(frozen=True)
class Adoption:
    outcome: str
    reason: str
    variation: Decimal | None = None
    period: tuple[date, date] | None = None
    folds: tuple[AdoptionFold, ...] = ()
    scores: dict[int, HorizonResult] = field(default_factory=dict)


def _created(deals, amounts, after: date, through: date) -> Decimal:
    return sum(
        (
            amounts[d.id]
            for d in deals
            if after < d.created <= through and amounts.get(d.id) is not None
        ),
        Decimal(0),
    )


def score_fold(
    population: Dataset,
    members,
    cfg: CapacityConfig,
    cutoff: date,
    horizon: int,
    since: date,
    fitted: CapacityFit | None = None,
) -> AdoptionFold | None:
    """One fold at ``cutoff`` and ``horizon`` months; None if capacity cannot
    be fitted there (nobody employed in the trailing year)."""
    known = as_known_at(population, cutoff)
    fit = fitted or fit_capacity(known.deals, members, cutoff, since, cfg)
    if fit.unavailable:
        return None
    end = add_months(cutoff, horizon)
    trailing_start = cutoff - timedelta(days=rules.TRAILING_DAYS)
    trailing = _created(known.deals, creation_amounts(known), trailing_start, cutoff)
    flat = trailing / Decimal(rules.TRAILING_DAYS) * Decimal((end - cutoff).days)
    per_ramped_month = trailing / fit.trailing_ramped_months
    # Realized staffing: the whole roster as it turned out, the ramp known at the cutoff.
    realized = ramped_ae_months(members, fit.curve, cutoff, end)
    actual = _created(population.deals, creation_amounts(population), cutoff, end)
    return AdoptionFold(cutoff, horizon, actual, flat, per_ramped_month * realized)


def staffing_variation(members, curve: RampCurve, first: date, last: date) -> Decimal:
    """(largest - smallest) / mean of the average ramped heads in each calendar
    month over (first, last]."""
    windows = month_windows(first, last)
    if not windows:
        return Decimal(0)
    heads = [
        ramped_ae_months(members, curve, w.start, w.end)
        * rules.DAYS_PER_AE_MONTH
        / Decimal(w.days)
        for w in windows
    ]
    mean = sum(heads, Decimal(0)) / len(heads)
    if not mean:
        return Decimal(0)
    return ((max(heads) - min(heads)) / mean).quantize(PLACES)


def decide(folds: list[AdoptionFold], variation: Decimal) -> Adoption:
    """The declared rule, applied to scored folds and the staffing variation."""
    scores = {}
    for h in rules.SCORED_HORIZONS:
        mine = [f for f in folds if f.horizon == h]
        if mine:
            n = Decimal(len(mine))
            flat = sum((abs(f.flat - f.actual) for f in mine), Decimal(0)) / n
            cap = sum((abs(f.capacity - f.actual) for f in mine), Decimal(0)) / n
            better = (flat - cap) / flat if flat else Decimal(0)
            scores[h] = HorizonResult(h, len(mine), flat, cap, better)
    for h in rules.SCORED_HORIZONS:
        n = scores[h].folds if h in scores else 0
        if n < rules.MIN_FOLDS:
            return Adoption(
                NOT_SHOWN,
                f"{n} folds at {h} months; at least {rules.MIN_FOLDS} are needed",
                variation, None, tuple(folds), scores,
            )  # fmt: skip
    if variation < rules.MIN_STAFFING_VARIATION:
        return Adoption(
            NOT_SHOWN,
            f"ramped AE-months varied {variation:.0%} across the scored period; at least "
            f"{rules.MIN_STAFFING_VARIATION:.0%} is needed for headcount to be testable",
            variation, None, tuple(folds), scores,
        )  # fmt: skip
    for h in rules.SCORED_HORIZONS:
        s = scores[h]
        if s.improvement < rules.MIN_IMPROVEMENT:
            return Adoption(
                NOT_SHOWN,
                f"at {h} months the capacity rate's mean absolute error {s.mae_capacity:,.0f} is "
                f"{_percent1(s.improvement)} below the flat rate's {s.mae_flat:,.0f}; at least "
                f"{rules.MIN_IMPROVEMENT:.0%} lower is needed at both horizons",
                variation, None, tuple(folds), scores,
            )  # fmt: skip
    text = "; ".join(
        f"{h} months {scores[h].mae_capacity:,.0f} against {scores[h].mae_flat:,.0f} "
        f"({_percent1(scores[h].improvement)} lower)"
        for h in rules.SCORED_HORIZONS
    )
    return Adoption(
        ADOPTED,
        f"created-pipeline error with realized staffing: {text}; ramped AE-months varied "
        f"{variation:.0%}",
        variation, None, tuple(folds), scores,
    )  # fmt: skip


def adoption_test(
    population: Dataset,
    members,
    cfg: CapacityConfig | None,
    as_of: date,
    params: FitParams = DEFAULT_PARAMS,
    unavailable: str = "",
) -> Adoption:
    if unavailable:
        return Adoption(UNAVAILABLE, unavailable)
    if cfg is None:
        return Adoption(UNAVAILABLE, "no capacity.yaml in the profile")
    if not members:
        return Adoption(UNAVAILABLE, "no quota-carrying people in the roster")
    if not population.deals:
        return Adoption(UNAVAILABLE, "no deals")
    if population.observations is None:
        return Adoption(
            UNAVAILABLE,
            "no deal_observations.csv: the amounts of deals when they were created are not "
            "recorded, so created pipeline cannot be scored in dollars",
        )
    since = min(d.created for d in population.deals)
    now = fit_capacity(population.deals, members, as_of, since, cfg)
    if now.unavailable:
        return Adoption(UNAVAILABLE, now.unavailable)
    folds: list[AdoptionFold] = []
    for cutoff, horizons in fold_cutoffs(population, as_of, params):
        known = as_known_at(population, cutoff)
        fitted = fit_capacity(known.deals, members, cutoff, since, cfg)
        for h in rules.SCORED_HORIZONS:
            if h in horizons:
                f = score_fold(population, members, cfg, cutoff, h, since, fitted)
                if f is not None:
                    folds.append(f)
    if not folds:
        return Adoption(NOT_SHOWN, "no fold could be scored: too little history")
    first = min(f.cutoff for f in folds)
    last = max(add_months(f.cutoff, f.horizon) for f in folds)
    variation = staffing_variation(members, now.curve, first, last)
    result = decide(folds, variation)
    return Adoption(
        result.outcome,
        result.reason,
        variation,
        (first, last),
        result.folds,
        result.scores,
    )
