"""Back-test: refit at each past cutoff on what was known then, and score the
fitted model against the two baselines.

Scoring was declared before building (design doc, builder check 8): per horizon,
mean absolute dollar error over all folds. The verdict is "yes" only if the
fitted model's error is lower than both baselines at 1 and 3 months, "no" if
not, and "not enough history to say" under six folds at either horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .fiscal import Window, add_months
from .fit import DEFAULT_PARAMS, FitParams, fit, matured_snapshots
from .forecast import model_forecast, run_rate, simulate, stage_weighted
from .history import as_known_at, latest_known_date
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


@dataclass(frozen=True)
class Backtest:
    folds: tuple[Fold, ...]
    scores: tuple[HorizonScore, ...]
    verdict: str
    verdict_reason: str
    notes: tuple[str, ...]


def fold(
    population: Dataset,
    cutoff: date,
    horizons: tuple[int, ...],
    profile: Profile,
    params: FitParams = DEFAULT_PARAMS,
    draws: int = 1000,
    seed: int = 0,
) -> list[Fold]:
    """Forecast each horizon from ``cutoff`` using only what was known then."""
    known = as_known_at(population, cutoff)
    if latest_known_date(known) > cutoff:  # defence in depth; as_known_at guarantees it
        raise AssertionError(f"fold at {cutoff} can see {latest_known_date(known)}")
    model = fit(known, cutoff, profile, params)
    folds = []
    for h in horizons:
        window = Window(f"+{h}m", cutoff, add_months(cutoff, h))
        actual = sum(
            (d.arr for d in population.deals if d.is_won and window.contains(d.close)),
            Decimal(0),
        )
        results = {
            RUN_RATE: run_rate(known, cutoff, [window], params.trailing_days),
            STAGE_WEIGHTED: stage_weighted(
                known, cutoff, profile, [window], params.trailing_days
            ),
            MODEL: model_forecast(model, known, cutoff, [window]),
        }
        forecasts = {
            k: (f.total() if f.available else None) for k, f in results.items()
        }
        range80 = range95 = None
        if results[MODEL].available:
            spread = simulate(
                model, known, cutoff, [window], draws=draws, seed=seed
            ).total
            range80, range95 = (spread.p10, spread.p90), (spread.p2_5, spread.p97_5)
        folds.append(Fold(cutoff, h, actual, forecasts, range80, range95))
    return folds


def backtest(
    population: Dataset,
    as_of: date,
    profile: Profile,
    params: FitParams = DEFAULT_PARAMS,
    draws: int = 1000,
    seed: int = 0,
) -> Backtest:
    folds: list[Fold] = []
    # Outcomes are only observed up to the latest dated fact in the files, which
    # can be earlier than the as-of date; no window may be scored past it.
    observed_through = (
        min(as_of, latest_known_date(population)) if population.deals else as_of
    )
    k = 1
    while True:
        cutoff = add_months(as_of, -k)
        known = as_known_at(population, cutoff)
        if (
            not known.deals
            or fit_snapshots(known, cutoff, params) < MIN_TRAINING_SNAPSHOTS
        ):
            break
        horizons = tuple(
            h for h in HORIZONS if add_months(cutoff, h) <= observed_through
        )
        if horizons:
            folds.extend(
                fold(population, cutoff, horizons, profile, params, draws, seed)
            )
        k += 1
    scores = tuple(_score(h, [f for f in folds if f.horizon == h]) for h in HORIZONS)
    notes = []
    if population.observations is None:
        notes.append(
            "no deal_observations.csv: past open-deal amounts and expected close dates are not "
            "recorded, so the fitted model and the stage-weighted baseline cannot be scored in dollars"
        )
    result, reason = verdict(scores)
    if population.observations is None and result == TOO_SHORT:
        reason = notes[0]
    return Backtest(tuple(folds), scores, result, reason, tuple(notes))


def fit_snapshots(known: Dataset, cutoff: date, params: FitParams) -> int:
    return len(matured_snapshots(known, cutoff, params.horizon_days))


def _score(horizon: int, folds: list[Fold]) -> HorizonScore:
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
    cov80 = cov95 = None
    if ranged:
        cov80 = sum(f.range80[0] <= f.actual <= f.range80[1] for f in ranged) / len(
            ranged
        )
        cov95 = sum(f.range95[0] <= f.actual <= f.range95[1] for f in ranged) / len(
            ranged
        )
    return HorizonScore(horizon, len(folds), mae, bias, cov80, cov95, len(ranged))


def verdict(scores) -> tuple[str, str]:
    by_h = {s.horizon: s for s in scores}
    for h in VERDICT_HORIZONS:
        s = by_h.get(h)
        if s is None or s.folds < MIN_FOLDS:
            n = 0 if s is None else s.folds
            return (
                TOO_SHORT,
                f"{n} folds at {h} month(s); at least {MIN_FOLDS} are needed",
            )
        if any(s.mae[m] is None for m in METHODS):
            return (
                TOO_SHORT,
                f"not every method could be scored in dollars at {h} month(s)",
            )
    losses = [
        f"{h}m: model {by_h[h].mae[MODEL]:,.0f} vs {m} {by_h[h].mae[m]:,.0f}"
        for h in VERDICT_HORIZONS
        for m in (RUN_RATE, STAGE_WEIGHTED)
        if not by_h[h].mae[MODEL] < by_h[h].mae[m]
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
