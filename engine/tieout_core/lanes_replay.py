"""Replay the lanes against the raw deals and the forward function.

The contract can only check what the file holds; whether the actuals are what the deals say, and
whether the company's forecast is what the whole forward function gives with the scenario's
people and programs, needs the model. This module recomputes the company row's actuals straight
from the deals (a different path from the one that wrote them) and its forecast bookings from
``Scenario``. The generator's ``--verify`` runs it over every committed lanes file, and so does
the test suite.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .actions import Scenario
from .figures import cents
from .history import creation_amounts
from .report import Prepared

ZERO = Decimal(0)
RATE_PLACES_HALF = Decimal("0.00005")  # a rate is written to four places


def replay(state: Prepared, doc: dict, hires, inflows) -> list[str]:
    """Every disagreement between the company row of ``doc`` and the deals and the model."""
    if "unavailable" in doc:
        return []
    g, deals = state.ground, state.pop.deals
    forecast = Scenario(g).forecast(tuple(hires), tuple(inflows))
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
