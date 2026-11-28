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

from . import lanes_basis
from . import lanes_flows as flows
from . import lanes_rules as rules
from .actions import Ground
from .capacity import project
from .figures import CENT, cents, money, number
from .fiscal import add_months
from .forecast import Inflow, Lift
from .lanes_basis import Basis, Sizes
from .lanes_flows import Calendar
from .plan import NEXT_12, REST_OF_FY, Plan, PlanAction, month_words
from .records import Check
from .roster import Member
from .worksheet_drivers import Probe
from .worksheet_rules import PRECISION, WIN_RATE

ZERO, ONE = Decimal(0), Decimal(1)
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
    out: dict[str, dict[tuple[int, int], Decimal]] = {s: {} for s in series}
    for key, by_segment in wins.items():
        total = sum(by_segment.values(), ZERO)
        weighed = sum((w * sizes[s].won for s, w in by_segment.items()), ZERO)
        for seg in by_segment:
            if weighed:
                out[seg][key] = sizes[seg].won * total / weighed
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
    return Frame(tuple(segments), organic, program, series, price, landing, origin)


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
    lift = Lift(
        baseline,
        frame.organic,
        frame.program,
        {s: tuple(v) for s, v in changes.items()},
        frame.price,
        frame.landing,
        frame.origin,
    )
    return Effect(
        frame,
        baseline,
        as_of,
        tuple(actions),
        {s: tuple(v) for s, v in changes.items()},
        lift,
    )


# ---------------------------------------------------------------- what the lanes read


def action_flows(g: Ground, eff: Effect, cal: Calendar) -> dict[flows.Leaf, flows.Flow]:
    """The extra wins the actions expect in the fiscal year, by (segment, quarter it lands in,
    quarter its deal was created in). Wins and win days are the lanes' own arithmetic; the
    bookings are booked month by month at the pooled size times the segment's price index in
    that month's cell, as the forward function books them, so the lanes add to its figures."""
    days = (cal.year.end - g.as_of).days
    series = {
        s: [c * d for c, d in zip(eff.frame.series[s][:days], eff.changes[s][:days])]
        for s in eff.frame.segments
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
        for s, per_day in series.items():
            index = eff.frame.price[s]
            for t, count in enumerate(per_day, 1):
                hit = timing.count_through(b - t) - timing.count_through(a - t)
                if count and hit:
                    origin = cal.bucket(g.as_of + timedelta(days=t))
                    cell = (i, eff.frame.origin[t - 1])
                    booked[(s, q, origin)] += count * hit * index.get(cell, ONE)
    return {k: flows.Flow(f.wins, booked[k] * per_win, f.days) for k, f in wins.items()}


def period_rate(eff: Effect, segments: Sequence[str], window, as_of: date) -> Decimal:
    """The win rate on the pipeline ``segments`` are expected to create in ``window`` (its dates
    after ``as_of``): the pooled rate plus the change the actions make, weighted by the deals
    created each day. A period with no deal to create keeps the pooled rate."""
    days = len(eff.frame.origin)
    first = max((window.start - as_of).days + 1, 1)
    last = min((window.end - as_of).days, days)
    moved = made = ZERO
    for s in segments:
        for t in range(first, last + 1):
            made += eff.frame.series[s][t - 1]
            moved += eff.frame.series[s][t - 1] * eff.changes[s][t - 1]
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
            f"Win-rate actions cannot be valued for this company: its plan basis is unavailable ({found})."
        )
    return found


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
NO_INTERACTION = (
    "The actions together gain what removing each one loses, to within rounding: they do not "
    "interact in this model."
)
REINFORCE = (
    "What removing each one loses adds up to more than the actions gain together: each is worth "
    "more with the others in place, so they reinforce each other."
)
OVERLAP = (
    "The actions together gain more than what removing each one loses adds up to: the others "
    "cover part of what each does, so they overlap."
)


def _windows(f, probe: Probe) -> dict[str, Decimal]:
    shown = probe.shown(f)
    return {w: shown[w] for w in WINDOWS}


def _slice(a: PlanAction) -> dict:
    return {
        "kind": "company" if a.segment is None else "segment",
        "key": a.segment,
        "label": a.slice_label,
    }


def affects_text(slice_label: str, start: str, ramp_months: int) -> str:
    ramp = (
        "at once"
        if ramp_months == 0
        else f"ramping up over {ramp_months} {'month' if ramp_months == 1 else 'months'}"
    )
    return (
        f"Pipeline created from {month_words(date.fromisoformat(f'{start}-01'))} in {slice_label}, {ramp} to the target; pipeline "
        "created earlier, and every deal already open, keeps its rate."
    )


def _evidence(g: Ground, a: PlanAction, row: dict) -> dict:
    """The pooled baseline, the change, the result, and where the target sits against the
    worksheet's low and high for this driver (its means of the lower and upper halves of the
    quarters observed, not the extremes)."""
    places = PRECISION[WIN_RATE]
    base = g.model.new_pipeline.win_rate
    h = row["historical"]
    low = high = None
    if h is None:
        position, label = "none", NOT_OFFERED
    else:
        low, high = h["low"]["setting"], h["high"]["setting"]
        if a.target < Decimal(low):
            position, label = "below", OUTSIDE
        elif a.target > Decimal(high):
            position, label = "above", OUTSIDE
        else:
            position, label = "inside", INSIDE
    return {
        "baseline_rate": number(base, places),
        "change_points": f"{(a.target - base) * 100:.2f}",
        "resulting_rate": number(a.target, places),
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
    win_rate_row: dict,
    plan_section: dict,
) -> tuple[dict, list[Check]]:
    """The driver actions' values and evidence, by the worksheet's probe (expectations only):
    every counterfactual is the plan's own hires and programs with some of the actions."""
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
                "target": number(a.target, PRECISION[WIN_RATE]),
                "affects": affects_text(
                    a.slice_label, f"{a.start:%Y-%m}", a.ramp_months
                ),
                "removal_value": {w: money(v) for w, v in removal.items()},
                "evidence": _evidence(g, a, win_rate_row),
            }
        )
    summed = {w: sum((r[w] for r in removals), ZERO) for w in WINDOWS}
    gap = {w: joint[w] - summed[w] for w in WINDOWS}
    tolerance = {w: CENT * _months(g)[w] * (1 + len(eff.actions)) for w in WINDOWS}
    sentences = {
        w: NO_INTERACTION
        if abs(gap[w]) <= tolerance[w]
        else (REINFORCE if gap[w] < 0 else OVERLAP)
        for w in WINDOWS
    }
    out = {
        "definition": DEFINITION,
        "line": LINE,
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
        Check(
            "driver actions on a win rate do not interact: removal values add to the joint gain",
            all(abs(gap[w]) <= tolerance[w] for w in WINDOWS),
            "; ".join(
                f"{w}: reconciliation {money(gap[w])}, rounding allows {money(tolerance[w])}"
                for w in WINDOWS
            ),
        ),
    ]
    return out, checks
