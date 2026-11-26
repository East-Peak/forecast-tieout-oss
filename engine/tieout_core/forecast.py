"""The forward function: three forecasts over the same windows.

Each forecast keeps its parts apart: what the pipeline open at the cutoff is
expected to book, what pipeline not yet created is assumed to book, and (for
the fitted model only) what pipeline added by the lever would book.
Expectations are exact decimals; the ranges come from a seeded simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

import numpy as np

from .fiscal import Window
from .fit import Model
from .history import UNKNOWN_STAGE
from .rates import ENTERED, FITTED, Rate
from .records import Check, Dataset, Profile

EXISTING = "existing pipeline"
FUTURE = "future pipeline"
ADDED = "added pipeline"
RUN_RATE = "run-rate"


@dataclass(frozen=True)
class Forecast:
    method: str
    components: dict[str, dict[str, Decimal]]
    assumptions: tuple[str, ...] = ()
    available: bool = True
    unavailable_reason: str = ""
    rates: tuple[Rate, ...] = ()

    def window_total(self, label: str) -> Decimal:
        return sum((c[label] for c in self.components.values()), Decimal(0))

    def total(self) -> Decimal:
        return sum(
            (sum(c.values(), Decimal(0)) for c in self.components.values()), Decimal(0)
        )


def _unavailable(method: str, reason: str) -> Forecast:
    return Forecast(method, {}, (), False, reason)


def _trailing_text(cutoff: date, trailing_days: int) -> str:
    return f"{cutoff - timedelta(days=trailing_days - 1)} to {cutoff}"


def _zeros(windows: list[Window]) -> dict[str, Decimal]:
    return {w.label: Decimal(0) for w in windows}


def _trailing_bookings(data: Dataset, cutoff: date, trailing_days: int) -> Decimal:
    start = cutoff - timedelta(days=trailing_days)
    return sum(
        (d.arr for d in data.deals if d.is_won and start < d.close <= cutoff),
        Decimal(0),
    )


def run_rate(
    data: Dataset, cutoff: date, windows: list[Window], trailing_days: int = 365
) -> Forecast:
    start = cutoff - timedelta(days=trailing_days)
    wins = [d for d in data.deals if d.is_won and start < d.close <= cutoff]
    won = sum((d.arr for d in wins), Decimal(0))
    per_day = won / Decimal(trailing_days)
    rate = Rate(
        "trailing_bookings_per_day", per_day, "new-business ARR booked per day",
        f"{won:.2f} ARR booked", f"{trailing_days} days", f"closed {_trailing_text(cutoff, trailing_days)}",
        "trailing", len(wins), FITTED,
    )  # fmt: skip
    return Forecast(
        "trailing run-rate",
        {RUN_RATE: {w.label: won * w.days / Decimal(trailing_days) for w in windows}},
        (
            f"new-business bookings continue at the trailing {trailing_days}-day rate of {per_day:.2f} per day",
        ),
        rates=(rate,),
    )


def _window_index(windows: list[Window], d: date) -> int | None:
    for i, w in enumerate(windows):
        if w.contains(d):
            return i
    return None


def stage_weighted(
    data: Dataset,
    cutoff: date,
    profile: Profile,
    windows: list[Window],
    trailing_days: int = 365,
) -> Forecast:
    method = "stage-weighted pipeline"
    open_deals = [d for d in data.deals if not d.is_closed]
    if any(d.arr is None for d in open_deals):
        return _unavailable(method, "open-deal amounts at this date are not recorded")
    if any(d.close is None for d in open_deals):
        return _unavailable(
            method, "open-deal expected close dates at this date are not recorded"
        )
    existing = _zeros(windows)
    unknown = 0
    for d in open_deals:
        if d.stage == UNKNOWN_STAGE:
            unknown += 1
            continue
        i = 0 if d.close <= cutoff else _window_index(windows, d.close)
        if i is not None and windows:
            existing[windows[i].label] += d.arr * profile.probability(d.stage)

    start = cutoff - timedelta(days=trailing_days)
    created = [d for d in data.deals if start < d.created <= cutoff]
    if any(d.arr is None for d in created):
        return _unavailable(
            method, "amounts of recently created deals at this date are not recorded"
        )
    created_per_day = sum((d.arr for d in created), Decimal(0)) / Decimal(trailing_days)
    cycles = [
        (d.close - d.created).days
        for d in data.deals
        if d.is_won and start < d.close <= cutoff
    ]
    first_stage = profile.open_codes[0]
    p_first = profile.probability(first_stage)
    future = _zeros(windows)
    if cycles and windows:
        cycle = int(median(cycles))
        for t in range(1, windows[-1].end.toordinal() - cutoff.toordinal() + 1):
            i = _window_index(windows, cutoff + timedelta(days=t + cycle))
            if i is not None:
                future[windows[i].label] += created_per_day * p_first
        cycle_text = f"closing {cycle} days after creation (median cycle of {len(cycles)} trailing wins)"
    else:
        cycle_text = (
            "no trailing wins, so no cycle length: future pipeline contributes nothing"
        )
    assumptions = (
        "open deals book at their amount times the profile's stage probability (stages.yaml), "
        "in the month of their expected close; past-due deals count in the first month",
        f"new pipeline is created at {created_per_day:.2f} ARR per day (trailing {trailing_days} days) "
        f"and converts at the {profile.stage_name(first_stage)} probability {p_first}, {cycle_text}",
    )
    if unknown:
        assumptions += (f"{unknown} open deals with no stage on record are left out",)
    window_text = _trailing_text(cutoff, trailing_days)
    rates = tuple(
        Rate(
            f"stage_probability:{code}", profile.probability(code),
            f"probability that a deal in {profile.stage_name(code)} is won (stages.yaml)",
            "", "", "stages.yaml", "unstated", 0, ENTERED,
        )
        for code in profile.open_codes
    ) + (
        Rate(
            "created_arr_per_day", created_per_day, "new-business ARR created per day",
            f"{sum((d.arr for d in created), Decimal(0)):.2f} ARR created", f"{trailing_days} days",
            f"created {window_text}", "trailing", len(created), FITTED,
        ),
        Rate(
            "median_won_cycle_days", Decimal(int(median(cycles))) if cycles else Decimal(0),
            "median days from creation to close of a won deal",
            "median of days to close", f"{len(cycles)} wins", f"closed {window_text}",
            "trailing", len(cycles), FITTED,
        ),
    )  # fmt: skip
    return Forecast(
        method, {EXISTING: existing, FUTURE: future}, assumptions, rates=rates
    )


def model_forecast(
    model: Model,
    data: Dataset,
    cutoff: date,
    windows: list[Window],
    added_pipeline: Decimal = Decimal(0),
) -> Forecast:
    method = "fitted model"
    open_deals = [d for d in data.deals if not d.is_closed and d.stage != UNKNOWN_STAGE]
    if any(d.arr is None for d in open_deals):
        return _unavailable(method, "open-deal amounts at this date are not recorded")
    unknown = sum(1 for d in data.deals if not d.is_closed and d.stage == UNKNOWN_STAGE)
    offsets = [
        (
            w.start.toordinal() - cutoff.toordinal(),
            w.end.toordinal() - cutoff.toordinal(),
        )
        for w in windows
    ]

    existing = _zeros(windows)
    for d in open_deals:
        p = model.win_rate(d.stage, (cutoff - d.created).days)
        timing = model.timing(d.stage)
        for w, (a, b) in zip(windows, offsets):
            existing[w.label] += d.arr * p * (timing.cdf(b) - timing.cdf(a))

    new = model.new_pipeline
    future = _zeros(windows)
    added = _zeros(windows)
    n = len(new.timing.samples)
    if n and windows:
        horizon_end = offsets[-1][1]
        per_created_deal = new.win_rate * new.mean_won_arr / Decimal(n)
        for w, (a, b) in zip(windows, offsets):
            hits = sum(
                new.timing.count_through(b - t) - new.timing.count_through(a - t)
                for t in range(1, horizon_end + 1)
            )
            future[w.label] = new.created_per_day * per_created_deal * hits
        if added_pipeline and new.mean_created_arr:
            per_window = added_pipeline / Decimal(len(windows))
            for sa, sb in offsets:
                deals_per_day = per_window / Decimal(sb - sa) / new.mean_created_arr
                for w, (a, b) in zip(windows, offsets):
                    hits = sum(
                        new.timing.count_through(b - t)
                        - new.timing.count_through(a - t)
                        for t in range(sa + 1, sb + 1)
                    )
                    added[w.label] += deals_per_day * per_created_deal * hits

    components = {EXISTING: existing, FUTURE: future}
    if added_pipeline:
        components[ADDED] = added
    assumptions = (
        "open deals book at their current amount times the fitted win rate for their stage and age, "
        "on the fitted close-timing distribution",
        f"new pipeline is created at {new.created_per_day:.4f} deals per day and wins at the fitted "
        f"creation-cohort rate {new.win_rate:.4f}, averaging {new.mean_won_arr:.2f} ARR per win",
    )
    if unknown:
        assumptions += (f"{unknown} open deals with no stage on record are left out",)
    return Forecast(method, components, assumptions)


def existing_pipeline_conservation(
    model: Model, data: Dataset, cutoff: date, windows: list[Window]
) -> Check:
    """Every open dollar is accounted for: expected won inside the windows, won
    later within the horizon, or not won within the horizon."""
    open_deals = [
        d
        for d in data.deals
        if not d.is_closed and d.stage != UNKNOWN_STAGE and d.arr is not None
    ]
    inside = model_forecast(
        model, Dataset(tuple(open_deals), (), None), cutoff, windows
    ).components[EXISTING]
    end = windows[-1].end.toordinal() - cutoff.toordinal()
    later = not_won = Decimal(0)
    for d in open_deals:
        p = model.win_rate(d.stage, (cutoff - d.created).days)
        later += d.arr * p * (1 - model.timing(d.stage).cdf(end))
        not_won += d.arr * (1 - p)
    total_open = sum((d.arr for d in open_deals), Decimal(0))
    accounted = sum(inside.values(), Decimal(0)) + later + not_won
    return Check(
        "existing pipeline conserved",
        abs(accounted - total_open) <= Decimal("0.000001"),
        f"open {total_open:.2f} = won in window {sum(inside.values(), Decimal(0)):.2f}"
        f" + won later {later:.2f} + not won {not_won:.2f}",
    )


@dataclass(frozen=True)
class Spread:
    mean: float
    p2_5: float
    p10: float
    p50: float
    p90: float
    p97_5: float


@dataclass(frozen=True)
class Simulation:
    draws: int
    seed: int
    by_window: dict[str, Spread] = field(compare=True)
    total: Spread = field(compare=True)
    samples_total: tuple[float, ...] = field(compare=True, repr=False)
    by_group: dict[str, Spread] = field(default_factory=dict)


def _spread(values: np.ndarray) -> Spread:
    q = np.percentile(values, [2.5, 10, 50, 90, 97.5])
    return Spread(float(values.mean()), *(float(x) for x in q))


def simulate(
    model: Model,
    data: Dataset,
    cutoff: date,
    windows: list[Window],
    draws: int = 4000,
    seed: int = 0,
    groups: dict[str, list[str]] | None = None,
) -> Simulation:
    """Draw outcomes from the fitted model: each open deal wins or not and, if
    it wins, closes after a day count drawn from its timing; future wins arrive
    as a Poisson process with sizes drawn from past wins."""
    rng = np.random.default_rng(seed)
    if not windows:
        empty = _spread(np.zeros(draws))
        return Simulation(
            draws,
            seed,
            {},
            empty,
            tuple(0.0 for _ in range(draws)),
            {g: empty for g in groups or {}},
        )
    ends = np.array([w.end.toordinal() - cutoff.toordinal() for w in windows])
    out = np.zeros((draws, len(windows)))
    draw_index = np.arange(draws)

    def book(rows: np.ndarray, offsets: np.ndarray, amounts: np.ndarray) -> None:
        idx = np.searchsorted(ends, offsets, side="left")
        keep = (offsets >= 1) & (idx < len(windows))
        np.add.at(out, (rows[keep], idx[keep]), amounts[keep])

    for d in data.deals:
        if d.is_closed or d.stage == UNKNOWN_STAGE or d.arr is None:
            continue
        samples = model.timing(d.stage).samples
        if not samples:
            continue
        p = float(model.win_rate(d.stage, (cutoff - d.created).days))
        won = rng.random(draws) < p
        days = np.asarray(samples)[rng.integers(0, len(samples), draws)]
        book(draw_index[won], days[won], np.full(int(won.sum()), float(d.arr)))

    new = model.new_pipeline
    if new.timing.samples and new.won_arr_samples:
        span = int(ends[-1])
        lam = float(new.created_per_day * new.win_rate) * span
        counts = rng.poisson(lam, draws)
        total = int(counts.sum())
        rows = np.repeat(draw_index, counts)
        created = rng.integers(1, span + 1, total)
        days = np.asarray(new.timing.samples)[
            rng.integers(0, len(new.timing.samples), total)
        ]
        sizes = np.asarray([float(x) for x in new.won_arr_samples])[
            rng.integers(0, len(new.won_arr_samples), total)
        ]
        book(rows, created + days, sizes)

    totals = out.sum(axis=1)
    return Simulation(
        draws,
        seed,
        {w.label: _spread(out[:, i]) for i, w in enumerate(windows)},
        _spread(totals),
        tuple(float(x) for x in totals),
        {
            name: _spread(
                out[:, [i for i, w in enumerate(windows) if w.label in labels]].sum(
                    axis=1
                )
            )
            for name, labels in (groups or {}).items()
        },
    )
