"""The forward function: three forecasts over the same windows.

Each forecast keeps its parts apart: what the pipeline open at the cutoff is
expected to book, what pipeline not yet created is assumed to book, and (for
the fitted model only) what pipeline added by the lever would book.
Expectations are exact decimals; the ranges come from a seeded simulation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

import numpy as np

from .fiscal import Window
from .fit import Model, Timing
from .history import CREATION_AMOUNT_BASIS, UNKNOWN_STAGE, creation_amounts
from .rates import ENTERED, FITTED, Rate
from .records import Check, Dataset, Profile

EXISTING = "existing pipeline"
FUTURE = "future pipeline"
ADDED = "added pipeline"
ACTIONS = "driver actions"
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


@dataclass(frozen=True)
class Creation:
    """Pipeline not yet created, by day: the deals created on each day after the
    cutoff (offsets 1..H). ``draws``, when given, returns a (draws, H) matrix of
    the same quantity with future departures drawn at random, centered on
    ``per_day``; the headline uses ``per_day`` and the ranges use the draws."""

    per_day: tuple[Decimal, ...]
    text: str
    ramped_ae_months: tuple[Decimal, ...] = ()  # expected ramped AE-months on each day
    heads: tuple[Decimal, ...] = ()  # expected people employed on each day
    departures: tuple[Decimal, ...] = ()  # expected last days of employment on each day
    draws: Callable[[np.random.Generator, int], np.ndarray] | None = field(
        default=None, compare=False, repr=False
    )


@dataclass(frozen=True)
class Inflow:
    """Dollars of pipeline created evenly over the days (start, end] after the cutoff."""

    start: int
    end: int
    dollars: Decimal


@dataclass(frozen=True)
class Lift:
    """Changes to pipeline not yet created, segment by segment: what the plan's driver actions
    do to it.

    ``organic`` and ``program`` are the deals each segment is expected to create on each day
    after the cutoff (day 1 first), from its people and from programs; ``changes`` the points
    added to the pooled win rate ``baseline`` on each day, and ``size`` the relative change in
    the size of each win and ``creation`` the relative change in the organic deals created (0.1
    is a tenth bigger, or more): the deals a segment's own people create, not programs'. A win books at the pooled mean won size times
    ``price``, a segment's frozen price index by (the window it lands in, the fiscal quarter its
    deal was created in), 1 where none is given; ``landing`` names the window each day after the
    cutoff falls in and ``origin`` its fiscal quarter. A day on which a driver is not changed
    has zero for it; a driver no action touches may be left out."""

    baseline: Decimal
    organic: Mapping[str, Sequence[Decimal]]
    program: Mapping[str, Sequence[Decimal]]
    changes: Mapping[str, Sequence[Decimal]]
    price: Mapping[str, Mapping[tuple[int, int], Decimal]]
    landing: Sequence[int]
    origin: Sequence[int]
    size: Mapping[str, Sequence[Decimal]] = field(default_factory=dict)
    creation: Mapping[str, Sequence[Decimal]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return any(
            any(c)
            for column in (self.changes, self.size, self.creation)
            for c in column.values()
        )

    def counts(self, segment: str) -> list[Decimal]:
        return [o + p for o, p in zip(self.organic[segment], self.program[segment])]

    def created(self, segment: str) -> tuple[Decimal, ...]:
        """The deals ``segment`` is expected to create on each day, with the change in its
        organic creation."""
        grown = self.creation.get(segment)
        if not grown or not any(grown):
            return tuple(self.counts(segment))
        return tuple(
            c + o * u
            for c, o, u in zip(self.counts(segment), self.organic[segment], grown)
        )

    def extra(self, segment: str, landing: int) -> list[Decimal]:
        """The extra bookings, in units of the pooled mean won size, expected from the deals
        ``segment`` creates on each day, for wins landing in window ``landing``. Every win in a
        segment has one price, its frozen index, whoever created it: the deals it was to create,
        and the organic deals its change adds or takes away, are won at the rate and size the day's
        changes leave. A win-rate change alone is the deals times the change times the price. A
        segment never books below zero: it can lose at most the organic wins it had."""
        return self.extra_of(
            segment, landing, self.counts(segment), self.organic[segment]
        )

    def extra_of(
        self,
        segment: str,
        landing: int,
        count: Sequence[Decimal],
        organic: Sequence[Decimal],
    ) -> list[Decimal]:
        """``extra`` for any of the segment's lanes (an owner, say): the deals ``count`` it creates
        on each day, of which ``organic`` are its people's, under the segment's changes."""
        change = self.changes[segment]
        size = self.size.get(segment) or ()
        grown = self.creation.get(segment) or ()
        out = [Decimal(0)] * len(self.origin)
        if not (any(change) or any(size) or any(grown)):
            return out
        price = self.price.get(segment, {})
        for t, c in enumerate(change):
            z = size[t] if size else 0
            u = grown[t] if grown else 0
            if (c or z or u) and t < len(count):
                moved = c * (1 + z) + self.baseline * z if z else c
                value = count[t] * moved
                if u:
                    value += organic[t] * u * (self.baseline + c) * (1 + z)
                out[t] = value * price.get((landing, self.origin[t]), Decimal(1))
        return out

    def extra_wins(self, segment: str) -> list[Decimal]:
        """The extra wins expected from the deals ``segment`` creates on each day: its deals
        times the change in the rate, and the organic deals its change adds times the rate."""
        return self.extra_wins_of(segment, self.counts(segment), self.organic[segment])

    def extra_wins_of(
        self, segment: str, count: Sequence[Decimal], organic: Sequence[Decimal]
    ) -> list[Decimal]:
        """``extra_wins`` for any of the segment's lanes, as ``extra_of``."""
        change = self.changes[segment]
        grown = self.creation.get(segment)
        out = [n * c for n, c in zip(count, change)]
        if grown and any(grown):
            base = self.baseline
            out = [
                w + o * u * (base + c) if u else w
                for w, o, u, c in zip(out, organic, grown, change)
            ]
        return out

    def priced(self, landing: int) -> list[Decimal]:
        """Extra wins on each day of creation for wins landing in window ``landing``, each at its
        price index and size."""
        out = [Decimal(0)] * len(self.origin)
        for s in self.changes:
            for t, x in enumerate(self.extra(s, landing)):
                if x:
                    out[t] += x
        return out

    def rebased(self, rate: Decimal) -> Lift:
        """The same changes in points on a pooled win rate of ``rate``, the rate each day's
        deals are won at held between zero and one."""
        if rate == self.baseline:
            return self
        one, zero = Decimal(1), Decimal(0)
        moved = {
            s: tuple(min(max(rate + c, zero), one) - rate for c in change)
            for s, change in self.changes.items()
        }
        return replace(self, baseline=rate, changes=moved)

    def scaled(self, organic: Decimal) -> Lift:
        """The same with each segment's organic creation (not programs') multiplied."""
        if organic == 1:
            return self
        return replace(
            self,
            organic={s: tuple(x * organic for x in v) for s, v in self.organic.items()},
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
    amounts = creation_amounts(data)
    if any(amounts[d.id] is None for d in created):
        return _unavailable(
            method, "amounts of recently created deals at creation are not recorded"
        )
    created_arr = sum((amounts[d.id] for d in created), Decimal(0))
    created_per_day = created_arr / Decimal(trailing_days)
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
        (
            "open deals book at their amount times the profile's stage probability (stages.yaml), "
            "in the month of their expected close; past-due deals count in the first month"
        ),
        (
            f"new pipeline is created at {created_per_day:.2f} ARR per day (trailing {trailing_days} days) "
            f"and converts at the {profile.stage_name(first_stage)} probability {p_first}, {cycle_text}"
        ),
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
            f"{created_arr:.2f} ARR created ({CREATION_AMOUNT_BASIS})", f"{trailing_days} days",
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
    added_through: date | None = None,
    creation: Creation | None = None,
    inflows: Sequence[Inflow] = (),
    existing: dict[str, Decimal] | None = None,
    lift: Lift | None = None,
) -> Forecast:
    """``lift`` is the plan's win-rate actions: the extra wins expected from the deals created on
    each day after the cutoff, each at the mean won size and its price index, booking on the
    timing of any other new win. ``added_pipeline`` is created in equal parts in each window that ends by
    ``added_through`` (every window by default) and books in any window.
    ``inflows`` are further dollars created over given day ranges (programs,
    quarterly requirements). ``creation``, when given, replaces the flat
    trailing creation rate of pipeline not yet created. ``existing``, when given, is the
    existing-pipeline component of an earlier forecast from the same model, deals and windows
    (it does not depend on anything a caller varies here), so it is not computed again."""
    method = "fitted model"
    all_open = [d for d in data.deals if not d.is_closed]
    if any(d.arr is None for d in all_open):
        return _unavailable(method, "open-deal amounts at this date are not recorded")
    open_deals = [d for d in all_open if d.stage != UNKNOWN_STAGE]
    unknown = len(all_open) - len(open_deals)
    if windows:
        # Missing evidence is not an observed zero: say so instead of forecasting $0.
        no_timing = sorted(
            {
                d.stage
                for d in open_deals
                if not model.timing(d.stage, (cutoff - d.created).days).samples
            }
        )
        if no_timing:
            return _unavailable(
                method,
                f"no close-timing evidence for open deals in {', '.join(no_timing)}",
            )
        if model.new_pipeline.cohort_size == 0:
            return _unavailable(
                method,
                f"no matured creation cohort (deals created at least {model.params.horizon_days} "
                "days before the cutoff), so future pipeline cannot be fitted",
            )
    offsets = [
        (
            w.start.toordinal() - cutoff.toordinal(),
            w.end.toordinal() - cutoff.toordinal(),
        )
        for w in windows
    ]

    if existing is None:
        existing = _zeros(windows)
        for d in open_deals:
            p = model.win_rate(d.stage, (cutoff - d.created).days)
            timing = model.timing(d.stage, (cutoff - d.created).days)
            for w, (a, b) in zip(windows, offsets):
                existing[w.label] += d.arr * p * (timing.cdf(b) - timing.cdf(a))

    new = model.new_pipeline
    future = _zeros(windows)
    added = _zeros(windows)
    n = new.timing.total
    if n and windows:
        horizon_end = offsets[-1][1]
        per_created_deal = (
            new.win_rate * new.mean_won_arr / Decimal(n)
        )  # per unit of timing mass
        for w, (a, b) in zip(windows, offsets):
            if creation is None:
                hits = sum(
                    new.timing.count_through(b - t) - new.timing.count_through(a - t)
                    for t in range(1, horizon_end + 1)
                )
                future[w.label] = new.created_per_day * per_created_deal * hits
            else:
                future[w.label] = per_created_deal * sum(
                    (
                        creation.per_day[t - 1]
                        * (
                            new.timing.count_through(b - t)
                            - new.timing.count_through(a - t)
                        )
                        for t in range(1, horizon_end + 1)
                    ),
                    Decimal(0),
                )
        spread = [
            o
            for w, o in zip(windows, offsets)
            if added_through is None or w.end <= added_through
        ]
        flows = list(inflows)
        if added_pipeline and spread:
            per_window = added_pipeline / Decimal(len(spread))
            flows += [Inflow(sa, sb, per_window) for sa, sb in spread]
        if new.mean_created_arr:
            for flow in flows:
                deals_per_day = (
                    flow.dollars / Decimal(flow.end - flow.start) / new.mean_created_arr
                )
                for w, (a, b) in zip(windows, offsets):
                    hits = sum(
                        new.timing.count_through(b - t)
                        - new.timing.count_through(a - t)
                        for t in range(flow.start + 1, flow.end + 1)
                    )
                    added[w.label] += deals_per_day * per_created_deal * hits

    lifted = _zeros(windows)
    if n and windows and lift:
        per_win = new.mean_won_arr / Decimal(n)
        for i, (w, (a, b)) in enumerate(zip(windows, offsets)):
            extra = lift.priced(i)
            lifted[w.label] = per_win * sum(
                (
                    extra[t - 1]
                    * (
                        new.timing.count_through(b - t)
                        - new.timing.count_through(a - t)
                    )
                    for t in range(1, min(offsets[-1][1], len(extra)) + 1)
                ),
                Decimal(0),
            )
    components = {EXISTING: existing, FUTURE: future}
    if added_pipeline or inflows:
        components[ADDED] = added
    if lift:
        components[ACTIONS] = lifted
    creation_text = (
        f"new pipeline is created at {new.created_per_day:.4f} deals per day"
        if creation is None
        else creation.text
    )
    assumptions = (
        (
            "open deals book at their current amount times the fitted win rate for their stage and age, "
            "on the fitted close-timing distribution"
        ),
        (
            f"{creation_text} and wins at the fitted "
            f"creation-cohort rate {new.win_rate:.4f}, averaging {new.mean_won_arr:.2f} ARR per win"
        ),
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
    forecast = model_forecast(
        model, Dataset(tuple(open_deals), (), None), cutoff, windows
    )
    if not forecast.available:
        return Check(
            "existing pipeline conserved",
            True,
            f"not applicable: {forecast.unavailable_reason}",
        )
    inside = forecast.components[EXISTING]
    end = windows[-1].end.toordinal() - cutoff.toordinal()
    later = not_won = Decimal(0)
    for d in open_deals:
        p = model.win_rate(d.stage, (cutoff - d.created).days)
        later += (
            d.arr * p * (1 - model.timing(d.stage, (cutoff - d.created).days).cdf(end))
        )
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


def _beta(rng: np.random.Generator, p: float, n: float, draws: int) -> np.ndarray:
    """A rate with mean ``p`` resting on ``n`` effective observations; fixed when
    it rests on none or sits at 0 or 1."""
    if n <= 0 or p <= 0 or p >= 1:
        return np.full(draws, p)
    return rng.beta(p * n, (1 - p) * n, draws)


def _draw_days(rng: np.random.Generator, timing: Timing, size: int) -> np.ndarray:
    """Days to a win drawn from ``timing``: uniformly over its samples, or by
    their weights."""
    samples = np.asarray(timing.samples)
    if timing.weights is None:
        return samples[rng.integers(0, len(samples), size)]
    p = np.asarray([float(w) for w in timing.weights])
    return samples[rng.choice(len(samples), size=size, p=p / p.sum())]


def _price_grid(index, landing_of: np.ndarray, origin_of: np.ndarray) -> np.ndarray:
    """A price index as an array by (window landed in, quarter created in), 1 where none is given."""
    grid = np.ones((landing_of.max() + 1, origin_of.max() + 1))
    for (landing, origin), value in index.items():
        grid[landing, origin] = float(value)
    return grid


def _draw_lifted(rng, new, lift: Lift, deals, span: int, book, organic, extra) -> None:
    """Book the wins of new pipeline when a ``lift`` changes some segments' drivers. ``deals`` is
    each path's expected creation by day, made of ``organic`` (random departures drawn) and
    ``extra`` (programs'); every segment takes its expected share of it. A segment whose organic
    creation changes takes the same share of the organic part, more or less of it (fewer deals are
    the organic ones kept, each with the probability the change leaves: a thinned Poisson is a
    Poisson at the lower rate), and its share of the programs' as it was. A segment's deals are won
    at the pooled rate plus its own change on the day they are created, and a win's size is scaled
    by its segment's one price index (the window it lands in, the quarter it was created in) and by
    the change in size its segment's actions make on the day its deal was created. How many are won
    and what each books are drawn apart, so the draws are centered on the forward function's
    expectation: the segments' prices add back to the pooled price over each quarter's wins. Every
    win books a positive amount, so no path books below zero."""
    names = list(lift.changes)
    count = np.array([[float(x) for x in lift.counts(s)[:span]] for s in names])
    change = np.array([[float(x) for x in lift.changes[s][:span]] for s in names])
    bigger = np.array(
        [[1 + float(x) for x in lift.size.get(s, [0] * span)[:span]] for s in names]
    )
    made = count.sum(axis=0)
    share = np.divide(count, made, out=np.zeros_like(count), where=made > 0)
    landing_of, origin_of = np.asarray(lift.landing), np.asarray(lift.origin)
    grown = np.array(
        [[float(x) for x in lift.creation.get(s, [0] * span)[:span]] for s in names]
    )
    if grown.any():  # the organic deals and the programs' are shared out apart
        mine = np.array([[float(x) for x in lift.organic[s][:span]] for s in names])
        whole = mine.sum(axis=0)
        organic_share = np.divide(mine, whole, out=np.zeros_like(mine), where=whole > 0)
        ours = np.array([[float(x) for x in lift.program[s][:span]] for s in names])
        all_programs = ours.sum(axis=0)
        program_share = np.divide(
            ours, all_programs, out=np.zeros_like(ours), where=all_programs > 0
        )
    pool = np.asarray([float(x) for x in new.won_arr_samples])
    if new.won_arr_weights is None:
        weights = np.full(len(pool), 1 / len(pool))
    else:
        weights = np.asarray([float(w) for w in new.won_arr_weights])
        weights = weights / weights.sum()
    base = float(new.win_rate)
    for i, name in enumerate(names):
        grid = _price_grid(lift.price.get(name, {}), landing_of, origin_of)
        if grown[i].any():
            mine_i = (
                organic * (organic_share[i] * (1 + grown[i])) + extra * program_share[i]
            )
        else:
            mine_i = deals * share[i]
        wins = rng.poisson(mine_i * (base + change[i]))
        row_of, day_of = np.nonzero(wins)
        repeats = wins[row_of, day_of].astype(np.intp)
        rows = np.repeat(row_of, repeats)
        created = np.repeat(day_of + 1, repeats)
        days = _draw_days(rng, new.timing, len(rows))
        sizes = pool[rng.choice(len(pool), size=len(rows), p=weights)]
        landing = created + days
        land = landing_of[np.minimum(landing, len(landing_of)) - 1]
        book(
            rows,
            landing,
            sizes * grid[land, origin_of[created - 1]] * bigger[i][created - 1],
        )


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
    parameter_uncertainty: bool = False,
    creation: Creation | None = None,
    inflows: Sequence[Inflow] = (),
    lift: Lift | None = None,
) -> Simulation:
    """Draw outcomes from the fitted model: each open deal wins or not and, if
    it wins, closes after a day count drawn from its timing; future wins arrive
    as a Poisson process with sizes drawn from past wins.

    With ``parameter_uncertainty`` each draw first draws the rates themselves:
    each win rate from a beta with the fitted mean and its effective sample
    (shared by every deal using that rate in the draw), the creation rate from
    a gamma on its count, and the mean win size by bootstrap. All keep their
    means, so the simulation stays centered on the expectation. Close timing is
    not drawn. With ``creation`` the creation rate is the given day-by-day one
    (departures drawn at random when it can) instead of the flat trailing rate,
    and its own count-based uncertainty is not drawn. With a ``lift`` each segment's
    share of every simulated path's creation is won at that segment's resulting
    probability, so the draws are conditional on the changes having been made;
    whether they are made is not drawn. A win's price is kept apart from whether it
    is won: its size is scaled by the segment's price index, which does not change
    how many are won."""
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

    rate_draws: dict = {}
    for d in data.deals:
        if d.is_closed or d.stage == UNKNOWN_STAGE or d.arr is None:
            continue
        age = (cutoff - d.created).days
        timing = model.timing(d.stage, age)
        if not timing.samples:
            continue
        p = float(model.win_rate(d.stage, age))
        if parameter_uncertainty:
            key = model.rate_key(d.stage, age)
            if key not in rate_draws:
                rate_draws[key] = _beta(rng, p, model.rate_n.get(key, 0.0), draws)
            p = rate_draws[key]
        won = rng.random(draws) < p
        days = _draw_days(rng, timing, draws)
        book(draw_index[won], days[won], np.full(int(won.sum()), float(d.arr)))

    new = model.new_pipeline
    if new.timing.samples and new.won_arr_samples:
        span = int(ends[-1])
        extra = np.zeros(span)  # deals created per day by program inflows
        if inflows and new.mean_created_arr:
            for flow in inflows:
                lo, hi = max(flow.start, 0), min(flow.end, span)
                if hi > lo:
                    extra[lo:hi] += float(
                        flow.dollars
                        / Decimal(flow.end - flow.start)
                        / new.mean_created_arr
                    )
        if lift and parameter_uncertainty:
            raise ValueError(
                "a lift is drawn with fixed rates, not with their uncertainty"
            )
        if creation is None and not extra.any() and not lift:
            lam = float(new.created_per_day * new.win_rate) * span
            if parameter_uncertainty:
                per_day = (
                    rng.gamma(new.created_count, 1 / new.created_days, draws)
                    if new.created_count and new.created_days
                    else np.full(draws, float(new.created_per_day))
                )
                lam = (
                    per_day
                    * _beta(rng, float(new.win_rate), new.win_rate_n, draws)
                    * span
                )
            counts = rng.poisson(lam, draws)
            total = int(counts.sum())
            # counts are cast to the platform integer: 32-bit WebAssembly refuses a wider count array
            rows = np.repeat(draw_index, counts.astype(np.intp))
            created = rng.integers(1, span + 1, total)
        else:
            if creation is None:
                per_day = np.full(span, float(new.created_per_day))
            else:
                per_day = np.asarray([float(x) for x in creation.per_day[:span]])
            organic = (
                creation.draws(rng, draws)[:, :span]
                if creation is not None and creation.draws is not None
                else np.tile(per_day, (draws, 1))
            )
            deals = organic + extra
            win_rate = float(new.win_rate)
            if parameter_uncertainty:
                win_rate = _beta(rng, win_rate, new.win_rate_n, draws)[:, None]
            if lift:
                _draw_lifted(rng, new, lift, deals, span, book, organic, extra)
                rows = created = np.zeros(0, dtype=np.intp)  # booked by segment above
                total = 0
            else:
                cell = rng.poisson(deals * win_rate)
                row_of, day_of = np.nonzero(cell)
                repeats = cell[row_of, day_of]
                rows = np.repeat(row_of, repeats.astype(np.intp))
                created = np.repeat(day_of + 1, repeats.astype(np.intp))
                total = len(rows)
        days = _draw_days(rng, new.timing, total)
        pool = np.asarray([float(x) for x in new.won_arr_samples])
        if new.won_arr_weights is None:
            sizes = pool[rng.integers(0, len(pool), total)]
            weights = np.full(len(pool), 1 / len(pool))
        else:
            weights = np.asarray([float(w) for w in new.won_arr_weights])
            weights = weights / weights.sum()
            sizes = pool[rng.choice(len(pool), size=total, p=weights)]
        if parameter_uncertainty:  # each draw's mean win size, by (weighted) bootstrap
            picks = rng.choice(len(pool), size=(draws, len(pool)), p=weights)
            sizes = sizes * (pool[picks].mean(axis=1) / float(pool @ weights))[rows]
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
