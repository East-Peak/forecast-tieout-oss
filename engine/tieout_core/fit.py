"""The fitted model: pooled win rates by stage and age, empirical close timing,
and the parameters of pipeline not yet created.

``fit`` must be given data already cut to its cutoff (``history.as_known_at``).
Two estimators of the same quantity (won within the horizon of a snapshot):

- ``MATURED`` (Goal 1): the share won, from snapshots whose whole horizon lies
  before the cutoff, so the newest evidence is a year old.
- ``RECENCY`` (Goal 2A candidate): the cumulative incidence of a win over days
  since the snapshot, with loss competing and still-open deals counted only for
  the days they were observed (Aalen-Johansen), from the trailing months'
  snapshots including young ones. Close timing is the same curve's increments.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from itertools import accumulate

from .fiscal import add_months
from .history import CREATION_AMOUNT_BASIS, UNKNOWN_STAGE, creation_amounts
from .rates import DEFAULT, FITTED, Rate, RateBook, wilson, wilson_interval
from .records import LOST, WON, Dataset, Deal, Profile

MATURED = "matured snapshots"
RECENCY = "cumulative incidence"
WIN, LOSS, OPEN = "won", "lost", "still open"
OUTCOME_RANGES = "deal outcomes only"
PARAMETER_RANGES = "deal outcomes and rate uncertainty"


@dataclass(frozen=True)
class FitParams:
    horizon_days: int = 365
    smoothing: int = 20  # pseudo-observations pulling a cell toward its stage
    min_timing_samples: int = 20
    trailing_days: int = 365
    estimator: str = MATURED
    recency_months: int = 24  # RECENCY: snapshots from this many trailing months
    ranges: str = OUTCOME_RANGES  # what the simulation draws


NEW_PIPELINE_LABEL = "Deals created, won within the horizon"
DEFAULT_PARAMS = FitParams()

AGE_GROUPS = ((90, "0-90d"), (180, "91-180d"))
OLDEST_AGE_GROUP = "181d+"


def age_group(age_days: int) -> str:
    for limit, label in AGE_GROUPS:
        if age_days <= limit:
            return label
    return OLDEST_AGE_GROUP


@dataclass(frozen=True)
class Timing:
    """Distribution of whole days from a starting point to a win: sorted
    samples, each counting once, or with ``weights`` (one per distinct day)."""

    samples: tuple[int, ...]
    source: str
    weights: tuple[Decimal, ...] | None = None
    _cum: tuple[Decimal, ...] = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.weights is not None:
            object.__setattr__(self, "_cum", tuple(accumulate(self.weights)))

    @property
    def total(self) -> int | Decimal:
        if self.weights is None:
            return len(self.samples)
        return self._cum[-1] if self._cum else Decimal(0)

    def count_through(self, days: int) -> int | Decimal:
        """Samples (or weight) on or before ``days``."""
        k = 0 if days < 0 else bisect_right(self.samples, days)
        if self.weights is None:
            return k
        return self._cum[k - 1] if k else Decimal(0)

    def cdf(self, days: int) -> Decimal:
        if days < 0 or not self.samples:
            return Decimal(0)
        return Decimal(self.count_through(days)) / Decimal(self.total)


@dataclass(frozen=True)
class Incidence:
    """A cumulative incidence of a win within a horizon, with its sample."""

    value: Decimal
    variance: float
    n: int
    wins: int  # wins observed within the horizon
    still_open: int  # observations censored while open
    timing: Timing  # the curve's increments: when, within the horizon, wins land
    known: int = 0  # observations whose outcome by the horizon is known

    @property
    def effective_n(self) -> float:
        """The binomial sample size with the same variance (n without censoring).
        At 0 or 1 the variance is zero and says nothing, so only observations
        whose outcome by the horizon is known count: a deal censored early
        carries no information about the horizon."""
        p = float(self.value)
        if self.variance <= 0 or p in (0.0, 1.0):
            return float(self.known)
        return min(float(self.n), p * (1 - p) / self.variance)


def cumulative_incidence(
    obs: list[tuple[int, str]], horizon: int, source: str = "cumulative incidence"
) -> Incidence:
    """Aalen-Johansen estimate of P(won within ``horizon`` days), from
    (days observed, outcome) pairs: WIN or LOSS on that day, or OPEN (censored
    after that day). An observation is at risk on every day up to its own.
    Computed in exact fractions; the variance is the delta-method estimate,
    which reduces to p(1 - p)/n without censoring."""
    n = len(obs)
    events: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for days, outcome in obs:
        if outcome != OPEN and days <= horizon:
            events[days][outcome == LOSS] += 1
    ordered = sorted(days for days, _ in obs)
    surv, cum = Fraction(1), Fraction(0)
    steps = []  # (at risk, wins, events, survival before, cumulative incidence after)
    for t in sorted(events):
        at_risk = n - bisect_left(ordered, t)
        wins, losses = events[t]
        cum += surv * Fraction(wins, at_risk)
        steps.append((t, at_risk, wins, wins + losses, surv, cum))
        surv *= 1 - Fraction(wins + losses, at_risk)
    final = float(cum)
    variance = 0.0
    for _, r, w, d, s_prev, f_j in steps:
        s_prev, gap = float(s_prev), final - float(f_j)
        if r > d:
            variance += gap * gap * d / (r * (r - d))
        variance += s_prev * s_prev * w * (r - w) / r**3
        variance -= 2 * gap * s_prev * w / r**2
    days = tuple(t for t, _, w, *_ in steps if w)
    weights = tuple(
        _dec(s_prev * Fraction(w, r)) for _, r, w, _, s_prev, _ in steps if w
    )
    known = sum(1 for d, o in obs if d >= horizon or (o != OPEN and d <= horizon))
    return Incidence(
        _dec(cum), max(0.0, variance), n, sum(w for _, _, w, *_ in steps),
        sum(1 for _, o in obs if o == OPEN), Timing(days, source, weights), known,
    )  # fmt: skip


def _dec(x: Fraction) -> Decimal:
    return Decimal(x.numerator) / Decimal(x.denominator)


@dataclass(frozen=True)
class NewPipeline:
    win_rate: Decimal  # share of created deals won within the horizon
    timing: Timing  # days from creation to win
    mean_won_arr: Decimal
    mean_created_arr: Decimal
    created_per_day: Decimal
    won_arr_samples: tuple[Decimal, ...]
    cohort_size: int  # created deals behind win_rate; 0 means no evidence
    win_rate_n: float = 0.0  # effective sample behind win_rate (its uncertainty)
    created_count: int = 0  # deals behind created_per_day
    created_days: int = 0  # ... over this many days
    # Weight of each won_arr_sample (None: equal). Recency weights each win by
    # its day's incidence increment, so censoring does not favor quick wins.
    won_arr_weights: tuple[Decimal, ...] | None = None
    # The deal's segment (as recorded) behind each won_arr_sample, so a segment can be drawn from its own.
    won_arr_segments: tuple[str, ...] | None = None


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
    # Effective sample behind each rate, keyed as rate_key returns; a rate with
    # none (a profile default) is held fixed when ranges draw rate uncertainty.
    rate_n: dict[tuple[str, str | None], float] = field(default_factory=dict)

    def rate_key(self, stage: str, age_days: int) -> tuple[str, str | None]:
        cell = (stage, age_group(age_days))
        return cell if cell in self.cells else (stage, None)

    def win_rate(self, stage: str, age_days: int) -> Decimal:
        return self.cells.get((stage, age_group(age_days)), self.stage_rates[stage])

    def timing(self, stage: str, age_days: int) -> Timing:
        """Close timing for a deal in ``stage`` aged ``age_days``: its stage-and-age
        cell when that has enough wins, else the stage's (itself pooled when thin)."""
        return self.cell_timings.get((stage, age_group(age_days)), self.timings[stage])


def fit(
    data: Dataset, cutoff: date, profile: Profile, params: FitParams = DEFAULT_PARAMS
) -> Model:
    if params.estimator == RECENCY:
        return _fit_recency(data, cutoff, profile, params)
    horizon = params.horizon_days
    snapshots = matured_snapshots(data, cutoff, horizon)
    first = f"{snapshots[-1]} to {snapshots[0]}" if snapshots else "none"
    cohort_text = f"monthly snapshots {first}"
    stage_seen, cell_seen, unknown = _observe(data, snapshots)
    stage_obs = {
        k: [_days_to_win(d, s, horizon) for d, s in v] for k, v in stage_seen.items()
    }
    cell_obs = {
        k: [_days_to_win(d, s, horizon) for d, s in v] for k, v in cell_seen.items()
    }

    book = RateBook()
    stage_rates: dict[str, Decimal] = {}
    rate_n: dict[tuple[str, str | None], float] = {}
    for code in profile.open_codes:
        obs = stage_obs.get(code, [])
        wins = sum(1 for x in obs if x is not None)
        if obs:
            low, high = wilson(wins, len(obs))
            value, source = Decimal(wins) / Decimal(len(obs)), FITTED
            rate_n[(code, None)] = float(len(obs))
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
                label=profile.stage_name(code),
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
        rate_n[(code, group)] = float(n + params.smoothing)
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
        cell_timings, rate_n,
    )  # fmt: skip


def _observe(data: Dataset, snapshots: list[date]):
    """Each deal open at a snapshot, at the first (oldest) snapshot where it is
    in a given stage, and in a given stage-and-age cell: (deal, snapshot) pairs."""
    history = defaultdict(list)
    for t in data.transitions:
        history[t.deal_id].append(t)
    by_stage: dict[str, list] = defaultdict(list)
    by_cell: dict[tuple[str, str], list] = defaultdict(list)
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
            if (d.id, stage) not in seen_stage:
                seen_stage.add((d.id, stage))
                by_stage[stage].append((d, s))
            cell = (stage, age_group((s - d.created).days))
            if (d.id, cell) not in seen_cell:
                seen_cell.add((d.id, cell))
                by_cell[cell].append((d, s))
    return by_stage, by_cell, unknown


def _outcome(d: Deal, start: date, cutoff: date) -> tuple[int, str]:
    """Days from ``start`` to the deal's outcome, or to the cutoff if it is
    still open there (the data is already cut, so a closed deal closed by then)."""
    if d.is_closed:
        return (d.close - start).days, WIN if d.is_won else LOSS
    return (cutoff - start).days, OPEN


def recent_snapshots(data: Dataset, cutoff: date, months: int) -> list[date]:
    """Monthly snapshot dates in the trailing ``months``, newest first, young
    ones included, none before the first deal."""
    if not data.deals:
        return []
    earliest = min(d.created for d in data.deals)
    snaps = [add_months(cutoff, -k) for k in range(1, months + 1)]
    return [s for s in snaps if s >= earliest]


def _fit_recency(
    data: Dataset, cutoff: date, profile: Profile, params: FitParams
) -> Model:
    horizon, months = params.horizon_days, params.recency_months
    snapshots = recent_snapshots(data, cutoff, months)
    first = f"{snapshots[-1]} to {snapshots[0]}" if snapshots else "none"
    cohort_text = f"monthly snapshots {first}"
    stage_seen, cell_seen, unknown = _observe(data, snapshots)

    def incidence(pairs, source):
        return cumulative_incidence(
            [_outcome(d, s, cutoff) for d, s in pairs], horizon, source
        )

    stage_ci = {k: incidence(v, f"stage {k}") for k, v in stage_seen.items()}
    book = RateBook()
    stage_rates: dict[str, Decimal] = {}
    rate_n: dict[tuple[str, str | None], float] = {}
    for code in profile.open_codes:
        ci = stage_ci.get(code)
        if ci is not None:
            low, high = wilson_interval(float(ci.value), ci.effective_n)
            value, source = ci.value, FITTED
            rate_n[(code, None)] = ci.effective_n
        else:
            low = high = None
            value, source = profile.probability(code), DEFAULT
        stage_rates[code] = value
        book.add(
            Rate(
                name=f"win_within_horizon:{code}",
                value=value,
                definition=f"cumulative incidence of a win within {horizon} days of a snapshot for "
                f"deals open in {profile.stage_name(code)} (losses compete; deals still open are "
                "counted for the days observed)",
                numerator=f"{ci.wins if ci else 0} wins observed within {horizon} days",
                denominator=f"{ci.n if ci else 0} deals open in {code} at their first snapshot in "
                f"the trailing {months} months ({ci.still_open if ci else 0} still open at the cutoff)",
                cohort=cohort_text,
                horizon=f"{horizon} days",
                sample_size=ci.n if ci else 0,
                source=source,
                low95=low,
                high95=high,
                label=profile.stage_name(code),
            )
        )

    m = Decimal(params.smoothing)
    cells: dict[tuple[str, str], Decimal] = {}
    cell_timings = {}
    for (code, group), pairs in sorted(cell_seen.items()):
        if code not in stage_rates:
            continue
        ci = incidence(pairs, f"stage {code}, aged {group}")
        n_eff = Decimal(f"{ci.effective_n:.6f}")
        cells[(code, group)] = (n_eff * ci.value + m * stage_rates[code]) / (n_eff + m)
        rate_n[(code, group)] = ci.effective_n + params.smoothing
        if ci.wins >= params.min_timing_samples:
            cell_timings[(code, group)] = ci.timing
        book.add(
            Rate(
                name=f"win_within_horizon:{code}:{group}",
                value=cells[(code, group)],
                definition=f"stage {code} cumulative incidence for deals aged {group}, shrunk toward "
                f"the stage rate with {params.smoothing} pseudo-observations",
                numerator=f"{ci.wins} wins observed within {horizon} days (+{params.smoothing} x stage rate)",
                denominator=f"{ci.n} deals open in {code} aged {group} ({n_eff:.1f} effective after "
                f"censoring, +{params.smoothing})",
                cohort=cohort_text,
                horizon=f"{horizon} days",
                sample_size=ci.n,
                source=FITTED,
            )
        )

    pooled = incidence(
        [p for pairs in stage_seen.values() for p in pairs],
        "pooled across stages",
    ).timing
    timings = {}
    for code in profile.open_codes:
        ci = stage_ci.get(code)
        if ci is not None and ci.wins >= params.min_timing_samples:
            timings[code] = ci.timing
        else:
            timings[code] = Timing(
                pooled.samples,
                f"pooled across stages (fewer than {params.min_timing_samples} wins in {code})",
                pooled.weights,
            )
    new = _new_pipeline_recency(data, cutoff, params, book)
    return Model(
        cutoff, params, book, cells, stage_rates, timings, new, unknown, len(snapshots),
        cell_timings, rate_n,
    )  # fmt: skip


def _new_pipeline_recency(
    data: Dataset, cutoff: date, params: FitParams, book: RateBook
) -> NewPipeline:
    """The creation cohort under RECENCY: deals created in the trailing months,
    each observed from its creation date, young ones included."""
    horizon, months = params.horizon_days, params.recency_months
    start = add_months(cutoff, -months)
    cohort = [d for d in data.deals if start < d.created <= cutoff]
    outcomes = [_outcome(d, d.created, cutoff) for d in cohort]
    ci = cumulative_incidence(outcomes, horizon, "days from creation to win")
    wins = [d for d, (days, o) in zip(cohort, outcomes) if o == WIN and days <= horizon]
    first_amount = creation_amounts(data)
    created_amounts = [
        first_amount[d.id] for d in cohort if first_amount.get(d.id) is not None
    ]
    trailing_start = cutoff - timedelta(days=params.trailing_days)
    created_recent = sum(1 for d in data.deals if trailing_start < d.created <= cutoff)
    per_day = Decimal(created_recent) / Decimal(params.trailing_days)
    cohort_text = f"new-business deals created {start + timedelta(days=1)} to {cutoff}"
    n = len(cohort)
    low, high = wilson_interval(float(ci.value), ci.effective_n) if n else (None, None)
    day_weight = dict(zip(ci.timing.samples, ci.timing.weights or ()))
    per_day_wins: dict[int, int] = defaultdict(int)
    for d in wins:
        per_day_wins[(d.close - d.created).days] += 1
    won_weights = tuple(
        day_weight[(d.close - d.created).days]
        / per_day_wins[(d.close - d.created).days]
        for d in wins
    )
    total_weight = sum(won_weights, Decimal(0))
    mean_won = (
        sum((w * d.arr for w, d in zip(won_weights, wins)), Decimal(0)) / total_weight
        if total_weight
        else Decimal(0)
    )
    mean_created = _mean(created_amounts)
    for name, value, (definition, source), num, den, horizon_text, size, rng in (
        (
            "new_pipeline_win_rate", ci.value,
            _evidence(n, f"cumulative incidence of a win within {horizon} days of creation "
                         "(losses compete; deals still open are counted for the days observed)"),
            f"{ci.wins} wins observed within {horizon} days",
            f"{n} deals created ({ci.still_open} still open at the cutoff)",
            f"{horizon} days", n, (low, high),
        ),
        (
            "mean_won_arr", mean_won,
            _evidence(len(wins), "mean booked ARR of a created deal that is won, each win "
                                 "weighted by its day's incidence increment"),
            "booked ARR of those wins", f"{len(wins)} wins observed", f"{horizon} days",
            len(wins), (None, None),
        ),
        (
            "mean_created_arr", mean_created,
            _evidence(len(created_amounts), f"mean ARR of a created deal ({CREATION_AMOUNT_BASIS})"),
            "ARR of created deals", f"{len(created_amounts)} deals with a known amount",
            "at creation", len(created_amounts), (None, None),
        ),
    ):  # fmt: skip
        book.add(
            Rate(
                name=name, value=value, definition=definition, numerator=num,
                denominator=den, cohort=cohort_text, horizon=horizon_text,
                sample_size=size, source=source, low95=rng[0], high95=rng[1],
                label=NEW_PIPELINE_LABEL if name == "new_pipeline_win_rate" else None,
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
    return NewPipeline(
        ci.value, ci.timing, mean_won, mean_created, per_day, tuple(d.arr for d in wins), n,
        ci.effective_n if n else 0.0, created_recent, params.trailing_days, won_weights,
        tuple(d.segment for d in wins),
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
                label=NEW_PIPELINE_LABEL if name == "new_pipeline_win_rate" else None,
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
        win_rate, timing, mean_won, mean_created, per_day, tuple(d.arr for d in wins), n,
        float(n), created_recent, params.trailing_days, None,
        tuple(d.segment for d in wins),
    )  # fmt: skip


def _evidence(n: int, definition: str) -> tuple[str, str]:
    """(definition, source) for a rate that is undefined without evidence: with
    no sample it is a default of 0, never presented as fitted."""
    if n:
        return definition, FITTED
    return f"{definition} (no evidence: set to 0)", DEFAULT


def _mean(values) -> Decimal:
    values = list(values)
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else Decimal(0)
