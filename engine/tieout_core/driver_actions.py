"""Actions on a slice: what a change to the win rate of one segment (or the company) is
expected to add, from the day it starts.

The model fits one pooled win rate, so an action is an entered change, not a segment's fit. It
applies to deals created on or after its start, and ramps linearly by creation date: on the
``k``-th day from the start (the start day is the first) the change is ``k`` over the days in the
ramp's months, at most all of it, and a ramp of zero months is all of it from the start day. Deals
created earlier, and every deal already open, keep the rate they had. A change of ``d`` points on
a day on which a segment creates ``c`` deals is ``c * d`` more expected wins.

Wins are priced at the pooled mean won size times the segment's price index, which is frozen: the
no-action plan's wins priced as the lanes share the pooled bookings out (by segment size), taken
over the fiscal year as one figure per segment. That is why a segment's action moves nothing in
another segment, why the company's action is the same action in every segment, and why the
actions' bookings are added to the company forecast rather than shared out of it.

Everything is an exact decimal. ``lift`` is the one series the forward function reads: the extra
wins, priced, expected from the deals created on each day.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import lanes_basis
from . import lanes_flows as flows
from . import lanes_rules as rules
from .actions import Ground
from .capacity import project
from .fiscal import add_months
from .forecast import Inflow
from .lanes_basis import Basis, Sizes
from .lanes_flows import Calendar
from .plan import Plan, PlanAction
from .roster import Member
from .worksheet_rules import WIN_RATE

ZERO, ONE = Decimal(0), Decimal(1)


class Unavailable(ValueError):
    """Actions cannot be valued for this company; the message says why."""


@dataclass(frozen=True)
class Frame:
    """The company by segment as the plan leaves it before any action: the deals each segment is
    expected to create on each day after the as-of date, and each segment's price index."""

    segments: tuple[str, ...]
    series: Mapping[str, Sequence[Decimal]]
    price: Mapping[str, Decimal]


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
    lift: tuple[Decimal, ...]  # extra wins, priced, from the deals created on each day

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


def creation_series(
    g: Ground,
    shares: Mapping[str, Decimal],
    hires: Sequence[Member],
    inflows: Sequence[Inflow],
    segments: Sequence[str],
    days: int,
) -> dict[str, list[Decimal]]:
    """Deals created on each of ``days`` days after the as-of date, by segment: each segment's
    organic creation (its people's, where the capacity term is adopted, else its frozen share
    of the flat rate) and its share of the programs' (a program names no segment)."""
    if g.cap.adopted:
        people = [*g.cap.members, *hires]
        organic = {
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
    else:
        rate = g.model.new_pipeline.created_per_day
        organic = {seg: [rate * shares.get(seg, ZERO)] * days for seg in segments}
    extra = flows.inflow_series(inflows, g.model.new_pipeline.mean_created_arr, days)
    return flows.segment_series(organic, extra, shares)


def price_index(
    g: Ground,
    series: Mapping[str, Sequence[Decimal]],
    sizes: Mapping[str, Sizes],
    cal: Calendar,
) -> dict[str, Decimal]:
    """Each segment's price per win over the pooled mean won size, from the no-action plan's
    wins in the fiscal year as the lanes price them (the pooled bookings of each quarter and
    origin shared out by wins times segment size); 1 for a segment with no wins to price."""
    pooled = g.model.new_pipeline.mean_won_arr
    days = (cal.year.end - g.as_of).days
    wins, _ = flows.new_flows(
        g.model, {s: v[:days] for s, v in series.items()}, g.as_of, cal
    )
    priced = flows.price(wins, sizes, pooled)
    out = {}
    for seg in series:
        mine = [k for k in priced if k[0] == seg]
        count = sum((priced[k].wins for k in mine), ZERO)
        booked = sum((priced[k].bookings for k in mine), ZERO)
        out[seg] = booked / (count * pooled) if count and pooled else ONE
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
    series = creation_series(g, shares, hires, inflows, segments, g.horizon_days)
    return Frame(tuple(segments), series, price_index(g, series, sizes, cal))


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


def _change(baseline: Decimal, action: PlanAction) -> Decimal:
    """The points the action adds to the win rate: its target less the pooled rate."""
    if action.driver == WIN_RATE:
        return action.target - baseline
    raise ValueError(f"no rule for the driver {action.driver!r}")


def effect(
    frame: Frame, baseline: Decimal, as_of: date, actions: Sequence[PlanAction]
) -> Effect:
    days = len(next(iter(frame.series.values()), ()))
    changes = {s: [ZERO] * days for s in frame.segments}
    for a in actions:
        unknown = a.segment is not None and a.segment not in changes
        if unknown:
            raise ValueError(
                f"the action {a.id!r} is for a segment with no lane: {a.segment}"
            )
        points = _change(baseline, a)
        weights = ramp(a, as_of, days)
        for s in frame.segments if a.segment is None else (a.segment,):
            changes[s] = [c + points * w for c, w in zip(changes[s], weights)]
    lift = tuple(
        sum(
            (
                frame.series[s][t] * changes[s][t] * frame.price[s]
                for s in frame.segments
            ),
            ZERO,
        )
        for t in range(days)
    )
    return Effect(
        frame,
        baseline,
        as_of,
        tuple(actions),
        {s: tuple(v) for s, v in changes.items()},
        lift,
    )


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
            f"win-rate actions need the plan basis, which is unavailable: {found}"
        )
    return found


def effect_for(
    state, plan: Plan, hires: Sequence[Member], inflows: Sequence[Inflow]
) -> Effect | None:
    """The plan's actions over the plan's own hires and programs; None when it has no actions.
    The frame is made once for each such plan and shared by every change to its actions."""
    if not plan.actions:
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
