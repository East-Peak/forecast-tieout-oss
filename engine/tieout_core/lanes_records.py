"""The records shard: which deals each actual cell of the grid is made of.

The browser lists and never sums. For every row and period the shard names, by deal id, the deals
behind the cells whose actual is a count or a sum of deals: the deals open at the period's start,
the deals created in it, the deals won in it (split by whether their pipeline was carried in or
created in the period), and the creation cohort behind the win rate with the cohort's wins. A
cell's count is then the number of ids, its ARR the sum of their recorded amounts, a cycle the sum
of their days. Each deal is stored once, in ``records``, with what a drill needs; the cells
reference it by id. Only deals on the file are named: what the model expects to be created or won
after the as-of date appears as contribution rows on a cell, never here. Membership is a fact, so
it is the same in every scenario and there is one shard per company.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .figures import money
from .history import creation_amounts
from .lanes_contract import SCHEMA_VERSION
from .lanes_facts import Period, owner_of, periods
from .lanes_flows import Calendar

SETS = (
    "open",
    "created",
    "won_carried_in",
    "won_created_in_period",
    "cohort",
    "cohort_won",
)
WON = ("won_carried_in", "won_created_in_period")
USED_BY = {  # the sets a column's actual is made of
    "open": ["open"],
    "created": ["created"],
    "created_arr": ["created"],
    "win_rate": ["cohort_won", "cohort"],  # numerator, denominator
    "cycle": list(WON),
    "won": list(WON),
    "avg_won_arr": list(WON),
    "bookings": list(WON),
}
CAVEAT = (
    "These are the deals on the file. A deal's owner and segment are today's, which stand in for "
    "what they were: the files keep no history of either. What the model expects after the as-of "
    "date is never a deal here."
)


def _hits(d, p: Period, cal: Calendar, as_of: date, horizon: int) -> list[str]:
    """The sets of ``p`` that deal ``d`` belongs to."""
    out = []
    held = d.created <= p.window.start and (not d.is_closed or d.close > p.window.start)
    if p.window.start <= as_of and held:
        out.append("open")
    if cal.start < d.created <= as_of and cal.bucket(d.created) in p.buckets:
        out.append("created")
    if (
        d.is_won
        and cal.start < d.close <= as_of
        and cal.bucket(d.close) - 1 in p.quarters
    ):
        carried = cal.bucket(d.created) <= p.carried_through
        out.append(WON[0] if carried else WON[1])
    last = min(p.window.end, as_of) - timedelta(days=horizon)
    if last - timedelta(days=horizon) < d.created <= last:
        out.append("cohort")
        if d.is_won and (d.close - d.created).days <= horizon:
            out.append("cohort_won")
    return out


def _record(d, first: Decimal | None, stage: str) -> dict:
    seg, owner = owner_of(d)
    return {
        "id": d.id,
        "name": d.name,
        "segment": seg,
        "owner": owner,
        "owner_name": d.owner_name,
        "created": str(d.created),
        "close": None if d.close is None else str(d.close),
        "stage": stage,
        "status": "won" if d.is_won else "lost" if d.is_closed else "open",
        "arr_first": None if first is None else money(first),
        "arr": None if d.arr is None else money(d.arr),
    }


def document(state, company: str) -> dict:
    """The shard for ``company``: ``state`` is its prepared report state (or anything with the
    deals, the as-of date, the profile and the fit parameters)."""
    cal = Calendar(state.profile.fiscal_year)
    as_of, horizon = state.as_of, state.params.horizon_days
    amounts = creation_amounts(state.pop)
    grid = periods(cal)
    held: dict[tuple, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    records = {}
    for d in state.pop.deals:
        seg, owner = owner_of(d)
        paths = (("total",), ("segment", seg), ("segment", seg, "owner", owner))
        for p in grid:
            for name in _hits(d, p, cal, as_of, horizon):
                for path in paths:
                    held[(path, p.key)][name].append(d.id)
                if d.id not in records:
                    try:
                        stage = state.profile.stage_name(d.stage)
                    except StopIteration:
                        stage = d.stage
                    records[d.id] = _record(d, amounts.get(d.id), stage)
    rows = []
    for path in sorted({k[0] for k in held}, key=lambda x: (len(x) > 1, x)):
        rows.append(
            {
                "path": list(path),
                "periods": {
                    p.key: {
                        name: None
                        if name == "open" and p.window.start > as_of
                        else sorted(held[(path, p.key)][name])
                        for name in SETS
                    }
                    for p in grid
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "company": company,
        "as_of": str(as_of),
        "fiscal_year": cal.year.label,
        "horizon_days": horizon,
        "periods": [
            {
                "key": p.key,
                "start": str(p.window.start + timedelta(days=1)),
                "end": str(p.window.end),
            }
            for p in grid
        ],
        "sets": USED_BY,
        "caveat": CAVEAT,
        "records": dict(sorted(records.items())),
        "rows": rows,
    }


def _flat(x) -> bool:
    return not any(
        isinstance(v, dict | list) for v in (x.values() if isinstance(x, dict) else x)
    )


def _dump(x, depth: int) -> str:
    if not isinstance(x, dict | list) or _flat(x):
        return json.dumps(x, sort_keys=True, ensure_ascii=False)
    pad, end = "  " * (depth + 1), "  " * depth
    if isinstance(x, list):
        body = ",\n".join(pad + _dump(v, depth + 1) for v in x)
        return f"[\n{body}\n{end}]"
    body = ",\n".join(
        f"{pad}{json.dumps(k, ensure_ascii=False)}: {_dump(v, depth + 1)}"
        for k, v in sorted(x.items())
    )
    return f"{{\n{body}\n{end}}}"


def text(doc: dict) -> str:
    """The shard as written: sorted keys, two-space indent, and a list of ids or a record on one
    line, so a file of thousands of ids stays small and a diff stays readable."""
    return _dump(doc, 0) + "\n"
