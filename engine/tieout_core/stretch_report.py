"""Goal 2D in the report: the decision with its evidence, the stretched simulation and
the label beside every range.

``evaluate`` rolls the back-test folds through ``stretch.score_horizon`` and applies the
declared rule (``stretch_rules.decide``). When the rule adopts the stretch, ``stretched``
returns the simulation with every range stretched by the factors of the horizon it
belongs to; the point forecasts, the medians and the means do not move. With-plan ranges
are never passed through here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction

from .backtest import Backtest
from .fiscal import Window
from .forecast import Simulation
from .stretch import HorizonStretch, horizon_for, score_horizon, stretch_spread
from .stretch_rules import (
    ADOPTED,
    HORIZONS,
    MAX_WORSENING,
    MIN_ELIGIBLE_FOLDS,
    MIN_SCORED_FOLDS,
    SCORED_HORIZONS,
    SIDE_COVERAGE,
    TARGET,
    Counts,
    Decision,
    decide,
)

STRETCHED = "stretched by past misses"
SIMULATED = "simulated"
NOT_SEPARATELY_TESTED = "not separately tested"
_WORDS = {1: "one-month", 3: "three-month", 6: "six-month"}


def _percent(x: Fraction) -> str:
    return f"{float(x):.0%}"


RULE = (
    f"adopted if there are at least {MIN_SCORED_FOLDS} scored folds at 1 and at 3 months, "
    f"pooled 80% coverage over 1 and 3 months is closer to {_percent(TARGET)} than the "
    f"simulated range's on the same folds, and no horizon (1, 3 or 6 months) moves more than "
    f"{float(MAX_WORSENING) * 100:.0f} points further from {_percent(TARGET)}; each side's "
    f"factor is the smallest, never below 1, that would have put at least "
    f"{_percent(SIDE_COVERAGE)} of the eligible past folds inside on that side (a fold is "
    f"eligible once its whole horizon has ended; at least {MIN_ELIGIBLE_FOLDS} are needed)"
)


@dataclass(frozen=True)
class Evaluation:
    decision: Decision
    horizons: dict[int, HorizonStretch]

    @property
    def adopted(self) -> bool:
        return self.decision.outcome == ADOPTED


def evaluate(bt: Backtest, as_of: date) -> Evaluation:
    folds = list(bt.folds)
    horizons = {h: score_horizon(folds, h, as_of) for h in HORIZONS}
    decision = decide(
        [
            Counts(h, s.scored, s.inside_simulated, s.inside_stretched)
            for h, s in horizons.items()
        ]
    )
    return Evaluation(decision, horizons)


def stretched(
    sim: Simulation,
    windows: list[Window],
    groups: dict[str, list[str]],
    as_of: date,
    ev: Evaluation,
) -> Simulation:
    """The simulation with every month's and every group's range stretched by the factors
    of the tested horizon it falls in; unchanged when the stretch is not adopted."""
    if not ev.adopted:
        return sim
    ends = {w.label: w.end for w in windows}

    def factors(end: date):
        return ev.horizons[horizon_for(as_of, end)[0]].factors

    by_window = {
        label: stretch_spread(spread, factors(ends[label]))
        for label, spread in sim.by_window.items()
    }
    by_group = {}
    for name, spread in sim.by_group.items():
        months = [ends[m] for m in groups.get(name, []) if m in ends]
        by_group[name] = (
            stretch_spread(spread, factors(max(months))) if months else spread
        )
    return replace(sim, by_window=by_window, by_group=by_group)


# ---------------------------------------------------------------- the labels


def labels(ev: Evaluation, as_of: date, end: date) -> tuple[str, str] | None:
    """The (80%, 95%) labels of a range that ends at ``end``, or None when the stretch is
    not adopted (the range keeps its back-test label)."""
    if not ev.adopted:
        return None
    h, beyond = horizon_for(as_of, end)
    s = ev.horizons[h]
    if not s.factors.learned:
        return (
            (
                f"{SIMULATED}: fewer than {MIN_ELIGIBLE_FOLDS} past {_WORDS[h]} "
                "forecasts to stretch from"
            ),
            f"{SIMULATED}, {NOT_SEPARATELY_TESTED}",
        )
    if beyond:
        head = (
            f"{STRETCHED} with the six-month factors, because this range is longer "
            "than six months"
        )
        held = f"held {s.inside_stretched} of {s.scored} past {_WORDS[h]} forecasts"
    else:
        head = STRETCHED
        held = f"held {s.inside_stretched} of {s.scored} past forecasts at this horizon"
    if not s.scored:
        held = f"no past {_WORDS[h]} forecast could be scored yet"
    return f"{head}; {held}", f"stretched, {NOT_SEPARATELY_TESTED}"


def status(ev: Evaluation, as_of: date, end: date) -> str | None:
    """A window's long status: its label and what the simulated range alone held."""
    got = labels(ev, as_of, end)
    if got is None or not got[0].startswith(STRETCHED):
        return None if got is None else got[0]
    h, _ = horizon_for(as_of, end)
    s = ev.horizons[h]
    if not s.scored:
        return got[0]
    return (
        f"{got[0]} (the simulated range alone held {s.inside_simulated} of {s.scored})"
    )


def by_window_label(ev: Evaluation) -> str | None:
    if not ev.adopted:
        return None
    return (
        f"{STRETCHED}; each month by the factors of the horizon it falls in, and months "
        "beyond six use the six-month factors"
    )


# ---------------------------------------------------------------- the report's section


def _coverage(inside: int, scored: int) -> float | None:
    return round(inside / scored, 4) if scored else None


def _factor(x: float) -> str | None:
    return None if x == float("inf") else f"{x:.4f}"


def _width(x: float | None) -> str | None:
    return None if x is None else f"{x:.2f}"


def evidence(ev: Evaluation) -> dict:
    """``backtest.candidates.ranges``: the rule, the decision and, per tested horizon, what
    the back-test says."""
    d = ev.decision
    pooled = None
    if d.pooled is not None:
        scored = sum(ev.horizons[h].scored for h in SCORED_HORIZONS)
        pooled = {
            "scored_folds": scored,
            "coverage_simulated": round(float(d.pooled[0]), 4),
            "coverage_stretched": round(float(d.pooled[1]), 4),
        }
    return {
        "rule": RULE,
        "decision": d.outcome,
        "reason": d.reason,
        "pooled": pooled,
        "horizons": [
            {
                "horizon_months": h,
                "eligible_folds": s.factors.eligible,
                "factors_learned": s.factors.learned,
                "scored_folds": s.scored,
                "inside_simulated": s.inside_simulated,
                "inside_stretched": s.inside_stretched,
                "coverage_simulated": _coverage(s.inside_simulated, s.scored),
                "coverage_stretched": _coverage(s.inside_stretched, s.scored),
                "median_width80_simulated": _width(s.median_width_simulated),
                "median_width80_stretched": _width(s.median_width_stretched),
                "lower_factor": _factor(s.factors.lower),
                "upper_factor": _factor(s.factors.upper),
            }
            for h, s in ev.horizons.items()
        ],
    }
