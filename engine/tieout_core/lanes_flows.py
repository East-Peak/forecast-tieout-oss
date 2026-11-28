"""Expected wins, by the quarter they land in and the quarter their deal was created in.

The forward function says how many dollars a quarter is expected to book; a lane also needs how
many wins that is, how long they take, and which of them come from pipeline carried in and which
from pipeline created in the period. This module replays the forward function's own arithmetic
(an open deal's win rate times its timing curve; a created deal's win rate times the new-pipeline
curve) one deal and one day at a time, so each expectation can be given to a segment and to an
origin. A win is keyed ``(segment, quarter it lands in, origin)``: origin 0 is a deal created
before the fiscal year, 1 to 4 the quarter it was created in. Everything is an exact decimal.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import accumulate

from .fiscal import FiscalYear, Window
from .fit import Timing
from .forecast import Inflow
from .history import UNKNOWN_STAGE
from .records import Deal

ZERO = Decimal(0)
AFTER_THE_YEAR = 5
Leaf = tuple[str, int, int]


@dataclass(frozen=True)
class Flow:
    wins: Decimal
    bookings: Decimal
    days: Decimal  # expected days from creation to close, summed over the wins

    def __add__(self, other: Flow) -> Flow:
        return Flow(
            self.wins + other.wins,
            self.bookings + other.bookings,
            self.days + other.days,
        )


ZERO_FLOW = Flow(ZERO, ZERO, ZERO)


@dataclass(frozen=True)
class Calendar:
    """The fiscal year's four quarters, and which of them a date belongs to."""

    year: FiscalYear

    @property
    def quarters(self) -> tuple[Window, ...]:
        return tuple(self.year.quarter_window(k) for k in self.year.quarter_keys)

    @property
    def start(self) -> date:
        """The last day before the year: a deal created on or before it is carried in."""
        return self.year.start - timedelta(days=1)

    def bucket(self, d: date) -> int:
        if d <= self.start:
            return 0
        return next(
            (i for i, w in enumerate(self.quarters, 1) if w.contains(d)), AFTER_THE_YEAR
        )


class Mass:
    """A timing curve's cumulative mass and day-weighted mass: the share of wins that land
    within ``days`` of the start, and the days they take, both per unit of total weight."""

    def __init__(self, timing: Timing) -> None:
        self.samples = timing.samples
        weights = timing.weights or (Decimal(1),) * len(timing.samples)
        total = Decimal(timing.total)
        self.mass = [ZERO, *(c / total for c in accumulate(weights))]
        days = (w * s for w, s in zip(weights, self.samples))
        self.moment = [ZERO, *(m / total for m in accumulate(days))]

    def through(self, days: int) -> tuple[Decimal, Decimal]:
        k = bisect_right(self.samples, days) if days >= 0 else 0
        return self.mass[k], self.moment[k]


def apportion(
    total: Decimal, weights: Sequence[Decimal], places: str = "0.01"
) -> list[Decimal]:
    """``total`` shared in proportion to ``weights`` in whole units of ``places``, the largest
    remainders taking the leftover units, so the pieces add to the total exactly."""
    unit = Decimal(places)
    weight = sum(weights, ZERO)
    if not weight:
        if total:
            raise ValueError("nothing to share a total over")
        return [ZERO.quantize(unit) for _ in weights]
    exact = [total * w / weight / unit for w in weights]
    floors = [int(x // 1) for x in exact]
    left = int(total / unit) - sum(floors)
    order = sorted(
        range(len(exact)), key=lambda i: (exact[i] - floors[i], -i), reverse=True
    )
    for i in order[:left]:
        floors[i] += 1
    return [f * unit for f in floors]


def _offsets(w: Window, as_of: date) -> tuple[int, int]:
    """The days after ``as_of`` that a quarter covers, from its first to its last."""
    return max((w.start - as_of).days, 0), (w.end - as_of).days


def existing_flows(
    model, deals: Sequence[Deal], as_of: date, cal: Calendar
) -> dict[Leaf, Flow]:
    """What the deals open on ``as_of`` are expected to win in each quarter, from their own
    segment. A deal with no stage on record is left out, as the forecast leaves it out."""
    out: dict[Leaf, Flow] = defaultdict(lambda: ZERO_FLOW)
    masses: dict[int, Mass] = {}
    for d in deals:
        if d.is_closed or d.stage == UNKNOWN_STAGE or d.arr is None:
            continue
        age = (as_of - d.created).days
        timing = model.timing(d.stage, age)
        mass = masses.setdefault(id(timing), Mass(timing))
        p, origin = model.win_rate(d.stage, age), cal.bucket(d.created)
        for q, w in enumerate(cal.quarters):
            lo, hi = _offsets(w, as_of)
            if hi <= lo:
                continue
            (m0, d0), (m1, d1) = mass.through(lo), mass.through(hi)
            wins = p * (m1 - m0)
            if wins:
                days = p * (age * (m1 - m0) + d1 - d0)
                out[(d.segment, q, origin)] += Flow(wins, d.arr * wins, days)
    return dict(out)


def new_flows(
    model, series: Mapping[str, Sequence[Decimal]], as_of: date, cal: Calendar
) -> tuple[dict[Leaf, Flow], dict[tuple[str, int], Decimal]]:
    """What deals not yet created are expected to win, and how many are created in each
    quarter, from ``series`` (deals created on each day after ``as_of``, by segment). Wins are
    at the pooled size; a lane prices them for its segment afterwards."""
    new = model.new_pipeline
    mass = Mass(new.timing)
    out: dict[Leaf, Flow] = defaultdict(lambda: ZERO_FLOW)
    created: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
    for segment, per_day in series.items():
        for t, count in enumerate(per_day, 1):
            origin = cal.bucket(as_of + timedelta(days=t))
            if origin == AFTER_THE_YEAR:
                break
            created[(segment, origin)] += count
            if not count:
                continue
            for q, w in enumerate(cal.quarters):
                lo, hi = _offsets(w, as_of)
                (m1, d1), (m0, d0) = mass.through(hi - t), mass.through(lo - t)
                wins = count * new.win_rate * (m1 - m0)
                if wins:
                    days = count * new.win_rate * (d1 - d0)
                    out[(segment, q, origin)] += Flow(
                        wins, wins * new.mean_won_arr, days
                    )
    return dict(out), dict(created)


def inflow_series(
    inflows: Sequence[Inflow], mean_created_arr: Decimal, horizon: int
) -> list[Decimal]:
    """Deals created on each of ``horizon`` days by dollars of program pipeline, as the forward
    function converts them: dollars over their days over the pooled created size."""
    out = [ZERO] * horizon
    if not mean_created_arr:
        return out
    for flow in inflows:
        per_day = flow.dollars / Decimal(flow.end - flow.start) / mean_created_arr
        for t in range(flow.start, min(flow.end, horizon)):
            out[t] += per_day
    return out


def segment_series(
    organic: Mapping[str, Sequence[Decimal]],
    inflow: Sequence[Decimal],
    shares: Mapping[str, Decimal],
) -> dict[str, list[Decimal]]:
    """Each segment's deals created per day: its own organic creation plus its share of the
    programs' (a program names no segment, so it is split by the frozen creation shares)."""
    return {
        s: [o + shares.get(s, ZERO) * i for o, i in zip(per_day, inflow)]
        for s, per_day in organic.items()
    }
