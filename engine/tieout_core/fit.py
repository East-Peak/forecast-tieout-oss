"""The fitted model: pooled win rates by stage and age, empirical close timing,
and the parameters of pipeline not yet created.

``fit`` must be given data already cut to its cutoff (``history.as_known_at``),
and it only learns from snapshots whose whole horizon lies before the cutoff.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .fiscal import add_months
from .history import CREATION_AMOUNT_BASIS, UNKNOWN_STAGE, creation_amounts
from .rates import DEFAULT, FITTED, Rate, RateBook, wilson
from .records import LOST, WON, Dataset, Deal, Profile


@dataclass(frozen=True)
class FitParams:
    horizon_days: int = 365
    smoothing: int = 20  # pseudo-observations pulling a cell toward its stage
    min_timing_samples: int = 20
    trailing_days: int = 365


AGE_GROUPS = ((90, "0-90d"), (180, "91-180d"))
OLDEST_AGE_GROUP = "181d+"


def age_group(age_days: int) -> str:
    for limit, label in AGE_GROUPS:
        if age_days <= limit:
            return label
    return OLDEST_AGE_GROUP


@dataclass(frozen=True)
class Timing:
    """Empirical distribution of whole days from a starting point to a win."""

    samples: tuple[int, ...]
    source: str

    def cdf(self, days: int) -> Decimal:
        if days < 0 or not self.samples:
            return Decimal(0)
        return Decimal(bisect_right(self.samples, days)) / Decimal(len(self.samples))

    def count_through(self, days: int) -> int:
        return 0 if days < 0 else bisect_right(self.samples, days)


@dataclass(frozen=True)
class NewPipeline:
    win_rate: Decimal  # share of created deals won within the horizon
    timing: Timing  # days from creation to win
    mean_won_arr: Decimal
    mean_created_arr: Decimal
    created_per_day: Decimal
    won_arr_samples: tuple[Decimal, ...]
    cohort_size: int  # matured created deals behind win_rate; 0 means no evidence


@dataclass(frozen=True)
class Model:
    cutoff: date
    params: FitParams
    rates: RateBook
    cells: dict[tuple[str, str], Decimal]
    stage_rates: dict[str, Decimal]
    timings: dict[str, Timing]
    new_pipeline: NewPipeline
    unknown_stage_observations: int
    snapshot_count: int = 0
    cell_timings: dict[tuple[str, str], Timing] = field(default_factory=dict)

    def win_rate(self, stage: str, age_days: int) -> Decimal:
        return self.cells.get((stage, age_group(age_days)), self.stage_rates[stage])

    def timing(self, stage: str, age_days: int) -> Timing:
        """Close timing for a deal in ``stage`` aged ``age_days``: its stage-and-age
        cell when that has enough wins, else the stage's (itself pooled when thin)."""
        return self.cell_timings.get((stage, age_group(age_days)), self.timings[stage])


def fit(
    data: Dataset, cutoff: date, profile: Profile, params: FitParams = FitParams()
) -> Model:
    horizon = params.horizon_days
    snapshots = matured_snapshots(data, cutoff, horizon)
    first = f"{snapshots[-1]} to {snapshots[0]}" if snapshots else "none"
    cohort_text = f"monthly snapshots {first}"
    history = defaultdict(list)
    for t in data.transitions:
        history[t.deal_id].append(t)

    stage_obs: dict[str, list[int | None]] = defaultdict(list)  # days to win, or None
    cell_obs: dict[tuple[str, str], list[int | None]] = defaultdict(list)
    seen_stage, seen_cell = set(), set()
    unknown = 0
    for s in reversed(snapshots):  # oldest first, so "first" means first in time
        for d in data.deals:
            if d.created > s or (d.is_closed and d.close <= s):
                continue
            stage = _stage_on(history[d.id], s)
            if stage == UNKNOWN_STAGE:
                unknown += 1
                continue
            days = _days_to_win(d, s, horizon)
            if (d.id, stage) not in seen_stage:
                seen_stage.add((d.id, stage))
                stage_obs[stage].append(days)
            cell = (stage, age_group((s - d.created).days))
            if (d.id, cell) not in seen_cell:
                seen_cell.add((d.id, cell))
                cell_obs[cell].append(days)

    book = RateBook()
    stage_rates: dict[str, Decimal] = {}
    for code in profile.open_codes:
        obs = stage_obs.get(code, [])
        wins = sum(1 for x in obs if x is not None)
        if obs:
            low, high = wilson(wins, len(obs))
            value, source = Decimal(wins) / Decimal(len(obs)), FITTED
        else:
            low = high = None
            value, source = profile.probability(code), DEFAULT
        stage_rates[code] = value
        book.add(
            Rate(
                name=f"win_within_horizon:{code}",
                value=value,
                definition=f"share of deals open in {profile.stage_name(code)} at a snapshot that are won within {horizon} days",
                numerator=f"{wins} won within {horizon} days",
                denominator=f"{len(obs)} deals open in {code} at their first matured snapshot",
                cohort=cohort_text,
                horizon=f"{horizon} days",
                sample_size=len(obs),
                source=source,
                low95=low,
                high95=high,
            )
        )

    m = Decimal(params.smoothing)
    cells: dict[tuple[str, str], Decimal] = {}
    for (code, group), outcomes in sorted(cell_obs.items()):
        if code not in stage_rates:
            continue
        wins, n = sum(1 for x in outcomes if x is not None), len(outcomes)
        cells[(code, group)] = (Decimal(wins) + m * stage_rates[code]) / (
            Decimal(n) + m
        )
        book.add(
            Rate(
                name=f"win_within_horizon:{code}:{group}",
                value=cells[(code, group)],
                definition=f"stage {code} rate for deals aged {group}, shrunk toward the stage rate with {params.smoothing} pseudo-observations",
                numerator=f"{wins} won within {horizon} days (+{params.smoothing} x stage rate)",
                denominator=f"{n} deals open in {code} aged {group} at their first matured snapshot (+{params.smoothing})",
                cohort=cohort_text,
                horizon=f"{horizon} days",
                sample_size=n,
                source=FITTED,
            )
        )

    pooled = tuple(
        sorted(x for obs in stage_obs.values() for x in obs if x is not None)
    )
    timings = {}
    for code in profile.open_codes:
        own = tuple(sorted(x for x in stage_obs.get(code, []) if x is not None))
        if len(own) >= params.min_timing_samples:
            timings[code] = Timing(own, f"stage {code}")
        else:
            timings[code] = Timing(
                pooled,
                f"pooled across stages (fewer than {params.min_timing_samples} wins in {code})",
            )

    # Timing is measured from the same snapshots as the win rate it goes with,
    # so a deal already old in its stage does not restart the clock.
    cell_timings = {}
    for cell, outcomes in cell_obs.items():
        own = tuple(sorted(x for x in outcomes if x is not None))
        if len(own) >= params.min_timing_samples:
            cell_timings[cell] = Timing(own, f"stage {cell[0]}, aged {cell[1]}")

    new = _new_pipeline(data, cutoff, params, book)
    return Model(
        cutoff, params, book, cells, stage_rates, timings, new, unknown, len(snapshots),
        cell_timings,
    )  # fmt: skip


def matured_snapshots(data: Dataset, cutoff: date, horizon: int) -> list[date]:
    """Monthly snapshot dates, newest first, whose horizon ends by the cutoff."""
    if not data.deals:
        return []
    earliest = min(d.created for d in data.deals)
    snapshots, k = [], 1
    while True:
        s = add_months(cutoff, -k)
        if s < earliest:
            return snapshots
        if (cutoff - s).days >= horizon:
            snapshots.append(s)
        k += 1


def _stage_on(history: list, when: date) -> str:
    stage = UNKNOWN_STAGE
    for t in history:
        if t.on > when:
            break
        stage = t.stage
    return UNKNOWN_STAGE if stage in (WON, LOST) else stage


def _days_to_win(d: Deal, start: date, horizon: int) -> int | None:
    if d.is_won and d.close <= start + timedelta(days=horizon):
        return (d.close - start).days
    return None


def _new_pipeline(
    data: Dataset, cutoff: date, params: FitParams, book: RateBook
) -> NewPipeline:
    horizon = params.horizon_days
    cohort_end = cutoff - timedelta(days=horizon)
    cohort_start = cohort_end - timedelta(days=params.trailing_days)
    cohort = [d for d in data.deals if cohort_start < d.created <= cohort_end]
    wins = [d for d in cohort if _days_to_win(d, d.created, horizon) is not None]
    first_amount = creation_amounts(data)
    created_amounts = [
        first_amount[d.id] for d in cohort if first_amount.get(d.id) is not None
    ]

    n = len(cohort)
    win_rate = Decimal(len(wins)) / Decimal(n) if n else Decimal(0)
    mean_won = _mean([d.arr for d in wins])
    mean_created = _mean(created_amounts)
    trailing_start = cutoff - timedelta(days=params.trailing_days)
    created_recent = sum(1 for d in data.deals if trailing_start < d.created <= cutoff)
    per_day = Decimal(created_recent) / Decimal(params.trailing_days)
    cohort_text = (
        f"new-business deals created {cohort_start + timedelta(days=1)} to {cohort_end}"
    )
    amount_basis = CREATION_AMOUNT_BASIS

    low, high = wilson(len(wins), n)
    for name, value, (definition, source), num, den, horizon_text, size, rng in (
        (
            "new_pipeline_win_rate", win_rate,
            _evidence(n, f"share of created deals won within {horizon} days of creation"),
            f"{len(wins)} won within {horizon} days", f"{n} deals created",
            f"{horizon} days", n, (low, high) if n else (None, None),
        ),
        (
            "mean_won_arr", mean_won,
            _evidence(len(wins), "mean booked ARR of a created deal that is won"),
            "booked ARR of those wins", f"{len(wins)} wins", f"{horizon} days", len(wins),
            (None, None),
        ),
        (
            "mean_created_arr", mean_created,
            _evidence(len(created_amounts), f"mean ARR of a created deal ({amount_basis})"),
            "ARR of created deals", f"{len(created_amounts)} deals with a known amount",
            "at creation", len(created_amounts), (None, None),
        ),
    ):  # fmt: skip
        book.add(
            Rate(
                name=name, value=value, definition=definition, numerator=num,
                denominator=den, cohort=cohort_text, horizon=horizon_text,
                sample_size=size, source=source, low95=rng[0], high95=rng[1],
            )
        )  # fmt: skip
    book.add(
        Rate(
            "created_deals_per_day", per_day, "new-business deals created per day",
            f"{created_recent} deals created", f"{params.trailing_days} days",
            f"created {trailing_start + timedelta(days=1)} to {cutoff}",
            "trailing", created_recent, FITTED,
        )
    )  # fmt: skip
    timing = Timing(
        tuple(sorted((d.close - d.created).days for d in wins)),
        "days from creation to win",
    )
    return NewPipeline(
        win_rate, timing, mean_won, mean_created, per_day, tuple(d.arr for d in wins), n
    )


def _evidence(n: int, definition: str) -> tuple[str, str]:
    """(definition, source) for a rate that is undefined without evidence: with
    no sample it is a default of 0, never presented as fitted."""
    if n:
        return definition, FITTED
    return f"{definition} (no evidence: set to 0)", DEFAULT


def _mean(values) -> Decimal:
    values = list(values)
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else Decimal(0)
