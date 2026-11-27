"""Replay a worksheet through the whole forward function.

The contract can only check what the report itself holds; the change in bookings at a setting
and the bookings a "needed alone" value reaches need the model. This module recomputes every one
of them from the prepared state, by ``Scenario`` (the full forward function, not the probe the
section was written with), and from the numbers the report serializes: the setting as written is
fed back in, so "this value reaches the target" is shown true when replayed. The generator's
``--verify`` runs it over every committed report, and so does the test suite.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from . import actions
from . import worksheet_drivers as wd
from . import worksheet_rules as rules
from .actions import Scenario
from .figures import money
from .plan import NEXT_12, REST_OF_FY, Plan
from .report import Prepared


def replay(state: Prepared, report: dict, plan: Plan | None) -> list[str]:
    """Every disagreement between ``report['worksheet']`` and the model; empty when none."""
    w = report["worksheet"]
    if "unavailable" in w:
        return []
    g = state.ground
    hires, inflows = actions.plan_inputs(g, plan) if plan is not None else ((), ())
    scenario = Scenario(g)

    def run(adjusted):
        return Scenario(adjusted).forecast(hires, inflows)

    base = run(g)
    base_shown = scenario.bookings(base)
    target = g.fy_target
    found: list[str] = []
    for d in w["drivers"]:
        name = d["driver"]
        where = f"{report['inputs']['identity']['scenario']}/{name}"
        values = [
            rules.value_of(q, name)
            for q in state.quarters
            if rules.eligible(q, name)[0] and rules.value_of(q, name) is not None
        ]
        settings = rules.historical_settings(values)
        h = d["historical"]
        if h is not None and settings is None:
            found.append(
                f"{where}: historical settings are offered without the evidence"
            )
        elif h is not None:
            for side in ("low", "high"):
                exact = getattr(settings, side)
                shown = scenario.bookings(run(wd.with_setting(g, name, exact)))
                for window in (REST_OF_FY, NEXT_12):
                    want = money(shown[window] - base_shown[window])
                    if h[side]["change"][window] != want:
                        found.append(
                            f"{where}: the {side} setting's change in {window} is {h[side]['change'][window]}, the model gives {want}"
                        )
        n = d["needed_alone"]
        if n is None:
            continue
        if n["scale"] is not None:
            adjusted = wd.with_cycle_scale(g, Fraction(n["scale"]))
        elif n["outcome"] == wd.COVERED or n["reason"] == wd.NO_EFFECT:
            adjusted = g
        else:
            adjusted = wd.with_setting(g, name, Decimal(n["value"]))
        reached = scenario.fiscal_year(run(adjusted))
        if money(reached) != n["achieved_fiscal_year_bookings"]:
            found.append(
                f"{where}: needed alone reaches {money(reached)} when replayed, the report says {n['achieved_fiscal_year_bookings']}"
            )
        if (reached >= target) != n["reaches_target"]:
            found.append(
                f"{where}: reaches_target is {n['reaches_target']}, the replay says {reached >= target}"
            )
        if n["outcome"] == wd.SOLVES and n["overshoot"] != money(reached - target):
            found.append(
                f"{where}: the overshoot is {n['overshoot']}, the replay says {money(reached - target)}"
            )
    return found
