"""Replay the lanes against the raw deals and the forward function.

The contract can only check what the file holds; whether the actuals are what the deals say, and
whether the company's forecast is what the whole forward function gives with the scenario's
people and programs, needs the model. This module recomputes the company row's actuals straight
from the deals (a different path from the one that wrote them) and its forecast bookings from
``Scenario``. The generator's ``--verify`` runs it over every committed lanes file, and so does
the test suite.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .actions import Scenario
from .figures import cents
from .history import creation_amounts
from .report import Prepared

ZERO = Decimal(0)
RATE_PLACES_HALF = Decimal("0.00005")  # a rate is written to four places


def replay(state: Prepared, doc: dict, hires, inflows, lift=None) -> list[str]:
    """Every disagreement between the company row of ``doc`` and the deals and the model."""
    if "unavailable" in doc:
        return []
    g, deals = state.ground, state.pop.deals
    forecast = Scenario(g).forecast(tuple(hires), tuple(inflows), lift)
    amounts = creation_amounts(state.pop)
    horizon = state.params.horizon_days
    found: list[str] = []
    for p in doc["periods"]:
        cells = p["rows"][0]["cells"]
        first, last = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        end = min(last, g.as_of)
        wins = [d for d in deals if d.is_won and first <= d.close <= end]
        made = [d for d in deals if first <= d.created <= end]
        want = {
            ("created", "actual"): Decimal(len(made)),
            ("created_arr", "actual"): sum((amounts[d.id] or ZERO for d in made), ZERO),
            ("won", "actual"): Decimal(len(wins)),
            ("bookings", "actual"): sum((d.arr for d in wins), ZERO),
        }
        if first - timedelta(days=1) <= g.as_of:
            want[("open", "actual")] = Decimal(
                sum(
                    1
                    for d in deals
                    if d.created < first and (not d.is_closed or d.close >= first)
                )
            )
        months = [w.label for w in g.windows if first <= w.end <= last]
        shown = sum((cents(forecast.window_total(m)) for m in months), ZERO)
        want[("bookings", "forecast")] = want[("bookings", "actual")] + shown
        for (column, mode), value in want.items():
            got = cells[column][mode]
            if got is None or Decimal(got) != value:
                found.append(
                    f"{p['key']}: {column} {mode} is {got}, the deals give {value}"
                )
        cohort = [
            d
            for d in deals
            if end - timedelta(days=2 * horizon)
            < d.created
            <= end - timedelta(days=horizon)
        ]
        rate = Decimal(
            sum(1 for d in cohort if d.is_won and (d.close - d.created).days <= horizon)
        ) / max(len(cohort), 1)
        got = cells["win_rate"]["actual"]
        if cohort and (got is None or abs(Decimal(got) - rate) > RATE_PLACES_HALF):
            found.append(
                f"{p['key']}: win_rate actual is {got}, the deals give {rate:.4f}"
            )
    return found


def records(state: Prepared, shard: dict) -> list[str]:
    """Every disagreement between the records shard and the raw deals: each set of each row and
    period rebuilt from the deals' own dates and the periods the shard names (not from the
    function that wrote it), and each record against its deal."""
    deals, as_of = state.pop.deals, state.as_of
    horizon = timedelta(days=state.params.horizon_days)
    expected: dict[tuple, set] = defaultdict(set)
    named: set[str] = set()
    for p in shard["periods"]:
        first, last = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        end = min(last, as_of)
        for d in deals:
            seg, who = d.segment or "unassigned", d.owner_id or "unassigned"
            where = (("total",), ("segment", seg), ("segment", seg, "owner", who))
            sets = []
            if d.created < first and (not d.is_closed or d.close >= first):
                sets.append("open")
            if first <= d.created <= end:
                sets.append("created")
            if d.is_won and first <= d.close <= end:
                sets.append("won_carried_in" if d.created < first else "won_created_in_period")  # fmt: skip
            if end - 2 * horizon < d.created <= end - horizon:
                sets.append("cohort")
                if d.is_won and d.close - d.created <= horizon:
                    sets.append("cohort_won")
            for name in sets:
                if name == "open" and first - timedelta(days=1) > as_of:
                    continue  # a period not begun has no opening stock to list
                named.add(d.id)
                for path in where:
                    expected[(path, p["key"], name)].add(d.id)
    found: list[str] = []
    given = {
        (tuple(r["path"]), key, name): ids
        for r in shard["rows"]
        for key, sets in r["periods"].items()
        for name, ids in sets.items()
    }
    for key in sorted(set(given) | set(expected), key=str):
        path, period, name = key
        mine = given.get(key)
        if mine is None and name == "open":
            mine = None if key not in expected else mine
        want = expected.get(key, set())
        got = set(mine or ())
        if got != want or len(mine or ()) != len(got):
            found.append(
                f"{period} {list(path)} {name}: the shard lists {len(got)}, the deals give {len(want)}"
            )
    by_id = {d.id: d for d in deals}
    if set(shard["records"]) != named:
        found.append("the shard holds records for deals no cell names, or lacks some")
    for i, r in shard["records"].items():
        d = by_id.get(i)
        if d is None or (r["segment"], r["owner"], r["created"], r["close"]) != (
            d.segment or "unassigned",
            d.owner_id or "unassigned",
            str(d.created),
            None if d.close is None else str(d.close),
        ):
            found.append(f"record {i} is not its deal")
    return found
