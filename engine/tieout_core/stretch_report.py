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
from .fiscal import Window, add_months
from .forecast import Simulation
from .stretch import (
    HorizonStretch,
    horizon_for,
    score_horizon,
    stretch_spread_with_floors,
)
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
) -> tuple[Simulation, dict[str, tuple[bool, bool]]]:
    """The simulation with every month's and every group's range stretched by the factors
    of the tested horizon it falls in, and, per group, whether its 80% and its 95% lower edge
    had to be floored at zero; unchanged when the stretch is not adopted."""
    if not ev.adopted:
        return sim, {}
    ends = {w.label: w.end for w in windows}

    def factors(end: date):
        return ev.horizons[horizon_for(as_of, end)[0]].factors

    by_window = {
        label: stretch_spread_with_floors(spread, factors(ends[label]))[0]
        for label, spread in sim.by_window.items()
    }
    by_group, floors = {}, {}
    for name, spread in sim.by_group.items():
        months = [ends[m] for m in groups.get(name, []) if m in ends]
        if months:
            by_group[name], floors[name] = stretch_spread_with_floors(
                spread, factors(max(months))
            )
        else:
            by_group[name] = spread
    return replace(sim, by_window=by_window, by_group=by_group), floors


# ---------------------------------------------------------------- the labels


@dataclass(frozen=True)
class Basis:
    """What stands behind a stretched range: the tested horizon whose factors it uses, which
    side those factors stretch, how many past forecasts at that horizon held and were scored,
    the window it covers and whether that is a shape that was tested, and whether a lower edge
    was floored at zero. Both lengths of label are built from these fields and nothing else."""

    factor_horizon_months: int
    held: int
    scored: int
    stretched_side: str  # lower, upper, both or neither
    window_start: date
    window_end: date
    extrapolated_because: (
        str | None
    )  # longer_than_six_months, not_the_tested_shape or None
    floored80: bool
    floored95: bool

    @property
    def extrapolated(self) -> bool:
        return self.extrapolated_because is not None

    def as_json(self) -> dict:
        return {
            "factor_horizon_months": self.factor_horizon_months,
            "held": self.held,
            "scored": self.scored,
            "stretched_side": self.stretched_side,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "extrapolated": self.extrapolated,
            "extrapolated_because": self.extrapolated_because,
            "floored_at_zero_80": self.floored80,
            "floored_at_zero_95": self.floored95,
        }


def side_of(factors) -> str:
    lower = factors.lower is not None and factors.lower > 1
    upper = factors.upper is not None and factors.upper > 1
    return {(True, True): "both", (True, False): "lower", (False, True): "upper"}.get(
        (lower, upper), "neither"
    )


def basis(
    ev: Evaluation,
    as_of: date,
    start: date,
    end: date,
    floors: tuple[bool, bool] = (False, False),
) -> Basis | None:
    """The basis of a range that covers (``start``, ``end``], or None when the stretch is not
    adopted or its horizon has too few folds to have learned a factor. Only a range that runs
    from the as-of date to exactly a tested horizon out is the shape that was tested; any
    other is extrapolated, and says so."""
    if not ev.adopted:
        return None
    h, beyond = horizon_for(as_of, end)
    s = ev.horizons[h]
    if not s.factors.learned:
        return None
    because = None
    if beyond:
        because = "longer_than_six_months"
    elif start != as_of or end != add_months(as_of, h):
        because = "not_the_tested_shape"
    return Basis(
        h, s.inside_stretched, s.scored, side_of(s.factors), start, end, because,
        floors[0], floors[1],
    )  # fmt: skip


_AHEAD = {1: "one month", 3: "three months", 6: "six months"}
_SIDE = {"lower": "the low side", "upper": "the high side", "both": "both sides"}
_THIN_BELOW = MIN_SCORED_FOLDS  # fewer scored past forecasts than this is called thin


def _date(d: date) -> str:
    """A date as the app writes it: Aug 31, 2026."""
    return f"{d:%b} {d.day}, {d.year}"


def label_short(b: Basis) -> str:
    """For cards and opened quarter rows: which side was stretched, no dates."""
    text = (
        f"Stretched on {_SIDE[b.stretched_side]} by past misses"
        if b.stretched_side in _SIDE
        else "Checked against past misses; no stretch needed"
    )
    return f"{text}; floored at zero" if b.floored80 else text


def label95(b: Basis) -> str:
    text = f"Stretched the same way; {NOT_SEPARATELY_TESTED}"
    return f"{text}; floored at zero" if b.floored95 else text


def label_full(b: Basis) -> str:
    """For the line on how far to trust the ranges and the checks section: plain sentences."""
    word = _WORDS[b.factor_horizon_months]
    parts = [
        f"Stretched by the model's own past misses, using what {word} forecasts needed."
    ]
    n = b.scored
    if n == 0:
        parts.append(
            f"No past {word} forecast could be scored yet, so the stretch is untested at this length."
        )
    elif n < _THIN_BELOW:
        held = (
            "held it" if (b.held, n) == (1, 1)
            else "did not hold it" if (b.held, n) == (0, 1)
            else "held all of them" if b.held == n
            else "held none of them" if b.held == 0
            else f"held {b.held} of them"
        )  # fmt: skip
        parts.append(
            f"Evidence at this length is thin: {n} past {word} forecast{'s' if n > 1 else ''} "
            f"could be scored, and the stretched range {held}."
        )
    else:
        parts.append(f"The stretched range held {b.held} of {n} past {word} forecasts.")
    window = f"({_date(b.window_start)} to {_date(b.window_end)})"
    if b.extrapolated_because == "longer_than_six_months":
        parts.append(
            f"This window {window} is longer than six months, so it uses the six-month factors."
        )
    elif b.extrapolated_because == "not_the_tested_shape":
        parts.append(
            f"This window {window} is not exactly the {word} forecast that was tested."
        )
    if b.floored80:
        parts.append("The lower edge of this range was floored at zero.")
    return " ".join(parts)


def unlearned_short() -> str:
    return "Simulated: too few past forecasts to stretch from"


def unlearned_full(as_of: date, end: date) -> str:
    h, _ = horizon_for(as_of, end)
    return (
        f"{SIMULATED.capitalize()}: fewer than {MIN_ELIGIBLE_FOLDS} past {_WORDS[h]} "
        "forecasts to stretch from."
    )


def status_text(label: str, b: Basis, ev: Evaluation) -> str:
    """A window's long status: its full label (what the simulated range alone held is in the
    evidence table)."""
    return label


BY_WINDOW_LABEL = (
    f"{STRETCHED}; each month by the factors of the horizon it falls in, and months "
    "beyond six use the six-month factors"
)


def by_window_label(ev: Evaluation) -> str | None:
    return BY_WINDOW_LABEL if ev.adopted else None


# ---------------------------------------------------------------- the report's section

_NO_FINITE = (
    "a past forecast fell outside this side of a range that had no width on it, so no "
    "finite factor would have held {rank} of the eligible past forecasts"
)


def _coverage(inside: int, scored: int) -> float | None:
    return round(inside / scored, 4) if scored else None


def _factor(x: float | None) -> str | None:
    return None if x is None else f"{x:.4f}"


def _reason(x: float | None) -> str | None:
    return None if x is not None else _NO_FINITE.format(rank=_percent(SIDE_COVERAGE))


def _width(x: float | None) -> str | None:
    return None if x is None else f"{x:.2f}"


def method_text(eligible_six: int, scored_six: int) -> str:
    """How the factor is chosen, said plainly, and why the six-month one is the least certain."""
    return (
        f"Each side's factor is the ceil({_percent(SIDE_COVERAGE)} of n)-th smallest of the factors "
        "the n eligible past forecasts would have needed: the plain empirical rule, not a "
        "finite-sample guarantee. Six-month factors come from overlapping forecasts (each shares "
        f"five of its six months with its neighbors) and are noisier: {eligible_six} past "
        f"six-month forecasts to learn from, {scored_six} scored."
    )


def stretched_side(ev: Evaluation) -> str:
    """Which sides the factors in use stretch: lower, upper, both or neither."""
    learned = [s.factors for s in ev.horizons.values() if s.factors.learned]
    lower = any(f.lower is not None and f.lower > 1 for f in learned)
    upper = any(f.upper is not None and f.upper > 1 for f in learned)
    return {(True, True): "both", (True, False): "lower", (False, True): "upper"}.get(
        (lower, upper), "neither"
    )


def acceptance_text(
    side: str, coverage: float, eligible_six: int, scored_six: int, floored: list[str]
) -> str:
    shape = (
        f"The stretch was one-sided: only the {side} side was stretched."
        if side in ("lower", "upper")
        else f"The stretch moved {'both sides' if side == 'both' else 'neither side'}."
    )
    text = (
        f"{shape} On the scored past dates it held {coverage:.1%} of actuals against a target "
        f"of {_percent(TARGET)}. The six-month factors rest on {eligible_six} past six-month "
        f"forecasts, of which {scored_six} could be scored."
    )
    if floored:
        text += f" The lower edge was floored at zero for: {', '.join(floored)}."
    return text


def evidence(ev: Evaluation, floored_names: list[str] | None = None) -> dict:
    """``backtest.candidates.ranges``: the rule, the decision and, per tested horizon, what
    the back-test says."""
    d = ev.decision
    six = ev.horizons[6]
    pooled = acceptance = None
    if d.pooled is not None:
        scored = sum(ev.horizons[h].scored for h in SCORED_HORIZONS)
        pooled = {
            "scored_folds": scored,
            "coverage_simulated": round(float(d.pooled[0]), 4),
            "coverage_stretched": round(float(d.pooled[1]), 4),
        }
    if ev.adopted:
        names = list(floored_names or [])
        side = stretched_side(ev)
        coverage = round(float(d.pooled[1]), 4)  # type: ignore[index]
        acceptance = {
            "stretched_side": side,
            "one_sided": side in ("lower", "upper"),
            "two_sided_coverage": coverage,
            "six_month_eligible_folds": six.factors.eligible,
            "six_month_scored_folds": six.scored,
            "floored_at_zero": names,
            "sentence": acceptance_text(
                side, coverage, six.factors.eligible, six.scored, names
            ),
        }
    return {
        "rule": RULE,
        "method": method_text(six.factors.eligible, six.scored),
        "decision": d.outcome,
        "reason": d.reason,
        "pooled": pooled,
        "acceptance": acceptance,
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
                "lower_reason": _reason(s.factors.lower),
                "upper_reason": _reason(s.factors.upper),
                "scored_dates": [
                    {
                        "cutoff": f.cutoff.isoformat(),
                        "inside_simulated": f.inside_simulated,
                        "inside_stretched": f.inside_stretched,
                        "lower_factor": _factor(f.lower),
                        "upper_factor": _factor(f.upper),
                    }
                    for f in s.detail
                ],
            }
            for h, s in ev.horizons.items()
        ],
    }
