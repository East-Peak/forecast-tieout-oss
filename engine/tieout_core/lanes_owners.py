"""Owner lanes: what each person (or bucket) holds beneath a segment.

A segment's figures are the pooled model's and are never changed here. An owner's figures are the
segment's, shared out: recorded deals by their own owner; each existing deal's expected wins by
its owner; future creation by each rep's ramped exposure where the capacity term is adopted and
by the frozen creation shares otherwise; program pipeline in a bucket of its own, since a program
is not a person's production; hires a plan adds in one "planned hires" bucket per segment, since
they are not real people. The segment's expected wins and creation are then apportioned over its
owners in proportion to what the owners' own deals and exposure imply, to the last unit, so the
owners add back to the segment exactly in every cell and every part of a split.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from . import lanes_flows as flows
from . import lanes_rules as rules
from .capacity import project
from .lanes_alloc import UNASSIGNED
from .lanes_cells import owner_cell
from .lanes_facts import owner_of
from .lanes_flows import Flow
from .records import Check

ZERO, ONE = Decimal(0), Decimal(1)
TOLERANCE = Decimal("0.000001")
PROGRAMS, PLANNED = "programs", "planned-hires"
KIND = {UNASSIGNED: "unassigned", PROGRAMS: "programs", PLANNED: "planned_hires"}
ORDER = {"owner": 0, "unassigned": 1, "programs": 2, "planned_hires": 3}
LABEL = {UNASSIGNED: "Unassigned", PROGRAMS: "Programs", PLANNED: "Planned hires"}


def kind(owner: str) -> str:
    return KIND.get(owner, "owner")


# ---------------------------------------------------------------- what is expected


def series(state, basis, cal, hires, inflows, segments) -> dict[tuple, list[Decimal]]:
    """Deals created on each day to the year's end, by (segment, owner or bucket)."""
    g = state.ground
    horizon = (cal.year.end - g.as_of).days
    new = g.model.new_pipeline
    seg_share = {s.key: s.creation_share for s in basis.segments}
    out: dict[tuple, list[Decimal]] = {}
    if g.cap.adopted:
        for m in g.cap.members:
            per_day = project(g.cap.fit, [m], g.as_of, g.horizon_days).per_day
            out[(rules.segment_key(m.segment), m.id)] = list(per_day[:horizon])
        planned = defaultdict(list)
        for h in hires:
            planned[rules.segment_key(h.segment)].append(h)
        for seg, hs in planned.items():
            per_day = project(g.cap.fit, hs, g.as_of, g.horizon_days).per_day
            out[(seg, PLANNED)] = list(per_day[:horizon])
    else:
        left = {m.id: m.end for m in g.cap.members if m.end is not None}
        days = [g.as_of + timedelta(days=t) for t in range(1, horizon + 1)]
        for seg in segments:
            share = {
                o.id: o.creation_share
                for o in basis.owners
                if o.segment == seg and o.creation_share
            }
            lanes = {k: [ZERO] * horizon for k in (*share, UNASSIGNED)}
            for t, day in enumerate(days):
                here = {k: w for k, w in share.items() if left.get(k, day) >= day}
                total = sum(here.values(), ZERO)
                if not total:
                    here, total = {UNASSIGNED: ONE}, ONE
                rate = new.created_per_day * seg_share.get(seg, ZERO)
                for k, w in here.items():
                    lanes[k][t] = rate * w / total
            out.update({(seg, k): v for k, v in lanes.items() if any(v)})
    extra = flows.inflow_series(inflows, new.mean_created_arr, horizon)
    if any(extra):
        for seg in segments:
            if seg_share.get(seg):
                out[(seg, PROGRAMS)] = [seg_share[seg] * x for x in extra]
    return out


def series_check(lanes: dict, whole: dict) -> Check:
    """The owners' creation on each day adds to its segment's."""
    days = len(next(iter(whole.values()), []))
    sums = {s: [ZERO] * days for s in whole}
    for (seg, _), per_day in lanes.items():
        sums[seg] = [a + b for a, b in zip(sums[seg], per_day)]
    off = [
        s
        for s, per_day in whole.items()
        if any(abs(a - b) > TOLERANCE for a, b in zip(sums[s], per_day))
    ]
    return Check(
        "owner creation adds to the segment's",
        not off,
        f"{days} days of creation by owner sum to each segment's"
        if not off
        else f"differs: {off}",
    )


def _spread(total: Decimal, weights: dict, seg: str, unit: str) -> dict:
    """``total`` over the lanes in proportion to ``weights``; with none to weigh, to the
    segment's unassigned bucket."""
    keys = sorted(weights)
    w = [weights[k] for k in keys]
    if not sum(w, ZERO):
        keys, w = [(seg, UNASSIGNED)], [ONE]
    return dict(zip(keys, flows.apportion(total, w, unit)))


def remainder(state, cal, series_, priced: dict, tied: dict, made: dict):
    """The segments' expected wins and creation (``tied``, ``made``) shared over owners: by
    leaf, so every quarter and every carried-in or created-in-period split adds back. Modeled
    wins are weighed at the price the segment's own modeled wins were given (``priced``, already
    normalized to the pooled total), so an owner's modeled bookings are consistent with it."""
    g = state.ground
    raw = flows.existing_flows(g.model, g.pop.deals, g.as_of, cal, lane=owner_of)
    wins, created = flows.new_flows(g.model, series_, g.as_of, cal)
    for (lane, q, origin), f in wins.items():
        whole = priced.get((lane[0], q, origin), flows.ZERO_FLOW)
        price = whole.bookings / whole.wins if whole.wins else ZERO
        at = Flow(f.wins, f.wins * price, f.days)
        raw[(lane, q, origin)] = raw.get((lane, q, origin), flows.ZERO_FLOW) + at
    leaves: dict = defaultdict(dict)
    for (lane, q, origin), f in raw.items():
        leaves[(lane[0], q, origin)][lane] = f
    out = {}
    for (seg, q, origin), total in tied.items():
        mine = leaves[(seg, q, origin)]
        pieces = [
            _spread(
                getattr(total, name),
                {k: getattr(f, name) for k, f in mine.items()},
                seg,
                unit,
            )
            for name, unit in (
                ("wins", "0.0001"),
                ("bookings", "0.01"),
                ("days", "0.01"),
            )
        ]
        for lane in sorted(set().union(*pieces)):
            out[(lane, q, origin)] = Flow(*(p.get(lane, ZERO) for p in pieces))
    counts: dict = defaultdict(dict)
    for (lane, j), n in created.items():
        counts[(lane[0], j)][lane] = n
    out_made = {}
    for (seg, j), (n, arr) in made.items():
        weights = counts[(seg, j)]
        counted = _spread(n, weights, seg, "0.0001")
        priced = _spread(arr, weights, seg, "0.01")
        for lane in sorted(set(counted) | set(priced)):
            out_made[(lane, j)] = (counted.get(lane, ZERO), priced.get(lane, ZERO))
    return out, out_made


# ---------------------------------------------------------------- goals and rows


def goal_atoms(basis, entries, cal_start, period, quarter_keys, seg, owner):
    """An owner's goal atoms in a period from the frozen basis; None where nothing was allocated
    (someone not on the plan-start roster), though an opening stock may still be on record."""
    entry = entries.get((seg, owner))
    if entry is None:
        return None
    mine = [
        basis.owner_goals.get((quarter_keys[q], seg, owner)) for q in period.quarters
    ]
    atoms = dict.fromkeys(("created", "created_arr", "won", "bookings", "days"))
    if all(m is not None for m in mine):
        for name in atoms:
            atoms[name] = sum((getattr(m, name) for m in mine), ZERO)
    atoms["open"] = Decimal(entry.opening) if period.window.start == cal_start else None
    return atoms


def present(grid: dict) -> set:
    """The lanes with anything to show in some period, mode or column; a lane with nothing
    anywhere is left out."""
    return {
        lane
        for by_lane in grid.values()
        for lane, by_mode in by_lane.items()
        for atoms in by_mode.values()
        if atoms and any(v for v in atoms.values() if v is not None)
    }


def ordered(lanes: set, year: dict, segments: list, names: dict) -> list:
    """Owners under each segment in the segments' order: people first by the year's bookings goal,
    largest first (those with no goal last), then by what they have booked, then name; then the
    unassigned, program and planned-hire buckets."""

    def key(lane):
        seg, owner = lane
        by = year[lane]
        goal = by["goal"] and by["goal"].get("bookings")
        return (
            segments.index(seg),
            ORDER[kind(owner)],
            goal is None,
            -(goal or ZERO),
            -by["actual"]["bookings"],
            names.get(owner, owner),
            owner,
        )

    return sorted(lanes, key=key)


def allocation(lane, entry, name: str) -> str:
    owner = lane[1]
    k = kind(owner)
    if k == "programs":
        return "Program pipeline: not a person's production; it follows the segment's frozen creation share."
    if k == "planned_hires":
        return "Hires this scenario plans: not real people; their ramped exposure where the capacity term is adopted."
    if k == "unassigned":
        return "Deals with no owner on file, and any goal left with nobody on the plan-start roster to share it to."
    if entry is None or not entry.allocated:
        return (
            f"No allocation: {name} was not a quota-carrying member of this segment on the "
            "plan-start roster (for example, hired after the plan date), so there is no original allocation."
        )
    quota = "no quota" if entry.quota is None else f"a ${entry.quota:,.0f} annual quota"
    return (
        f"Allocated goal: {entry.share:.1%} of the segment's, from {quota} and "
        f"{entry.days} days employed in the year on the plan-start roster. A planning "
        "allocation, not a measure of performance. Quota and roster segment are today's values "
        "standing in for the plan date; only employment dates and deals are cut at it."
    )


def row(lane, rank: int, by_mode: dict, name: str, text: str) -> dict:
    seg, owner = lane
    return {
        "path": ["segment", seg, "owner", owner],
        "label": LABEL.get(owner, name),
        "parent": ["segment", seg],
        "kind": kind(owner),
        "rank": rank,
        "allocation": text,
        "sizes": None,
        "cells": {c.key: owner_cell(c, by_mode) for c in rules.COLUMNS},
    }
