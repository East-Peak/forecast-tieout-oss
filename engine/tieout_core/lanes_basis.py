"""The reconstructed plan basis: what a refit on the day before the fiscal year started freezes.

The files keep no record of the plan the company set, so the core rebuilds one: it refits the
model using only what was known the day before the year began, solves for the pipeline each
quarter's entered target needs through that fit, and keeps the result. Every goal in a lane
comes from this basis and nothing else, so a scenario, an applied plan or what has happened
since cannot move a goal. It is labeled a reconstruction, never an original commitment.

The solver's schedule over-covers the targets (pipeline created to fund one quarter also lands in
later ones), so what it creates is a derived benchmark and its own bookings are kept beside the
targets. Segment goals split each target by the segment's share of the trailing year's bookings,
and every additive goal of a parent is the sum of its children.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal

from . import lanes_flows as flows
from . import lanes_rules as rules
from .adoption import ADOPTED, adoption_test
from .backtest import choose_fit
from .figures import CENT
from .fiscal import month_windows
from .fit import fit
from .forecast import model_forecast
from .history import as_known_at, creation_amounts, latest_known_date
from .lanes_alloc import UNITS, OwnerBasis, owner_basis
from .lanes_contract import SCHEMA_VERSION
from .lanes_flows import Calendar
from .lanes_rules import COUNT, OWNER_CAVEAT
from .records import Check, Deal
from .report import LEVER_CAP_MULTIPLE, Prepared, _trailing_created_arr
from .requirement import solve_quarters
from .roster import roster_at

ZERO = Decimal(0)
SEGMENT_MEAN, POOLED = "segment mean", "pooled, thin sample"
CAVEAT = (
    "These goals are derived benchmarks, not a reconciled operating plan. The solver's schedule "
    "creates more pipeline than the targets need, because pipeline created to fund one quarter "
    "also lands in later ones, so its own bookings are shown beside the targets; target-equivalent "
    "wins come from the target, not from the schedule. Ownership, segment and quota have no "
    "history in the files, so today's values stand in for the plan start. "
    + rules.ESTIMATOR_RULE
    + " "
    + rules.ZERO_TARGET_RULE
)


class BasisUnavailable(Exception):
    """The plan basis cannot be built; the message says why."""


@dataclass(frozen=True)
class Sizes:
    won: Decimal
    won_basis: str
    created: Decimal
    created_basis: str


@dataclass(frozen=True)
class Goal:
    bookings: Decimal
    won: Decimal  # target-equivalent wins
    created: Decimal
    created_arr: Decimal
    days: Decimal  # win days the benchmark cycle implies: wins times the cycle


@dataclass(frozen=True)
class ScheduleQuarter:
    quarter: str
    target: Decimal
    outcome: str
    created: Decimal
    created_arr: Decimal
    wins: Decimal
    bookings: Decimal
    days: Decimal


@dataclass(frozen=True)
class SegmentBasis:
    key: str
    trailing_bookings: Decimal
    share: Decimal
    creation_share: Decimal
    opening: int
    sizes: Sizes


@dataclass(frozen=True)
class Basis:
    cutoff: date
    label: str
    capacity_decision: str
    capacity_reason: str
    win_rate: Decimal
    cohort_size: int
    estimator: str
    mean_won_arr: Decimal
    mean_created_arr: Decimal
    created_per_day: Decimal
    segments: tuple[SegmentBasis, ...]  # by bookings goal, largest first
    schedule: tuple[ScheduleQuarter, ...]
    goals: Mapping[tuple[str, str], Goal]  # (quarter, segment)
    checks: tuple[Check, ...]
    owners: tuple[OwnerBasis, ...] = ()
    owner_goals: Mapping[tuple[str, str, str], Goal] = field(default_factory=dict)

    @property
    def opening(self) -> int:
        return sum(s.opening for s in self.segments)


def segment_sizes(
    deals: Sequence[Deal],
    amounts: Mapping[str, Decimal | None],
    cutoff: date,
    pooled_won: Decimal,
    pooled_created: Decimal,
    days: int = 365,
) -> dict[str, Sizes]:
    """Each segment's mean won size and mean created size over the ``days`` to ``cutoff``,
    where enough observations stand behind it; otherwise the pooled figure, and it says so."""
    start = cutoff - timedelta(days=days)
    out = {}
    for key in sorted({rules.segment_key(d.segment) for d in deals}):
        mine = [d for d in deals if rules.segment_key(d.segment) == key]
        wins = [d.arr for d in mine if d.is_won and start < d.close <= cutoff]
        made = [amounts.get(d.id) for d in mine if start < d.created <= cutoff]
        made = [a for a in made if a is not None]
        enough_won, enough_made = (
            len(wins) >= rules.MIN_SEGMENT_WINS,
            len(made) >= rules.MIN_SEGMENT_CREATED,
        )
        out[key] = Sizes(
            sum(wins, ZERO) / len(wins) if enough_won else pooled_won,
            SEGMENT_MEAN if enough_won else POOLED,
            sum(made, ZERO) / len(made) if enough_made else pooled_created,
            SEGMENT_MEAN if enough_made else POOLED,
        )
    return out


def split_goals(
    target: Decimal,
    trailing: Mapping[str, Decimal],
    sizes: Mapping[str, Sizes],
    created: Decimal,
    cycle: Decimal,
) -> dict[str, Goal]:
    """One quarter's goals by segment. The target is shared by trailing bookings, to the cent;
    target-equivalent wins are each share over the segment's own plan-start size; the schedule's
    created deals are shared in proportion to those wins (the pipeline each needs, conversion
    being pooled); created ARR is those deals at the segment's created size. The quarter's
    figures for the company are the sums of these, and no figure is rounded twice."""
    keys = list(trailing)
    bookings = flows.apportion(target, [trailing[k] for k in keys])
    needed = [b / sizes[k].won for b, k in zip(bookings, keys)]
    by = needed if any(needed) else [trailing[k] for k in keys]  # ZERO_TARGET_RULE
    made = flows.apportion(created.quantize(COUNT), by, "0.0001")
    out = {}
    for k, b, n, c in zip(keys, bookings, needed, made):
        wins = n.quantize(COUNT)
        out[k] = Goal(
            b,
            wins,
            c,
            (c * sizes[k].created).quantize(CENT),
            (wins * cycle).quantize(CENT),
        )
    return out


def _schedule(
    model, known, cutoff, cal, inflows, targets, results
) -> tuple[ScheduleQuarter, ...]:
    horizon = (cal.year.end - cutoff).days
    new = model.new_pipeline
    organic = [new.created_per_day] * horizon
    extra = flows.inflow_series(inflows, new.mean_created_arr, horizon)
    won, made = flows.new_flows(
        model, {"": [o + e for o, e in zip(organic, extra)]}, cutoff, cal
    )
    leaves = flows.existing_flows(model, known.deals, cutoff, cal)
    for leaf, flow in won.items():
        leaves[leaf] = leaves.get(leaf, flows.ZERO_FLOW) + flow
    out = []
    for q, (key, result) in enumerate(zip(cal.year.quarter_keys, results)):
        total = sum((f for (_, lq, _), f in leaves.items() if lq == q), flows.ZERO_FLOW)
        deals = made.get(("", q + 1), ZERO)
        out.append(
            ScheduleQuarter(
                key,
                targets[key],
                result.outcome,
                deals,
                deals * new.mean_created_arr,
                total.wins,
                total.bookings,
                total.days,
            )
        )
    return tuple(out)


def plan_basis(state: Prepared) -> Basis:
    """The reconstructed plan basis for the company ``state`` was prepared for."""
    profile, fy = state.profile, state.profile.fiscal_year
    cal = Calendar(fy)
    cutoff = cal.start
    known = as_known_at(state.pop, cutoff)
    # Nothing the report decided at its later date is inherited: the estimator is chosen again,
    # by the same rule, from back-test folds cut at the plan date.
    params, _, _ = choose_fit(
        known,
        cutoff,
        profile,
        replace(state.params, estimator=state.incumbent_name),
        min(state.draws, 1000),
        state.seed,
    )
    adoption = adoption_test(
        known,
        roster_at(state.cap.members, cutoff),
        state.cap.cfg,
        cutoff,
        params,
        state.cap.roster.unavailable,
    )
    if adoption.outcome == ADOPTED:
        raise BasisUnavailable(
            "the capacity term is adopted at the plan start, which the lanes do not yet support"
        )
    model = fit(known, cutoff, profile, params)
    months = month_windows(cutoff, fy.end)
    flat = model_forecast(model, known, cutoff, months)
    if not flat.available:
        raise BasisUnavailable(
            f"the plan-start forecast is unavailable: {flat.unavailable_reason}"
        )
    new = model.new_pipeline
    targets = profile.quarterly_targets
    cap = LEVER_CAP_MULTIPLE * _trailing_created_arr(
        known, cutoff, params.trailing_days
    )
    results = solve_quarters(
        model,
        known,
        cutoff,
        months,
        {q: (fy.quarter_window(q), targets[q]) for q in fy.quarter_keys},
        {},
        None,
        cap,
    )
    inflows = tuple(i for r in results for i in r.inflows)
    schedule = _schedule(model, known, cutoff, cal, inflows, targets, results)

    start = cutoff - timedelta(days=params.trailing_days)
    trailing: dict[str, Decimal] = {}
    created_count: dict[str, int] = {}
    opening: dict[str, int] = {}
    for d in known.deals:
        key = rules.segment_key(d.segment)
        trailing.setdefault(key, ZERO)
        created_count.setdefault(key, 0)
        opening.setdefault(key, 0)
        opening[key] += not d.is_closed
        created_count[key] += start < d.created <= cutoff
        if d.is_won and start < d.close <= cutoff:
            trailing[key] += d.arr
    if not sum(trailing.values(), ZERO) or not sum(created_count.values()):
        raise BasisUnavailable(
            "no bookings or no created deals in the year before the plan start"
        )
    order = sorted(trailing, key=lambda k: (-trailing[k], k))
    trailing = {k: trailing[k] for k in order}
    sizes = segment_sizes(
        known.deals,
        creation_amounts(known),
        cutoff,
        new.mean_won_arr,
        new.mean_created_arr,
        params.trailing_days,
    )
    total_bookings, total_created = (
        sum(trailing.values(), ZERO),
        sum(created_count.values()),
    )
    goals = {}
    for s in schedule:
        cycle = s.days / s.wins if s.wins else ZERO
        for k, g in split_goals(s.target, trailing, sizes, s.created, cycle).items():
            goals[(s.quarter, k)] = g
    segments = tuple(
        SegmentBasis(
            k,
            trailing[k],
            trailing[k] / total_bookings,
            Decimal(created_count[k]) / total_created,
            opening[k],
            sizes[k],
        )
        for k in order
    )

    owners, owner_goals = owner_basis(
        known.deals,
        state.cap.members,
        cutoff,
        fy,
        params.trailing_days,
        goals,
        order,
    )
    everything = model_forecast(model, known, cutoff, months, inflows=inflows)
    replayed = sum(
        (w for w in (everything.window_total(m.label) for m in months)), ZERO
    )
    checks = (
        Check(
            "plan basis saw nothing after its cutoff",
            latest_known_date(known) <= cutoff,
            f"the refit's latest fact is dated {latest_known_date(known)}; the cutoff is {cutoff}",
        ),
        Check(
            "frozen schedule replays the forward function",
            abs(sum((s.bookings for s in schedule), ZERO) - replayed)
            <= Decimal("0.000001"),
            f"the schedule's quarters book {sum((s.bookings for s in schedule), ZERO):.2f}; the forward function gives {replayed:.2f}",
        ),
        Check(
            "segment goals add to the entered targets",
            all(
                sum((g.bookings for (q, _), g in goals.items() if q == k), ZERO) == t
                for k, t in targets.items()
            ),
            "each quarter's segment bookings goals sum to its target to the cent",
        ),
        Check(
            "owner goals add to their segment's goal",
            all(
                sum(
                    (
                        getattr(g, f)
                        for (q, s, _), g in owner_goals.items()
                        if (q, s) == key
                    ),
                    ZERO,
                )
                == getattr(goal, f)
                for key, goal in goals.items()
                for f in UNITS
            ),
            "each segment goal's five figures, in each quarter, are the sums of its owners'",
        ),
    )
    return Basis(
        cutoff,
        f"Reconstructed FY plan basis, {cutoff}",
        adoption.outcome,
        adoption.reason,
        new.win_rate,
        new.cohort_size,
        params.estimator,
        new.mean_won_arr,
        new.mean_created_arr,
        new.created_per_day,
        segments,
        schedule,
        goals,
        checks,
        owners,
        owner_goals,
    )


def _text(x: Decimal, places: str) -> str:
    return str(x.quantize(Decimal(places)))


def _owner_goals(basis: Basis) -> dict:
    out: dict = {}
    for (quarter, seg, owner), g in basis.owner_goals.items():
        out.setdefault(quarter, {}).setdefault(seg, {})[owner] = {
            "bookings": _text(g.bookings, "0.01"),
            "won": _text(g.won, "0.0001"),
            "created": _text(g.created, "0.0001"),
            "created_arr": _text(g.created_arr, "0.01"),
            "days": _text(g.days, "0.01"),
        }
    return out


def document(basis: Basis, company: str) -> dict:
    """The basis as the file written beside the company's lanes. It holds no scenario figure."""
    return {
        "schema_version": SCHEMA_VERSION,
        "company": company,
        "label": basis.label,
        "cutoff": str(basis.cutoff),
        "capacity_at_plan_start": {
            "decision": basis.capacity_decision,
            "reason": basis.capacity_reason,
        },
        "fit": {
            "win_rate": _text(basis.win_rate, "0.0001"),
            "cohort_size": basis.cohort_size,
            "estimator": basis.estimator,
            "mean_won_arr": _text(basis.mean_won_arr, "0.01"),
            "mean_created_arr": _text(basis.mean_created_arr, "0.01"),
            "created_per_day": _text(basis.created_per_day, "0.0001"),
        },
        "opening": basis.opening,
        "segments": [
            {
                "key": s.key,
                "trailing_bookings": _text(s.trailing_bookings, "0.01"),
                "share": _text(s.share, "0.000001"),
                "creation_share": _text(s.creation_share, "0.000001"),
                "opening": s.opening,
                "won_size": _text(s.sizes.won, "0.01"),
                "won_size_basis": s.sizes.won_basis,
                "created_size": _text(s.sizes.created, "0.01"),
                "created_size_basis": s.sizes.created_basis,
            }
            for s in basis.segments
        ],
        "schedule_total": {
            "bookings": str(
                sum((Decimal(_text(q.bookings, "0.01")) for q in basis.schedule), ZERO)
            ),
            "target": str(
                sum((Decimal(_text(q.target, "0.01")) for q in basis.schedule), ZERO)
            ),
        },
        "schedule": [
            {
                "quarter": q.quarter,
                "target": _text(q.target, "0.01"),
                "outcome": q.outcome,
                "created": _text(q.created, "0.0001"),
                "created_arr": _text(q.created_arr, "0.01"),
                "wins": _text(q.wins, "0.0001"),
                "bookings": _text(q.bookings, "0.01"),
                "days": _text(q.days, "0.01"),
            }
            for q in basis.schedule
        ],
        "goals": {
            q.quarter: {
                s.key: {
                    "bookings": _text(basis.goals[(q.quarter, s.key)].bookings, "0.01"),
                    "won": _text(basis.goals[(q.quarter, s.key)].won, "0.0001"),
                    "created": _text(basis.goals[(q.quarter, s.key)].created, "0.0001"),
                    "created_arr": _text(
                        basis.goals[(q.quarter, s.key)].created_arr, "0.01"
                    ),
                    "days": _text(basis.goals[(q.quarter, s.key)].days, "0.01"),
                }
                for s in basis.segments
            }
            for q in basis.schedule
        },
        "owners": [
            {
                "segment": o.segment,
                "id": o.id,
                "name": o.name,
                "allocated": o.allocated,
                "quota": None if o.quota is None else _text(o.quota, "0.01"),
                "days": o.days,
                "weight": _text(o.weight, "0.01"),
                "share": _text(o.share, "0.000001"),
                "opening": o.opening,
                "creation_share": _text(o.creation_share, "0.000001"),
            }
            for o in basis.owners
        ],
        "owner_goals": _owner_goals(basis),
        "owner_caveat": OWNER_CAVEAT,
        "caveat": CAVEAT,
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in basis.checks
        ],
    }
