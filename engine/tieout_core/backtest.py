"""Back-test: refit at each past cutoff on what was known then, and score the
fitted model against the two baselines.

Scoring was declared before building (design doc, builder check 8): per horizon,
mean absolute dollar error over all folds. The verdict is "yes" only if the
fitted model's error is lower than both baselines at 1 and 3 months, "no" if
not, and "not enough history to say" under six folds at either horizon.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from statistics import median

from .fiscal import Window, add_months
from .fit import (
    DEFAULT_PARAMS,
    PARAMETER_RANGES,
    RECENCY,
    FitParams,
    fit,
    matured_snapshots,
)
from .forecast import Creation, model_forecast, run_rate, simulate, stage_weighted
from .history import as_known_at, latest_known_date
from .rates import wilson
from .records import Dataset, Profile

HORIZONS = (1, 3, 6)
VERDICT_HORIZONS = (1, 3)
MIN_FOLDS = 6
MIN_TRAINING_SNAPSHOTS = 3
RUN_RATE = "trailing run-rate"
STAGE_WEIGHTED = "stage-weighted pipeline"
MODEL = "fitted model"
METHODS = (RUN_RATE, STAGE_WEIGHTED, MODEL)
YES, NO, TOO_SHORT = "yes", "no", "not enough history to say"
BACK_TESTED, TOO_NARROW, TOO_WIDE, UNVALIDATED = (
    "back-tested", "too narrow", "too wide", "unvalidated",
)  # fmt: skip
NOMINAL80 = 0.8

# What the capacity term needs from a fold: the creation of pipeline not yet
# created as known at the cutoff (the cutoff, the data known then, the days to
# the end of the window). None means the flat trailing rate.
CreationFor = Callable[[date, Dataset, int], Creation | None]


@dataclass(frozen=True)
class Fold:
    cutoff: date
    horizon: int
    actual: Decimal
    forecasts: dict[str, Decimal | None]
    range80: tuple[float, float] | None
    range95: tuple[float, float] | None


@dataclass(frozen=True)
class HorizonScore:
    horizon: int
    folds: int
    mae: dict[str, Decimal | None]
    bias: dict[str, Decimal | None]
    coverage80: float | None
    coverage95: float | None
    range_folds: int = 0  # folds that had a fitted range: the coverage denominator
    inside80: int = 0  # of those, folds whose actual lay inside the 80% range
    median_width80: float | None = None


@dataclass(frozen=True)
class HorizonComparison:
    """The fitted model's error at one verdict horizon against each baseline's, with
    which is lower decided here so no reader has to compare numbers."""

    horizon: int
    model_error: Decimal
    against: dict[str, tuple[Decimal, str]]  # baseline: (its error, outcome)


@dataclass(frozen=True)
class Backtest:
    folds: tuple[Fold, ...]
    scores: tuple[HorizonScore, ...]
    verdict: str
    verdict_reason: str
    notes: tuple[str, ...]
    comparisons: tuple[HorizonComparison, ...] = ()
    in_words: str = ""


def fold(
    population: Dataset,
    cutoff: date,
    horizons: tuple[int, ...],
    profile: Profile,
    params: FitParams = DEFAULT_PARAMS,
    draws: int = 1000,
    seed: int = 0,
    creation_for: CreationFor | None = None,
) -> list[Fold]:
    """Forecast each horizon from ``cutoff`` using only what was known then."""
    known = as_known_at(population, cutoff)
    if latest_known_date(known) > cutoff:  # defense in depth; as_known_at guarantees it
        raise AssertionError(f"fold at {cutoff} can see {latest_known_date(known)}")
    model = fit(known, cutoff, profile, params)
    folds = []
    for h in horizons:
        window = Window(f"+{h}m", cutoff, add_months(cutoff, h))
        creation = (
            creation_for(cutoff, known, (window.end - cutoff).days)
            if creation_for
            else None
        )
        actual = sum(
            (d.arr for d in population.deals if d.is_won and window.contains(d.close)),
            Decimal(0),
        )
        results = {
            RUN_RATE: run_rate(known, cutoff, [window], params.trailing_days),
            STAGE_WEIGHTED: stage_weighted(
                known, cutoff, profile, [window], params.trailing_days
            ),
            MODEL: model_forecast(model, known, cutoff, [window], creation=creation),
        }
        forecasts = {
            k: (f.total() if f.available else None) for k, f in results.items()
        }
        range80 = range95 = None
        if results[MODEL].available:
            spread = simulate(
                model, known, cutoff, [window], draws=draws, seed=seed,
                parameter_uncertainty=params.ranges == PARAMETER_RANGES,
                creation=creation,
            ).total  # fmt: skip
            range80, range95 = (spread.p10, spread.p90), (spread.p2_5, spread.p97_5)
        folds.append(Fold(cutoff, h, actual, forecasts, range80, range95))
    return folds


def fold_cutoffs(
    population: Dataset, as_of: date, params: FitParams = DEFAULT_PARAMS
) -> list[tuple[date, tuple[int, ...]]]:
    """Each fold's cutoff, newest first, with the horizons it can be scored at.
    Outcomes are only observed up to the latest dated fact in the files, which
    can be earlier than the as-of date; no window may be scored past it."""
    observed_through = (
        min(as_of, latest_known_date(population)) if population.deals else as_of
    )
    out = []
    k = 1
    while True:
        cutoff = add_months(as_of, -k)
        known = as_known_at(population, cutoff)
        if (
            not known.deals
            or fit_snapshots(known, cutoff, params) < MIN_TRAINING_SNAPSHOTS
        ):
            return out
        horizons = tuple(
            h for h in HORIZONS if add_months(cutoff, h) <= observed_through
        )
        if horizons:
            out.append((cutoff, horizons))
        k += 1


def backtest(
    population: Dataset,
    as_of: date,
    profile: Profile,
    params: FitParams = DEFAULT_PARAMS,
    draws: int = 1000,
    seed: int = 0,
    creation_for: CreationFor | None = None,
) -> Backtest:
    folds: list[Fold] = []
    for cutoff, horizons in fold_cutoffs(population, as_of, params):
        folds.extend(
            fold(
                population, cutoff, horizons, profile, params, draws, seed, creation_for
            )
        )
    scores = tuple(
        score_horizon(h, [f for f in folds if f.horizon == h]) for h in HORIZONS
    )
    notes = []
    if population.observations is None:
        notes.append(
            "no deal_observations.csv: past open-deal amounts and expected close dates are not "
            "recorded, so the fitted model and the stage-weighted baseline cannot be scored in dollars"
        )
    result, reason = verdict(scores)
    if population.observations is None and result == TOO_SHORT:
        reason = notes[0]
    return Backtest(
        tuple(folds),
        scores,
        result,
        reason,
        tuple(notes),
        tuple(comparisons(scores)),
        verdict_in_words(result, scores, population.observations is not None),
    )


def fit_snapshots(known: Dataset, cutoff: date, params: FitParams) -> int:
    return len(matured_snapshots(known, cutoff, params.horizon_days))


def score_horizon(horizon: int, folds: list[Fold]) -> HorizonScore:
    mae: dict[str, Decimal | None] = {}
    bias: dict[str, Decimal | None] = {}
    for m in METHODS:
        pairs = [(f.forecasts[m], f.actual) for f in folds]
        if not pairs or any(p is None for p, _ in pairs):
            mae[m] = bias[m] = None
            continue
        n = Decimal(len(pairs))
        mae[m] = sum((abs(p - a) for p, a in pairs), Decimal(0)) / n
        bias[m] = sum((p - a for p, a in pairs), Decimal(0)) / n
    ranged = [f for f in folds if f.range80 is not None]
    cov80 = cov95 = width = None
    inside = sum(f.range80[0] <= f.actual <= f.range80[1] for f in ranged)
    if ranged:
        cov80 = inside / len(ranged)
        cov95 = sum(f.range95[0] <= f.actual <= f.range95[1] for f in ranged) / len(
            ranged
        )
        width = median(f.range80[1] - f.range80[0] for f in ranged)
    return HorizonScore(
        horizon, len(folds), mae, bias, cov80, cov95, len(ranged), inside, width
    )


def coverage_label(inside: int, folds: int) -> str:
    """A company-and-horizon cell: 'back-tested' when the 80% range's coverage
    is consistent with 80% (its 95% Wilson interval contains 0.8), otherwise
    too narrow or too wide; under MIN_FOLDS folds it is unvalidated."""
    if folds < MIN_FOLDS:
        return UNVALIDATED
    low, high = wilson(inside, folds)
    if low <= NOMINAL80 <= high:
        return BACK_TESTED
    return TOO_NARROW if high < NOMINAL80 else TOO_WIDE


BASELINES = (RUN_RATE, STAGE_WEIGHTED)
MODEL_LOWER, BASELINE_LOWER, TIE = "model lower", "baseline lower", "tie"


def _too_short(scores) -> tuple[str, int, int] | None:
    """Why the verdict cannot be given: ('folds', horizon, folds) when a verdict horizon
    has under MIN_FOLDS folds, ('unscored', horizon, 0) when a method cannot be scored in
    dollars there; None when every method is scored at every verdict horizon."""
    by_h = {s.horizon: s for s in scores}
    for h in VERDICT_HORIZONS:
        s = by_h.get(h)
        if s is None or s.folds < MIN_FOLDS:
            return "folds", h, 0 if s is None else s.folds
        if any(s.mae[m] is None for m in METHODS):
            return "unscored", h, 0
    return None


def _outcome(model: Decimal, baseline: Decimal) -> str:
    if model < baseline:
        return MODEL_LOWER
    return BASELINE_LOWER if model > baseline else TIE


def comparisons(scores) -> list[HorizonComparison]:
    """For each verdict horizon, the model's error and each baseline's with the outcome;
    empty when the verdict is 'not enough history to say'."""
    if _too_short(scores) is not None:
        return []
    by_h = {s.horizon: s for s in scores}
    return [
        HorizonComparison(
            h,
            by_h[h].mae[MODEL],
            {
                m: (by_h[h].mae[m], _outcome(by_h[h].mae[MODEL], by_h[h].mae[m]))
                for m in BASELINES
            },
        )
        for h in VERDICT_HORIZONS
    ]


def verdict(scores) -> tuple[str, str]:
    short = _too_short(scores)
    if short is not None:
        kind, h, n = short
        if kind == "folds":
            return (
                TOO_SHORT,
                f"{n} folds at {h} month(s); at least {MIN_FOLDS} are needed",
            )
        return TOO_SHORT, f"not every method could be scored in dollars at {h} month(s)"
    by_h = {s.horizon: s for s in scores}
    losses = [
        f"{c.horizon}m: model {c.model_error:,.0f} vs {m} {by_h[c.horizon].mae[m]:,.0f}"
        for c in comparisons(scores)
        for m in BASELINES
        if c.against[m][1] != MODEL_LOWER
    ]
    if losses:
        return (
            NO,
            "the model's mean absolute error is not lower than every baseline: "
            + "; ".join(losses),
        )
    return (
        YES,
        "the model's mean absolute error is lower than both baselines at 1 and 3 months",
    )


_MIN_FOLDS_IN_WORDS = {6: "six"}[
    MIN_FOLDS
]  # a change to MIN_FOLDS must reword the sentence
_AHEAD = {1: "one month", 3: "three months"}  # the verdict horizons, in words


def _horizons_in_words(horizons) -> str:
    return " and ".join(f"{_AHEAD[h]} ahead" for h in horizons)


def verdict_in_words(result: str, scores, observed: bool = True) -> str:
    """The verdict's reason as one sentence with no digits (the report's own sentence
    carries the figures). ``observed`` is whether past open-deal amounts exist."""
    if result == YES:
        return (
            "The fitted model's average miss is smaller than both simple yardsticks, "
            f"{_horizons_in_words(VERDICT_HORIZONS)}."
        )
    if result == NO:
        lost = [
            c.horizon
            for c in comparisons(scores)
            if any(outcome != MODEL_LOWER for _, outcome in c.against.values())
        ]
        return (
            "The fitted model's average miss is not smaller than both simple yardsticks "
            f"{_horizons_in_words(lost)}."
        )
    if not observed:
        return (
            "The past cannot be scored in dollars without a record of past open deals, "
            "so there is nothing to compare."
        )
    short = _too_short(scores)
    if short is not None and short[0] == "unscored":
        return "Not every method could be scored in dollars on the past, so there is nothing to compare."
    return (
        "Not enough past forecast dates to compare: the back-test needs at least "
        f"{_MIN_FOLDS_IN_WORDS} at both {' and '.join(_AHEAD[h] for h in VERDICT_HORIZONS)} ahead."
    )


@dataclass(frozen=True)
class Comparison:
    """A candidate estimator against the incumbent, on the same folds."""

    adopted: bool
    reason: str
    mae: dict[
        int, tuple[Decimal | None, Decimal | None]
    ]  # horizon: (incumbent, candidate)
    folds: dict[int, int]


def compare_estimators(incumbent: Backtest, candidate: Backtest) -> Comparison:
    """Declared rule (design doc, Goal 2A step 2.1): the candidate is adopted
    only if the fitted model's mean absolute error is lower at both 1 and 3
    months. Fewer than MIN_FOLDS folds, or a model that cannot be scored in
    dollars, keeps the incumbent."""

    def keys(b: Backtest):
        return sorted((f.cutoff, f.horizon) for f in b.folds)

    if keys(incumbent) != keys(candidate):
        raise ValueError("the estimators must be scored on the same folds")
    a = {s.horizon: s for s in incumbent.scores}
    b = {s.horizon: s for s in candidate.scores}
    mae = {h: (a[h].mae.get(MODEL), b[h].mae.get(MODEL)) for h in VERDICT_HORIZONS}
    folds = {h: a[h].folds for h in VERDICT_HORIZONS}
    for h in VERDICT_HORIZONS:
        if folds[h] < MIN_FOLDS:
            return Comparison(
                False,
                f"{folds[h]} folds at {h} month(s); at least {MIN_FOLDS} are needed to compare",
                mae,
                folds,
            )
        if None in mae[h]:
            return Comparison(
                False,
                f"not both fits could be scored in dollars at {h} month(s)",
                mae,
                folds,
            )
    text = "; ".join(
        f"{h}m: {mae[h][1]:,.0f} vs {mae[h][0]:,.0f}" for h in VERDICT_HORIZONS
    )
    if all(mae[h][1] < mae[h][0] for h in VERDICT_HORIZONS):
        return Comparison(
            True, f"lower mean absolute error at 1 and 3 months ({text})", mae, folds
        )
    return Comparison(
        False,
        f"mean absolute error not lower at both 1 and 3 months ({text})",
        mae,
        folds,
    )


def choose_fit(
    population: Dataset,
    as_of: date,
    profile: Profile,
    params: FitParams = DEFAULT_PARAMS,
    draws: int = 1000,
    seed: int = 0,
    creation_for: CreationFor | None = None,
) -> tuple[FitParams, Backtest, Comparison]:
    """Score the recency candidate against ``params`` on the same folds and
    return the fit in use with its back-test, by the declared rule."""
    candidate = replace(params, estimator=RECENCY)
    incumbent_bt = backtest(
        population, as_of, profile, params, draws, seed, creation_for
    )
    candidate_bt = backtest(
        population, as_of, profile, candidate, draws, seed, creation_for
    )
    cmp = compare_estimators(incumbent_bt, candidate_bt)
    if cmp.adopted:
        return candidate, candidate_bt, cmp
    return params, incumbent_bt, cmp


@dataclass(frozen=True)
class RangesDecision:
    adopted: bool
    reason: str
    pooled: dict[int, tuple[float, float]]  # horizon: (before, after)
    worst_cell: (
        tuple[object, int, float] | None
    )  # (company, horizon, points further from 80%)


def ranges_decision(before: dict, after: dict) -> RangesDecision:
    """Declared rule (design doc, Goal 2A step 2.2). ``before`` and ``after``
    map (company, horizon) to (folds inside the 80% range, folds with a range).
    Adopted if pooled 80% coverage at 1 and 3 months moves closer to 80% and no
    company-and-horizon cell moves more than 10 points further from it."""

    def pooled(cells, h):
        inside = sum(v[0] for (c, hh), v in cells.items() if hh == h)
        n = sum(v[1] for (c, hh), v in cells.items() if hh == h)
        return inside / n if n else None

    pooled_by_h = {h: (pooled(before, h), pooled(after, h)) for h in VERDICT_HORIZONS}
    worst = None
    for key in sorted(before, key=str):
        if key not in after or not before[key][1] or not after[key][1]:
            continue
        b, a = before[key][0] / before[key][1], after[key][0] / after[key][1]
        further = abs(a - NOMINAL80) - abs(b - NOMINAL80)
        if worst is None or further > worst[2]:
            worst = (key[0], key[1], further)
    text = "; ".join(
        f"{h}m pooled {b:.0%} -> {a:.0%}" for h, (b, a) in pooled_by_h.items()
        if b is not None and a is not None
    )  # fmt: skip
    for h, (b, a) in pooled_by_h.items():
        if b is None or a is None:
            return RangesDecision(
                False, f"no ranged folds at {h} month(s)", pooled_by_h, worst
            )
        if not abs(a - NOMINAL80) < abs(b - NOMINAL80):
            return RangesDecision(
                False, f"pooled 80% coverage at {h} month(s) does not move closer to 80% ({text})",
                pooled_by_h, worst,
            )  # fmt: skip
    if worst is not None and worst[2] > 0.10 + 1e-12:
        return RangesDecision(
            False,
            f"{worst[0]} at {worst[1]} month(s) moves {worst[2] * 100:.0f} points further from 80% "
            f"({text})",
            pooled_by_h, worst,
        )  # fmt: skip
    return RangesDecision(True, f"pooled coverage moves closer to 80% and no cell moves more than "
                                f"10 points further ({text})", pooled_by_h, worst)  # fmt: skip
