"""What has happened, by lane and period: the periods themselves, and the atoms of a lane's cells.

A lane is any set of deals named by a key function: a segment, or an owner within a segment. Its
atoms for a period come three ways: as recorded, as forecast (the record plus what is expected
after the as-of date) and as the goal says. Each is built from things that add, so a lane's
parent is the sum of its children whatever the lane is.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import lanes_flows as flows
from . import lanes_rules as rules
from .fiscal import Window
from .history import creation_amounts
from .lanes_cells import FLOW_ATOMS
from .lanes_flows import Calendar, Flow, Leaf
from .report import Prepared

ZERO = Decimal(0)


def segment_of(d) -> str:
    return rules.segment_key(d.segment)


def owner_of(d) -> tuple[str, str]:
    return rules.segment_key(d.segment), rules.owner_key(d.owner_id)


@dataclass(frozen=True)
class Period:
    key: str
    kind: str  # year or quarter
    window: Window
    quarters: tuple[int, ...]  # the quarters whose wins and creation the period holds
    carried_through: (
        int  # a win whose deal was created in this origin or earlier is carried in
    )

    @property
    def buckets(self) -> tuple[int, ...]:
        return tuple(q + 1 for q in self.quarters)


def periods(cal: Calendar) -> tuple[Period, ...]:
    year = cal.year
    whole = Period(
        year.label, "year", Window(year.label, cal.start, year.end), (0, 1, 2, 3), 0
    )
    return (whole,) + tuple(
        Period(key, "quarter", w, (q,), q)
        for q, (key, w) in enumerate(zip(year.quarter_keys, cal.quarters))
    )


def standing(window: Window, as_of: date) -> str:
    if window.end <= as_of:
        return "closed"
    return "not started" if window.start >= as_of else "in progress"


def facts(state: Prepared, cal: Calendar, lane=segment_of):
    """Wins by (lane, quarter, origin) and created deals by (lane, quarter), as recorded through
    the as-of date; the first recorded amount is a created deal's pipeline."""
    amounts = creation_amounts(state.pop)
    wins: dict[Leaf, Flow] = {}
    created: dict[tuple, tuple[Decimal, Decimal]] = {}
    for d in state.pop.deals:
        key = lane(d)
        if cal.start < d.created <= state.as_of:
            n, arr = created.get((key, cal.bucket(d.created)), (ZERO, ZERO))
            created[(key, cal.bucket(d.created))] = (
                n + 1,
                arr + (amounts[d.id] or ZERO),
            )
        if d.is_won and cal.start < d.close <= state.as_of:
            leaf = (key, cal.bucket(d.close) - 1, cal.bucket(d.created))
            days = Decimal((d.close - d.created).days)
            wins[leaf] = wins.get(leaf, flows.ZERO_FLOW) + Flow(Decimal(1), d.arr, days)
    return wins, created


def group(deals, lane) -> dict:
    """``deals`` by lane."""
    out = defaultdict(list)
    for d in deals:
        out[lane(d)].append(d)
    return out


def open_on(deals, day: date) -> int:
    return sum(
        1 for d in deals if d.created <= day and (not d.is_closed or d.close > day)
    )


def cohort(deals, end: date, horizon: int) -> tuple[int, int]:
    """(won within the horizon, created) among the deals created in the year ending
    ``horizon`` days before ``end``."""
    last = end - timedelta(days=horizon)
    mine = [d for d in deals if last - timedelta(days=horizon) < d.created <= last]
    return sum(
        1 for d in mine if d.is_won and (d.close - d.created).days <= horizon
    ), len(mine)


def by_lane(figures) -> dict:
    """``figures`` (keyed by a lane and then more) regrouped by lane, so a lane's own are quick."""
    out = defaultdict(list)
    for key, value in figures.items():
        out[key[0]].append((key[1:], value))
    return out


def flow_atoms(period: Period, lane, wins, created) -> dict[str, Decimal]:
    """The period's wins and creation of ``lane``, from ``by_lane`` groups of each."""
    out = dict.fromkeys(FLOW_ATOMS, ZERO)
    for (q, origin), f in wins.get(lane, ()):
        if q in period.quarters:
            part = "carried" if origin <= period.carried_through else "new"
            for name, value in (("won", f.wins), ("bookings", f.bookings)):
                out[name] += value
                out[f"{name}_{part}"] += value
            out["days"] += f.days
    for (j,), (n, arr) in created.get(lane, ()):
        if j in period.buckets:
            out["created"] += n
            out["created_arr"] += arr
    return out


def modes(state, period: Period, mine, key, record, forecast, goal) -> dict:
    """A lane's atoms in a period in the three modes, from ``mine`` (its deals). ``record`` and
    ``forecast`` are each the (wins, created) pair of ``by_lane`` groups; ``goal`` is the lane's
    goal atoms, or None where it has none."""
    as_of = state.ground.as_of
    held = (
        Decimal(open_on(mine, period.window.start))
        if period.window.start <= as_of
        else None
    )
    won, n = cohort(mine, min(period.window.end, as_of), state.params.horizon_days)
    return {
        "actual": {
            **flow_atoms(period, key, *record),
            "open": held,
            "cohort_wins": Decimal(won),
            "cohort_n": Decimal(n),
        },
        "forecast": {**flow_atoms(period, key, *forecast), "open": held},
        "goal": goal,
    }
