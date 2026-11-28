"""Actions on a slice: what a change to the win rate of one segment (or the company) is
expected to add, from the day it starts.

The model fits one pooled win rate, so an action is an entered change, not a segment's fit. It
applies to deals created on or after its start, and ramps linearly by creation date: on the
``k``-th day from the start (the start day is the first) the change is ``k`` over the days in the
ramp's months, at most all of it, and a ramp of zero months is all of it from the start day. Deals
created earlier, and every deal already open, keep the rate they had. A change of ``d`` points on
a day on which a segment creates ``c`` deals is ``c * d`` more expected wins.

Wins are priced at the pooled mean won size times the segment's price index, which is frozen:
the no-action plan's wins priced as the lanes share the pooled bookings out (by segment size) in
each month they land in and each fiscal quarter they were created in, over the whole horizon.
Within every one of those cells the segments' prices add back to the pooled price, so a company
action books what changing the pooled rate would; a zero target removes exactly the wins it
changes, and leaves no month below zero; a
segment's action moves nothing in another segment; and the company's action is the same action in
every segment. The actions' bookings are added to the company forecast, not shared out of it.

Everything is an exact decimal. ``Lift`` (in the forward function's module) is what the forward
function reads: each segment's deals and change in win rate by day, and the frozen prices.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from . import lanes_basis
from . import lanes_flows as flows
from . import lanes_rules as rules
from . import worksheet_drivers as wd
from .actions import Ground
from .capacity import project
from .cycle import Transport, exact_mean
from .figures import CENT, cents, money, number
from .fiscal import add_months
from .forecast import Inflow, Lift
from .lanes_basis import Basis, Sizes
from .lanes_flows import Calendar
from .plan import NEXT_12, REST_OF_FY, ActionRefused, Plan, PlanAction, month_words
from .records import Check
from .roster import Member
from .worksheet_drivers import Probe
from .worksheet_rules import CYCLE_DAYS, PRECISION, PRODUCTIVITY, WIN_RATE, WON_ARR

ZERO, ONE = Decimal(0), Decimal(1)
DRIVERS = (
    WIN_RATE,
    WON_ARR,
    PRODUCTIVITY,
    CYCLE_DAYS,
)  # the order Effect's changes are in
WORDS = {
    WIN_RATE: "the win rate",
    WON_ARR: "won ARR per win",
    PRODUCTIVITY: "creation productivity",
    CYCLE_DAYS: "cycle length",
}
ACTED_ON = {  # "driver actions on ... do not interact"
    WIN_RATE: "a win rate",
    WON_ARR: "won ARR per win",
    PRODUCTIVITY: "creation productivity",
    CYCLE_DAYS: "cycle length",
}
WINDOWS = (REST_OF_FY, NEXT_12)


class Unavailable(ValueError):
    """Actions cannot be valued for this company; the message says why."""


@dataclass(frozen=True)
class Frame:
    """The company by segment as the plan leaves it before any action: the deals each segment is
    expected to create on each day after the as-of date (from its people and from programs), each
    segment's frozen price index by (window landed in, fiscal quarter created in), the window each
    day falls in and its fiscal quarter, counted from the year's first (it can pass three)."""

    segments: tuple[str, ...]
    organic: Mapping[str, Sequence[Decimal]]
    program: Mapping[str, Sequence[Decimal]]
    series: Mapping[str, Sequence[Decimal]]  # the two added, as the lanes add them
    price: Mapping[str, Mapping[tuple[int, int], Decimal]]
    landing: tuple[int, ...]
    origin: tuple[int, ...]
    size: Decimal | None = None  # the pooled mean won ARR a size target is read against
    # the pooled creation rate a productivity target is read against
    productivity: Decimal | None = None
    # the pooled mean days from creation to win a cycle target is read against, and the timing moved
    cycle: Decimal | None = None
    transport: Transport | None = None
    cycle_mean: Fraction | None = (
        None  # the same, exactly: a cycle target is read against it
    )
    # each segment's own won amounts over its mean, for the draws of the simulation
    amounts: (
        Mapping[str, tuple[tuple[Decimal, ...], tuple[Decimal, ...] | None]] | None
    ) = None


@dataclass(frozen=True)
class Effect:
    """What a set of actions does in expectation, over a frame."""

    frame: Frame
    baseline: Decimal  # the pooled win rate they are measured from
    as_of: date
    actions: tuple[PlanAction, ...]
    changes: Mapping[
        str, tuple[Decimal, ...]
    ]  # each segment's change in win rate, by day
    sizes: Mapping[
        str, tuple[Decimal, ...]
    ]  # each segment's relative change in the size of a win, by day
    creation: Mapping[
        str, tuple[Decimal, ...]
    ]  # each segment's relative change in its organic creation, by day
    cycles: Mapping[
        str, tuple[Decimal, ...]
    ]  # each segment's relative change in the lag from creation to win, by day
    lift: Lift  # the changes the forward function reads

    def dropping(self, action: PlanAction) -> Effect:
        """The effect of the others alone."""
        rest = tuple(a for a in self.actions if a.id != action.id)
        return effect(self.frame, self.baseline, self.as_of, rest)


# ---------------------------------------------------------------- the frame


def segments_of(g: Ground, keys: Sequence[str], hires: Sequence[Member]) -> list[str]:
    """The lanes' segments: the basis's, then any more that deals or people bring."""
    people = [*g.cap.members, *hires]
    more = sorted(
        {rules.segment_key(d.segment) for d in g.pop.deals}
        | {rules.segment_key(m.segment) for m in people}
    )
    return [*keys, *(s for s in more if s not in keys)]


def organic_series(
    g: Ground,
    shares: Mapping[str, Decimal],
    hires: Sequence[Member],
    segments: Sequence[str],
    days: int,
) -> dict[str, list[Decimal]]:
    """Deals created on each of ``days`` days after the as-of date by each segment's own people
    (where the capacity term is adopted, with ``hires``) or, where it is not, its frozen share
    of the flat rate."""
    if g.cap.adopted:
        people = [*g.cap.members, *hires]
        return {
            seg: list(
                project(
                    g.cap.fit,
                    [m for m in people if rules.segment_key(m.segment) == seg],
                    g.as_of,
                    g.horizon_days,
                ).per_day[:days]
            )
            for seg in segments
        }
    rate = g.model.new_pipeline.created_per_day
    return {seg: [rate * shares.get(seg, ZERO)] * days for seg in segments}


def program_series(
    g: Ground,
    shares: Mapping[str, Decimal],
    inflows: Sequence[Inflow],
    segments: Sequence[str],
    days: int,
) -> dict[str, list[Decimal]]:
    """Deals the programs create on each day, by segment: a program names none, so each has its
    frozen share of them."""
    extra = flows.inflow_series(inflows, g.model.new_pipeline.mean_created_arr, days)
    return {s: [shares.get(s, ZERO) * i for i in extra] for s in segments}


def creation_series(
    g: Ground,
    shares: Mapping[str, Decimal],
    hires: Sequence[Member],
    inflows: Sequence[Inflow],
    segments: Sequence[str],
    days: int,
) -> dict[str, list[Decimal]]:
    """Deals created on each of ``days`` days after the as-of date, by segment: its organic
    creation and its share of the programs'."""
    organic = organic_series(g, shares, hires, segments, days)
    extra = flows.inflow_series(inflows, g.model.new_pipeline.mean_created_arr, days)
    return flows.segment_series(organic, extra, shares)


def day_cells(
    g: Ground, first_day: date, days: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """For each of ``days`` days after the as-of date, the index of the window it falls in and
    its fiscal quarter counted from the year's first (``first_day``; it can pass three)."""
    landing, origin = [], []
    for t in range(1, days + 1):
        d = g.as_of + timedelta(days=t)
        landing.append(
            next(
                (i for i, w in enumerate(g.windows) if w.contains(d)),
                len(g.windows) - 1,
            )
        )
        origin.append(((d.year - first_day.year) * 12 + d.month - first_day.month) // 3)
    return tuple(landing), tuple(origin)


def price_index(
    g: Ground,
    series: Mapping[str, Sequence[Decimal]],
    sizes: Mapping[str, Sizes],
    origin: Sequence[int],
) -> dict[str, dict[tuple[int, int], Decimal]]:
    """Each segment's price per win over the pooled mean won size, in each (window the win lands
    in, fiscal quarter its deal was created in): the cell's pooled bookings shared out by wins
    times segment size, as the lanes price the fiscal year by quarter. The wins are the no-action
    plan's, by the forward function's timing; a cell with no wins is left out (its index is 1)."""
    timing = g.model.new_pipeline.timing
    ends = [
        (
            w.start.toordinal() - g.as_of.toordinal(),
            w.end.toordinal() - g.as_of.toordinal(),
        )
        for w in g.windows
    ]
    wins: dict[tuple[int, int], dict[str, Decimal]] = defaultdict(dict)
    for seg, per_day in series.items():
        for t, count in enumerate(per_day, 1):
            if not count:
                continue
            for i, (a, b) in enumerate(ends):
                hit = timing.count_through(b - t) - timing.count_through(a - t)
                if hit:
                    mine = wins[(i, origin[t - 1])]
                    mine[seg] = mine.get(seg, ZERO) + count * hit
            if ends:  # the tail: wins landing after the last month shown, one more atom
                hit = timing.total - timing.count_through(ends[-1][1] - t)
                if hit:
                    mine = wins[(len(ends), origin[t - 1])]
                    mine[seg] = mine.get(seg, ZERO) + count * hit
    out: dict[str, dict[tuple[int, int], Decimal]] = {s: {} for s in series}
    for key, by_segment in wins.items():
        total = sum(by_segment.values(), ZERO)
        weighed = sum((w * sizes[s].won for s, w in by_segment.items()), ZERO)
        for seg in by_segment:
            if weighed:
                out[seg][key] = sizes[seg].won * total / weighed
    return out


MIN_OWN_AMOUNTS = 5  # won amounts a segment needs to be drawn from its own


def segment_amounts(new, segments: Sequence[str]) -> dict:
    """For each segment with at least ``MIN_OWN_AMOUNTS`` won amounts among the pooled samples, those
    amounts over their (weighted) mean with their weights: a win in the segment draws its size from
    these and books it at the segment's price, so the spread between segments is not counted twice
    (the pooled amounts carry it already). A segment with fewer, or none, draws the pooled amounts."""
    if not new.won_arr_segments or len(new.won_arr_segments) != len(
        new.won_arr_samples
    ):
        return {}
    out = {}
    for s in segments:
        at = [
            k for k, x in enumerate(new.won_arr_segments) if rules.segment_key(x) == s
        ]
        if len(at) < MIN_OWN_AMOUNTS:
            continue
        amounts = [new.won_arr_samples[k] for k in at]
        weights = (
            None
            if new.won_arr_weights is None
            else [new.won_arr_weights[k] for k in at]
        )
        total = sum(weights, ZERO) if weights else Decimal(len(amounts))
        mean = (
            sum((a * w for a, w in zip(amounts, weights)), ZERO) / total
            if weights
            else sum(amounts, ZERO) / total
        )
        if total > 0 and mean > 0:
            out[s] = (
                tuple(a / mean for a in amounts),
                None if weights is None else tuple(weights),
            )
    return out


def build_frame(
    g: Ground,
    shares: Mapping[str, Decimal],
    sizes: Mapping[str, Sizes],
    cal: Calendar,
    hires: Sequence[Member],
    inflows: Sequence[Inflow],
    segments: Sequence[str],
) -> Frame:
    days = g.horizon_days
    organic = organic_series(g, shares, hires, segments, days)
    program = program_series(g, shares, inflows, segments, days)
    extra = flows.inflow_series(inflows, g.model.new_pipeline.mean_created_arr, days)
    series = flows.segment_series(organic, extra, shares)
    landing, origin = day_cells(g, cal.year.start, days)
    price = price_index(g, series, sizes, origin)
    return Frame(
        tuple(segments),
        organic,
        program,
        series,
        price,
        landing,
        origin,
        g.model.new_pipeline.mean_won_arr,
        wd.current_value(g, PRODUCTIVITY),
        wd.current_value(g, CYCLE_DAYS),
        Transport(
            g.model.new_pipeline.timing,
            [(w.end - g.as_of).days for w in g.windows],
        ),
        exact_mean(g.model.new_pipeline.timing),
        segment_amounts(g.model.new_pipeline, segments),
    )


# ---------------------------------------------------------------- what an action does


def ramp(action: PlanAction, as_of: date, days: int) -> list[Decimal]:
    """The share of the action's change in force for the deals created on each of ``days``
    days after ``as_of``: none before the start, then ``k`` of the ramp's days on the ``k``-th
    day from the start, and all of it after."""
    if action.ramp_months == 0:
        span = 1
    else:
        span = (add_months(action.start, action.ramp_months) - action.start).days
    out = []
    for t in range(1, days + 1):
        since = (as_of + timedelta(days=t) - action.start).days
        out.append(ZERO if since < 0 else min(ONE, Decimal(since + 1) / Decimal(span)))
    return out


def ramp_exact(action: PlanAction, as_of: date, days: int) -> list[Fraction]:
    """``ramp`` as exact fractions: a cycle's relative change is carried as a rational down to the
    whole-day rounding of each lag, since a ratio rounded to digits moves an exact ceiling."""
    if action.ramp_months == 0:
        span = 1
    else:
        span = (add_months(action.start, action.ramp_months) - action.start).days
    out = []
    for t in range(1, days + 1):
        since = (as_of + timedelta(days=t) - action.start).days
        out.append(
            Fraction(0) if since < 0 else min(Fraction(1), Fraction(since + 1, span))
        )
    return out


def _change(frame: Frame, baseline: Decimal, action: PlanAction) -> Decimal | Fraction:
    """What the action changes, from its target against the baseline the driver is read from: the
    points it adds to the pooled win rate, or the relative change in the size of a win."""
    if action.driver == WIN_RATE:
        return action.target - baseline
    if action.driver == WON_ARR:
        if not frame.size:
            raise ValueError("won ARR per win has no baseline to change")
        return action.target / frame.size - 1
    if action.driver == PRODUCTIVITY:
        if not frame.productivity:
            raise ValueError("creation productivity has no baseline to change")
        return action.target / frame.productivity - 1
    if action.driver == CYCLE_DAYS:
        if not frame.cycle:
            raise ValueError("cycle length has no baseline to change")
        if (
            action.target == frame.cycle
        ):  # the pooled cycle as the report writes it: no change
            return Fraction(0)
        return Fraction(action.target) / (frame.cycle_mean or Fraction(frame.cycle)) - 1
    raise ValueError(f"no rule for the driver {action.driver!r}")


def effect(
    frame: Frame, baseline: Decimal, as_of: date, actions: Sequence[PlanAction]
) -> Effect:
    """What ``actions`` change in each segment on each day, composed in this one place: each
    driver's change is measured from the plan with no actions and the changes of one driver add,
    so the order of the actions cannot matter (the forward function then multiplies the drivers
    through, as they multiply in a win's expected booking)."""
    days = len(next(iter(frame.series.values()), ()))
    by_driver = {
        driver: {
            s: [Fraction(0) if driver == CYCLE_DAYS else ZERO] * days
            for s in frame.segments
        }
        for driver in DRIVERS
    }
    for a in actions:
        unknown = a.segment is not None and a.segment not in frame.segments
        if unknown:
            raise ValueError(
                f"the action {a.id!r} is for a segment with no lane: {a.segment}"
            )
        change = _change(frame, baseline, a)
        weights = (ramp_exact if a.driver == CYCLE_DAYS else ramp)(a, as_of, days)
        mine = by_driver[a.driver]
        for s in frame.segments if a.segment is None else (a.segment,):
            mine[s] = [c + change * w for c, w in zip(mine[s], weights)]
    changes, sizes, creation, cycles = (
        {s: tuple(v) for s, v in by_driver[d].items()} for d in DRIVERS
    )
    lift = Lift(
        baseline,
        frame.organic,
        frame.program,
        changes,
        frame.price,
        frame.landing,
        frame.origin,
        sizes,
        creation,
        cycles,
        frame.transport,
        frame.amounts or {},
    )
    return Effect(
        frame, baseline, as_of, tuple(actions), changes, sizes, creation, cycles, lift
    )


# ---------------------------------------------------------------- what the lanes read


def priced_new_wins(
    g: Ground,
    series: Mapping[str, Sequence[Decimal]],
    sizes: Mapping[str, Sizes],
    cal: Calendar,
    wins: Mapping[flows.Leaf, flows.Flow],
    lanes: Mapping[object, tuple[str, Sequence[Decimal]]] | None = None,
) -> dict[flows.Leaf, flows.Flow]:
    """The wins the plan expects from pipeline not yet created (``wins``, by lane, quarter
    landed in and quarter created in), priced as the pooled bookings are shared out among the
    segments in each month a win lands in, by the quarter its deal was created in: the same
    atoms the actions are priced on (``price_index``), added up to quarters. A win's price is
    then one price, whether the plan's baseline or an action changes it. ``series`` are the
    segments' deals created on each day, which fix the prices; ``lanes`` are what is priced
    (each as ``(segment, deals it creates on each day)``), the segments themselves by default,
    so an owner's wins are priced at the segment's price in each month they land."""
    days = len(next(iter(series.values()), ()))
    _, origin = day_cells(g, cal.year.start, days)
    index = price_index(g, series, sizes, origin)
    lanes = (
        {s: (s, per_day) for s, per_day in series.items()} if lanes is None else lanes
    )
    new = g.model.new_pipeline
    timing = new.timing
    per_win = new.mean_won_arr / Decimal(timing.total)
    booked: dict[flows.Leaf, Decimal] = defaultdict(Decimal)
    for i, w in enumerate(g.windows):
        q = next((k for k, qw in enumerate(cal.quarters) if qw.contains(w.end)), None)
        if q is None:
            continue
        a, b = (
            w.start.toordinal() - g.as_of.toordinal(),
            w.end.toordinal() - g.as_of.toordinal(),
        )
        for key, (s, per_day) in lanes.items():
            for t, count in enumerate(per_day[:days], 1):
                hit = timing.count_through(b - t) - timing.count_through(a - t)
                if count and hit:
                    when = cal.bucket(g.as_of + timedelta(days=t))
                    if when > len(cal.quarters):
                        continue
                    cell = index[s].get((i, origin[t - 1]), ONE)
                    booked[(key, q, when)] += count * new.win_rate * hit * cell
    return {
        k: flows.Flow(wins[k].wins, booked[k] * per_win, wins[k].days) for k in wins
    }


def lane_flows(
    g: Ground,
    lift: Lift,
    cal: Calendar,
    lanes: Mapping[object, tuple[str, Sequence[Decimal], Sequence[Decimal]]],
) -> dict[flows.Leaf, flows.Flow]:
    """What the actions add in the fiscal year to each lane, by (lane, quarter it lands in, quarter
    its deal was created in): extra wins and win days (the lanes' own arithmetic) and the bookings,
    booked month by month as the forward function books them (``Lift.extra_of``). A lane is
    ``(segment, deals it creates on each day, the deals among them that are its people's)``: a segment, or an
    owner of one, whose own creation dates decide what each action does to it."""
    days = (cal.year.end - g.as_of).days
    series = {
        k: lift.extra_wins_of(s, deals[:days], organic[:days])
        for k, (s, deals, organic) in lanes.items()
    }
    wins, _ = flows.new_flows(g.model, series, g.as_of, cal, rate=ONE)
    timing = g.model.new_pipeline.timing
    per_win = g.model.new_pipeline.mean_won_arr / Decimal(timing.total)
    booked: dict[flows.Leaf, Decimal] = defaultdict(Decimal)
    for i, w in enumerate(g.windows):
        q = next((k for k, qw in enumerate(cal.quarters) if qw.contains(w.end)), None)
        if q is None:
            continue
        a, b = (
            w.start.toordinal() - g.as_of.toordinal(),
            w.end.toordinal() - g.as_of.toordinal(),
        )
        for k, (s, deals, organic) in lanes.items():
            values = lift.extra_of(s, i, deals[:days], organic[:days])
            for t, value in enumerate(values[:days], 1):
                hit = timing.count_through(b - t) - timing.count_through(a - t)
                if value and hit:
                    origin = cal.bucket(g.as_of + timedelta(days=t))
                    booked[(k, q, origin)] += value * hit
    moved = _moved_flows(g, lift, cal, lanes, per_win)
    return {
        k: flows.Flow(
            wins.get(k, flows.ZERO_FLOW).wins,
            booked[k] * per_win,
            wins.get(k, flows.ZERO_FLOW).days,
        )
        + moved.get(k, flows.ZERO_FLOW)
        for k in {*wins, *booked, *moved}
    }


def _moved_flows(
    g: Ground,
    lift: Lift,
    cal: Calendar,
    lanes: Mapping[object, tuple[str, Sequence[Decimal], Sequence[Decimal]]],
    per_win: Decimal,
) -> dict[flows.Leaf, flows.Flow]:
    """What a cycle action adds to each lane in the fiscal year: for the deals created on the days
    it reaches, the wins as the plan's changes leave them, with their days and bookings, placed in
    the months their moved lags land them in (each at the price of the month it was to land in),
    less the wins they were, in the months they were to land in."""
    if lift.transport is None:
        return {}
    days = (cal.year.end - g.as_of).days
    total = lift.transport.total
    quarter_of = [
        next((k for k, qw in enumerate(cal.quarters) if qw.contains(w.end)), None)
        for w in g.windows
    ]
    out: dict[flows.Leaf, flows.Flow] = defaultdict(lambda: flows.ZERO_FLOW)
    for key, (segment, deals, organic) in lanes.items():
        price = lift.price.get(segment, {})
        for t in lift.moved_days(segment):
            if t >= days:
                break
            when = cal.bucket(g.as_of + timedelta(days=t + 1))
            if when > len(cal.quarters):
                continue
            wins_new, size, wins_was = lift.day_amounts_of(
                segment, t, deals[t], organic[t]
            )
            f = Fraction(lift.cycle[segment][t]) + 1
            for sign, scale, wins, grows in (
                (1, f, wins_new, size),
                (-1, Fraction(1), wins_was, 1),
            ):
                if not wins:
                    continue
                for piece in lift.transport.pieces(t + 1, scale):
                    q = (
                        quarter_of[piece.moved]
                        if piece.moved < len(quarter_of)
                        else None
                    )
                    if q is None:
                        continue
                    at = price.get((piece.original, lift.origin[t]), ONE)
                    out[(key, q, when)] += flows.Flow(
                        sign * wins * piece.weight / total,
                        sign * wins * grows * piece.weight * at * per_win,
                        sign * wins * piece.moment / total,
                    )
    return dict(out)


def action_flows(g: Ground, eff: Effect, cal: Calendar) -> dict[flows.Leaf, flows.Flow]:
    """What the actions add in the fiscal year to each segment: ``lane_flows`` over the segments'
    own creation, so the lanes add to the forward function's figures."""
    days = (cal.year.end - g.as_of).days
    lift = eff.lift
    return lane_flows(
        g,
        lift,
        cal,
        {
            s: (s, list(lift.counts(s)[:days]), list(lift.organic[s][:days]))
            for s in eff.frame.segments
        },
    )


def period_rate(eff: Effect, segments: Sequence[str], window, as_of: date) -> Decimal:
    """The win rate on the pipeline ``segments`` are expected to create in ``window`` (its dates
    after ``as_of``): the pooled rate plus the change the actions make, weighted by the deals
    created each day. A period with no deal to create keeps the pooled rate."""
    days = len(eff.frame.origin)
    first = max((window.start - as_of).days + 1, 1)
    last = min((window.end - as_of).days, days)
    moved = made = ZERO
    for s in segments:
        created = eff.lift.created(s)  # the deals the actions leave it to create
        for t in range(first, last + 1):
            made += created[t - 1]
            moved += created[t - 1] * eff.changes[s][t - 1]
    return eff.baseline + (moved / made if made else ZERO)


# ---------------------------------------------------------------- the plan's frame


def basis_of(state) -> Basis:
    """The company's frozen plan basis, built once for ``state``."""
    found = state.memo.get("basis")
    if found is None:
        try:
            found = lanes_basis.plan_basis(state)
        except lanes_basis.BasisUnavailable as why:
            found = why
        state.memo["basis"] = found
    if isinstance(found, lanes_basis.BasisUnavailable):
        raise Unavailable(
            f"Driver actions cannot be valued for this company: its plan basis is unavailable ({found})."
        )
    return found


# The most an action may ask for, in multiples of the pooled value: a creation rate any higher draws a
# win for each of billions of deals in every path; a size any higher overflows the exact decimals.
MAX_MULTIPLE = {PRODUCTIVITY: 10, WON_ARR: 1000}
MULTIPLE_WORDS = {10: "ten", 1000: "a thousand"}


def refuse_unbounded(g: Ground, plan: Plan) -> None:
    """Refuse a target the core could not carry, in a person's words, before any simulation."""
    for i, a in enumerate(plan.actions, 1):
        if a.driver == CYCLE_DAYS:
            _refuse_cycle(g, a, i)
            continue
        limit = MAX_MULTIPLE.get(a.driver)
        base = wd.current_value(g, a.driver) if limit else None
        if base and a.target > limit * base:
            words = MULTIPLE_WORDS[limit]
            if a.driver == PRODUCTIVITY:
                unit = (
                    "deals per ramped AE-month"
                    if g.cap.adopted
                    else "organic deals per day"
                )
                what = f"{a.target.normalize():f} {unit}"
                pooled = f"creation rate of {number(base, PRECISION[PRODUCTIVITY])}"
            else:
                what = f"${a.target.normalize():,f} per won deal"
                pooled = f"size of {money(base)}"
            raise ActionRefused(
                f"{a.name!r} asks for {what}, more than {words} times the pooled {pooled}; "
                f"an action may ask for at most {words} times it.",
                "target",
                i,
            )


CYCLE_FLOOR, CYCLE_CEILING = Decimal("0.5"), Decimal(2)


def _refuse_cycle(g: Ground, a: PlanAction, index: int) -> None:
    """A cycle target is held between half and twice the pooled cycle: a product guardrail, not
    evidence of what a team can do; with no cycle to read it against there is nothing to scale."""
    base = wd.current_value(g, CYCLE_DAYS)
    if not base:
        raise ActionRefused(
            f"{a.name!r} changes the cycle length, and there are no recorded win times to read a "
            "target against, so the cycle cannot be changed.",
            "target",
            index,
        )
    shown_base = number(base, PRECISION[CYCLE_DAYS])
    target = f"{a.target.normalize():f} days"
    if a.target < CYCLE_FLOOR * base:
        raise ActionRefused(
            f"{a.name!r} asks for {target}, less than half the pooled cycle of {shown_base} days. "
            "That is a guardrail on what an entered timing can be, not a finding about what is achievable.",
            "target",
            index,
        )
    if a.target > CYCLE_CEILING * base:
        raise ActionRefused(
            f"{a.name!r} asks for {target}, more than twice the pooled cycle of {shown_base} days. "
            "That is a guardrail on what an entered timing can be, not a finding about what is achievable.",
            "target",
            index,
        )


def effect_for(
    state, plan: Plan | None, hires: Sequence[Member], inflows: Sequence[Inflow]
) -> Effect | None:
    """The plan's actions over the plan's own hires and programs; None when it has no actions.
    The frame is made once for each such plan and shared by every change to its actions."""
    if plan is None or not plan.actions:
        return None
    g = state.ground
    key = (tuple(hires), tuple(inflows))
    frame = state.memo.setdefault("frames", {}).get(key)
    if frame is None:
        basis = basis_of(state)
        shares = {s.key: s.creation_share for s in basis.segments}
        segments = segments_of(g, [s.key for s in basis.segments], hires)
        sizes = lanes_basis.sizes_now(g, state.params.trailing_days, segments)
        frame = build_frame(
            g,
            shares,
            sizes,
            Calendar(state.profile.fiscal_year),
            hires,
            inflows,
            segments,
        )
        state.memo["frames"][key] = frame
    return effect(frame, g.model.new_pipeline.win_rate, g.as_of, plan.actions)


# ---------------------------------------------------------------- the report's section

REMOVAL_LABEL = "Bookings lost if removed"
LINE = (
    "An action changes the win rate of pipeline created from its start month on. Deals already "
    "open keep their odds. A segment's target is an entered change on the pooled baseline, "
    "not a measured segment rate."
)
# The reconciliation is material when it does not round to zero in whole dollars, the finest figure
# the screen writes; below that the line is not said. One rule, here, and the report states it per window.
MATERIAL_FROM = Decimal("0.5")


def is_material(value: Decimal) -> bool:
    return abs(value) >= MATERIAL_FROM


def win_rate_only(actions) -> bool:
    return all(a.driver == WIN_RATE for a in actions)


def line_for(actions) -> str:
    """The one line on what an action is: the win rate's own while that is all there is."""
    return LINE if win_rate_only(actions) else LINE_ANY


CYCLE_DEFINITION = (
    " A cycle action changes when wins land, not how many are won or how large they are: the same "
    "wins arrive earlier or later, each at the price of the month it was to land in, so the lifetime "
    "bookings of the pipeline it affects are the same and a month gains what another loses. Its "
    "target is an entered timing assumption on the pooled fitted history, held between half and "
    "twice the pooled cycle as a guardrail."
)


def definition_for(actions) -> str:
    if win_rate_only(actions):
        return DEFINITION
    cycle = any(a.driver == CYCLE_DAYS for a in actions)
    return DEFINITION_ANY + (CYCLE_DEFINITION if cycle else "")


def empty_section() -> dict:
    """A plan with no driver actions: no items, but what an action is, so a form can say it before the first."""
    return {"items": [], "definition": DEFINITION, "line": LINE}


DEFINITION = (
    "A driver action is a named change to one driver in one slice, with a start month, a ramp and "
    "a target. It changes the pipeline created from its start, ramping linearly by creation date "
    "to the target and holding it after. Pipeline created before the start, and every deal "
    "already open, keeps the rates it had. Where the capacity term is in use, hires and programs "
    "stay as the plan has them; each action is valued against them. For a segment, the target is "
    "an entered change on the pooled baseline win rate, not a win rate that was measured for the "
    "segment."
)
REMOVAL_NOTE = (
    "Each action's value is the forecast with all the actions less the forecast with every other "
    "action but not this one, hires and programs held. It is what removing it loses, not a share "
    "of the joint gain, so the values need not add up to it."
)
RANGE_NOTE = (
    "The plan's ranges are simulated with the actions in force, so they carry the model's "
    "uncertainty under the actions and exclude uncertainty about whether an action is achieved."
)
ROUNDING_NOTE = (
    "Each forecast is the sum of its months, each to the cent. A figure that is a difference of "
    "forecasts can differ from another route to the same figure by up to a cent a month; the "
    "reconciliation line is held to that."
)
INSIDE = "within the worksheet's historical settings"
OUTSIDE = "outside the worksheet's historical settings"
NOT_OFFERED = "the worksheet offers no historical settings for the win rate"
LINE_ANY = (
    "An action changes one driver of the pipeline created from its start month on: the win rate, "
    "the size of a win, how many deals people create, or how long wins take. Deals already open "
    "keep their odds, their size and their timing. A segment's target is an entered change on the "
    "pooled baseline, not a value measured for the segment."
)
DEFINITION_ANY = (
    "A driver action is a named change to one driver in one slice, with a start month, a ramp and "
    "a target. It changes the pipeline created from its start, ramping linearly by creation date "
    "to the target and holding it after. Pipeline created before the start, and every deal "
    "already open, keeps the rates, sizes and counts it had. Where the capacity term is in use, hires and "
    "programs stay as the plan has them; each action is valued against them. A target is read "
    "against the pooled baseline of its driver; for a segment it is an entered change on that "
    "baseline, not a value that was measured for the segment. Actions on different drivers add "
    "their changes to the plan as it stands without them, and work through each win together."
)
NO_INTERACTION = (
    "The actions together gain what removing each one loses, to within rounding: they do not "
    "interact in this model."
)
REINFORCE = (
    "What removing each one changes adds up to more than the actions change together: each does "
    "more with the others in place, because their changes multiply, so they reinforce each other."
)
OVERLAP = (
    "The actions together change bookings by more than what removing each one changes adds up "
    "to: the others cover part of what each does, so they overlap."
)


TIMING_INTERACTION = (
    "What removing each one changes does not add up to what the actions change together: a change in "
    "timing moves bookings between months, so its effect on a window can be positive or negative and "
    "the parts and the whole need not agree."
)


def reconciliation_sentence(
    joint: Decimal, summed: Decimal, allowed: Decimal, timed: bool = False
) -> str:
    """What the line between the joint gain and the sum of the removal values says. Within the
    rounding allowance the actions do not interact. Beyond it, by the size of the effects: if the
    removal values add up to more than the actions do together, each does more with the others in
    place; if to less, the others cover part of what each does. (The comparison is of sizes, so
    that it reads the same for actions that take bookings away.)"""
    if abs(joint - summed) <= allowed:
        return NO_INTERACTION
    if timed:  # a timing interaction is signed by the month: size alone says nothing
        return TIMING_INTERACTION
    return REINFORCE if abs(summed) > abs(joint) else OVERLAP


def _windows(f, probe: Probe) -> dict[str, Decimal]:
    shown = probe.shown(f)
    return {w: shown[w] for w in WINDOWS}


def _slice(a: PlanAction) -> dict:
    return {
        "kind": "company" if a.segment is None else "segment",
        "key": a.segment,
        "label": a.slice_label,
    }


def affects_text(
    slice_label: str, start: str, ramp_months: int, driver: str = WIN_RATE
) -> str:
    ramp = (
        "at once"
        if ramp_months == 0
        else f"ramping up over {ramp_months} {'month' if ramp_months == 1 else 'months'}"
    )
    month = month_words(date.fromisoformat(f"{start}-01"))
    if driver == WON_ARR:
        return (
            f"Wins of pipeline created from {month} in {slice_label}, {ramp} to the target size; "
            "how many are won, and the wins of pipeline created earlier or already open, keep their size."
        )
    if driver == CYCLE_DAYS:
        return (
            f"The wins of pipeline created from {month} in {slice_label}, {ramp} to the target days from "
            "creation to win: they land earlier or later, none more or fewer, each at the price of the "
            "month it was to land in; pipeline created earlier and deals already open keep their timing. "
            "An entered timing assumption on the pooled history."
        )
    if driver == PRODUCTIVITY:
        return (
            f"The deals {slice_label} creates itself from {month}, through its people, {ramp} to the "
            "target; the deals programs create, deals created earlier and every deal already open "
            "stay as they were."
        )
    return (
        f"Pipeline created from {month} in {slice_label}, {ramp} to the target; pipeline "
        "created earlier, and every deal already open, keeps its rate."
    )


def not_offered(driver: str) -> str:
    """The sentence for a driver the worksheet offers no historical settings for."""
    if driver == WIN_RATE:
        return NOT_OFFERED
    return f"the worksheet offers no historical settings for {WORDS[driver]}"


def placing(target: Decimal, row: dict, driver: str) -> tuple[str, str]:
    """Where ``target`` sits against the worksheet's low and high for its driver, and the label
    that says so."""
    h = row["historical"]
    if h is None:
        return "none", not_offered(driver)
    if target < Decimal(h["low"]["setting"]):
        return "below", OUTSIDE
    if target > Decimal(h["high"]["setting"]):
        return "above", OUTSIDE
    return "inside", INSIDE


def shown(driver: str, value: Decimal) -> str:
    """A driver's value as the worksheet writes it."""
    return money(value) if driver == WON_ARR else number(value, PRECISION[driver])


def _evidence(g: Ground, a: PlanAction, row: dict) -> dict:
    """The pooled baseline, the change, the result, and where the target sits against the
    worksheet's low and high for this driver (its means of the lower and upper halves of the
    quarters observed, not the extremes)."""
    h = row["historical"]
    low, high = (
        (None, None) if h is None else (h["low"]["setting"], h["high"]["setting"])
    )
    position, label = placing(a.target, row, a.driver)
    if a.driver == WIN_RATE:
        base = g.model.new_pipeline.win_rate
        return {
            "baseline_rate": number(base, PRECISION[WIN_RATE]),
            "change_points": f"{(a.target - base) * 100:.2f}",
            "resulting_rate": number(a.target, PRECISION[WIN_RATE]),
            "historical_low": low,
            "historical_high": high,
            "position": position,
            "label": label,
        }
    base = wd.current_value(g, a.driver)
    return {
        "baseline": shown(a.driver, base),
        "change_percent": f"{(a.target / base - 1) * 100:.2f}",
        "resulting": shown(a.driver, a.target),
        "historical_low": low,
        "historical_high": high,
        "position": position,
        "label": label,
    }


def _quarters(g: Ground, probe: Probe, f) -> list[dict]:
    out = []
    for q, status, _, booked, labels in g.quarters:
        forecast = probe.scenario.shown(f, list(labels))
        out.append(
            {
                "quarter": q,
                "status": status,
                "forecast": money(forecast),
                "expected": money(booked + cents(forecast)),
            }
        )
    return out


def _figures(g: Ground, probe: Probe, f) -> dict:
    shown = _windows(f, probe)
    return {
        "bookings": {w: money(v) for w, v in shown.items()},
        "expected_fiscal_year": money(g.fytd + shown[REST_OF_FY]),
        "quarters": _quarters(g, probe, f),
    }


def _months(g: Ground) -> dict[str, int]:
    return {REST_OF_FY: len(g.rest_labels), NEXT_12: len(g.twelve_labels)}


def section(
    g: Ground,
    eff: Effect,
    hires: Sequence[Member],
    inflows: Sequence[Inflow],
    rows: Mapping[str, dict],
    plan_section: dict,
) -> tuple[dict, list[Check]]:
    """The driver actions' values and evidence, by the worksheet's probe (expectations only):
    every counterfactual is the plan's own hires and programs with some of the actions. ``rows``
    are the worksheet's driver rows, by driver."""
    probe = Probe(g, hires, inflows)
    without = probe.base
    everything = probe.with_lift(eff.lift)
    none_shown, all_shown = probe.shown(without), probe.shown(everything)
    joint = {w: all_shown[w] - none_shown[w] for w in WINDOWS}
    items, removals = [], []
    for a in eff.actions:
        left = probe.shown(probe.with_lift(eff.dropping(a).lift))
        removal = {w: all_shown[w] - left[w] for w in WINDOWS}
        removals.append(removal)
        items.append(
            {
                "id": a.id,
                "name": a.name,
                "driver": a.driver,
                "slice": _slice(a),
                "start": f"{a.start:%Y-%m}",
                "ramp_months": a.ramp_months,
                "target": shown(a.driver, a.target),
                "affects": affects_text(
                    a.slice_label, f"{a.start:%Y-%m}", a.ramp_months, a.driver
                ),
                "removal_value": {w: money(v) for w, v in removal.items()},
                "evidence": _evidence(g, a, rows[a.driver]),
            }
        )
    summed = {w: sum((r[w] for r in removals), ZERO) for w in WINDOWS}
    gap = {w: joint[w] - summed[w] for w in WINDOWS}
    tolerance = {w: CENT * _months(g)[w] * (1 + len(eff.actions)) for w in WINDOWS}
    timed = any(a.driver == CYCLE_DAYS for a in eff.actions)
    sentences = {
        w: reconciliation_sentence(joint[w], summed[w], tolerance[w], timed)
        for w in WINDOWS
    }
    out = {
        "definition": definition_for(eff.actions),
        "line": line_for(eff.actions),
        "removal_label": REMOVAL_LABEL,
        "removal_note": REMOVAL_NOTE,
        "items": items,
        "joint_gain": {w: money(v) for w, v in joint.items()},
        "reconciliation": {
            "values": {w: money(v) for w, v in gap.items()},
            "tolerance": {w: money(v) for w, v in tolerance.items()},
            "sentences": sentences,
            "material": {w: is_material(gap[w]) for w in WINDOWS},
        },
        "without_actions": _figures(g, probe, without),
        "with_actions": _figures(g, probe, everything),
        "range_note": RANGE_NOTE,
        "rounding_note": ROUNDING_NOTE,
    }
    step = next(i for i in plan_section["items"] if i["kind"] == "actions")
    checks = [
        Check(
            "driver actions' joint gain is the plan's actions step",
            out["joint_gain"] == step["contribution"],
            f"{out['joint_gain']} by the probe against {step['contribution']} in the plan",
        ),
        Check(
            "driver actions' with-figures are the plan's expected fiscal year",
            out["with_actions"]["expected_fiscal_year"]
            == plan_section["expected_fiscal_year"],
            f"{out['with_actions']['expected_fiscal_year']} against {plan_section['expected_fiscal_year']}",
        ),
        _interaction_check(eff.actions, joint, summed, gap, tolerance),
    ]
    return out, checks


def _interaction_check(actions, joint, summed, gap, tolerance) -> Check:
    """Actions on one driver do not interact, so their removal values add to the joint gain;
    actions on different drivers do (more deals at a higher rate and size), so for them the
    check is that the reconciliation line is the joint gain less the removal values."""
    detail = "; ".join(
        f"{w}: reconciliation {money(gap[w])}, rounding allows {money(tolerance[w])}"
        for w in WINDOWS
    )
    drivers = {a.driver for a in actions}
    if len(drivers) == 1:
        (driver,) = drivers
        return Check(
            f"driver actions on {ACTED_ON[driver]} do not interact: removal values add to the joint gain",
            all(abs(gap[w]) <= tolerance[w] for w in WINDOWS),
            detail,
        )
    return Check(
        "driver actions on different drivers interact: the reconciliation is the joint gain less the removal values",
        all(gap[w] == joint[w] - summed[w] for w in WINDOWS),
        detail,
    )
