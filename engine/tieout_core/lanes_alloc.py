"""Owner goals: a segment's goal shared out by the plan-start roster, and nothing else.

Ownership, segment and quota have no history in the files, so today's values stand in for the plan
start; but who was on the roster is known: ``roster_at`` hides everything dated after the plan
date. A person's weight is their annual quota times the days they are employed in the fiscal year,
and a segment's goal is shared in proportion to weight, in whole units with the largest remainders
taking the leftover, so the shares add to the goal exactly. Someone hired after the plan date has
no weight and no row in the allocation: they had no original allocation. A segment with nobody to
share to gives its whole goal to its unassigned bucket rather than lose it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from . import lanes_flows as flows
from . import lanes_rules as rules
from .fiscal import FiscalYear
from .roster import Member, roster_at

ZERO = Decimal(0)
UNASSIGNED = rules.UNASSIGNED
UNITS = {  # the unit each goal figure is written in
    "bookings": "0.01",
    "won": "0.0001",
    "created": "0.0001",
    "created_arr": "0.01",
    "days": "0.01",
}


@dataclass(frozen=True)
class Weight:
    quota: Decimal | None
    days: (
        int  # days employed in the fiscal year, on the roster as known at the plan date
    )
    weight: Decimal  # quota times days


def weights(
    members: Sequence[Member], plan: date, fy: FiscalYear
) -> dict[tuple[str, str], Weight]:
    """Each person on the roster as known on ``plan``, by (segment, id)."""
    out = {}
    for m in roster_at(members, plan):
        last = fy.end if m.end is None else min(fy.end, m.end)
        days = max((last - max(fy.start, m.start)).days + 1, 0)
        quota = m.annual_quota
        out[(rules.segment_key(m.segment), m.id)] = Weight(
            quota, days, (quota or ZERO) * days
        )
    return out


def split_goal(goal, by_weight: Mapping[str, Decimal]):
    """``goal`` (any dataclass of the goal figures) shared by weight, each figure to its unit, with
    the unassigned bucket added: it takes the whole goal if nobody has weight, and nothing if
    somebody has."""
    keys = [k for k in by_weight if k != UNASSIGNED]
    shares = [by_weight[k] for k in keys]
    nobody = not sum(shares, ZERO)
    keys.append(UNASSIGNED)
    shares.append(Decimal(1) if nobody else ZERO)
    parts = {
        name: flows.apportion(getattr(goal, name), shares, unit)
        for name, unit in UNITS.items()
    }
    return {
        k: replace(goal, **{name: parts[name][i] for name in UNITS})
        for i, k in enumerate(keys)
    }


@dataclass(frozen=True)
class OwnerBasis:
    """What is frozen about one owner in one segment at the plan date."""

    segment: str
    id: str
    name: str
    allocated: bool  # on the plan-start roster (or the unassigned bucket): has a goal, perhaps zero
    quota: Decimal | None
    days: int
    share: Decimal  # of the segment's goal
    opening: int  # deals open at the plan date
    creation_share: Decimal  # of the segment's deals created in the trailing year


def owner_basis(
    deals, members, cutoff: date, fy: FiscalYear, trailing_days: int, goals, segments
):
    """(owners, owner goals) for the ``segments``, from ``deals`` as known at ``cutoff``, the
    roster as known then, and each segment's goal in each quarter."""
    held = weights(members, cutoff, fy)
    names = {m.id: m.name for m in members if m.name}
    opening: dict[tuple[str, str], int] = {}
    made: dict[tuple[str, str], int] = {}
    since = cutoff - timedelta(days=trailing_days)
    for d in deals:
        key = (rules.segment_key(d.segment), rules.owner_key(d.owner_id))
        names.setdefault(d.owner_id, d.owner_name)
        opening[key] = opening.get(key, 0) + (not d.is_closed)
        made[key] = made.get(key, 0) + (since < d.created <= cutoff)
    owners, owner_goals = [], {}
    for seg in segments:
        seen = {
            k
            for k in (*opening, *made)
            if k[0] == seg and (opening.get(k) or made.get(k))
        }
        seen |= {k for k, w in held.items() if k[0] == seg and w.days}
        mine = sorted({k[1] for k in seen} | {UNASSIGNED})  # a fixed order, for ties
        scale = {k: held[(seg, k)].weight for k in mine if (seg, k) in held}
        total, created = (
            sum(scale.values(), ZERO),
            sum((made.get((seg, k), 0) for k in mine), 0),
        )
        shared = {k: Decimal(1) if total == 0 and k == UNASSIGNED else ZERO for k in mine}  # fmt: skip
        shared.update({k: w / total for k, w in scale.items()} if total else {})
        for k in sorted(mine, key=lambda k: (k == UNASSIGNED, -shared[k], k)):
            w = held.get((seg, k))
            owners.append(
                OwnerBasis(
                    seg,
                    k,
                    "Unassigned" if k == UNASSIGNED else names.get(k) or k,
                    w is not None or k == UNASSIGNED,
                    w.quota if w else None,
                    w.days if w else 0,
                    shared[k],
                    opening.get((seg, k), 0),
                    Decimal(made.get((seg, k), 0)) / created if created else ZERO,
                )
            )
        for (quarter, s), goal in goals.items():
            if s == seg:
                for k, g in split_goal(goal, scale).items():
                    owner_goals[(quarter, seg, k)] = g
    return tuple(owners), owner_goals
