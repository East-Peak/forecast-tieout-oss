"""The report's ``worksheet`` section: what moves the outcome, and the plan's bridge.

It is written for every scenario by ``finish``, from the immutable prepared state and the plan
in force, with no simulation: every figure is an expectation, measured around the scenario in
force (the applied plan, or the roster as signed) for the rest of the fiscal year and the next
twelve months. Four operating drivers are moved one at a time; the section also restates the
two unit actions, the bridge from as signed to the working plan, the summary figures and, for
the as-signed forecast only, the top-down against bottom-up chain. Where a figure exists
elsewhere in the report it is carried as ``{value, source}`` with ``source`` a JSON pointer, and
the contract checks that the value is what the pointer finds, so there is one source of truth.

Every sentence a screen shows is written here from structured fields, in words: a sentence
carries no digit that a field does not carry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from . import worksheet_drivers as wd
from . import worksheet_rules as rules
from .actions import Ground
from .figures import cents, money, number
from .fiscal import add_months
from .fit import RECENCY, FitParams
from .forecast import Inflow, Lift
from .plan import NEXT_12, REST_OF_FY
from .records import Check
from .roster import Member, ramped_ae_months
from .worksheet_evidence import observe
from .worksheet_rules import (
    CYCLE_DAYS,
    DRIVERS,
    PRODUCTIVITY,
    WIN_RATE,
    WON_ARR,
    Quarter,
)

ZERO = Decimal(0)
CENT = Decimal(
    "0.01"
)  # a target with fractions of a cent can differ from displayed figures by one
WINDOWS = (REST_OF_FY, NEXT_12)

SENSITIVITY_NOTE = (
    "Each change is a conditional change in expected bookings, measured one driver at a time "
    "around the plan in force. It is not a forecast and not a cause, and the bars are never "
    "summed: drivers act together, not alone."
)
EXPECTATION_NOTE = (
    "Every figure here is an expected value from the forward function. No simulation is run, so "
    "no range is attached to any sensitivity."
)
CHAIN_NOTE = (
    "The chain reads the as-signed forecast: the roster as signed and nothing planned. It does "
    "not respond to the plan in force, so it is never mixed with working-plan figures."
)
ACTIONS_NOTE = (
    "The two unit actions are measured around the roster as signed, as in the actions section, "
    "and are restated here so that one number stands for one thing."
)
BRIDGE_ORDER_NOTE = (
    "Each contribution is the extra bookings from adding that item to everything above it, in "
    "the declared order (hires first, then programs, each in the plan's order), so the steps "
    "sum exactly to the working plan. Contributions depend on the order; they are not "
    "stand-alone effects."
)

FORMS = {
    WIN_RATE: ("fraction", "share of created deals won", "percent"),
    WON_ARR: ("dollars", "dollars of ARR per won deal", "money"),
    CYCLE_DAYS: ("days", "days from creation to win", "decimal"),
}
LABELS = {
    WIN_RATE: "Win rate of new pipeline",
    WON_ARR: "Won ARR per new win",
    PRODUCTIVITY: "Creation productivity",
    CYCLE_DAYS: "Cycle length of new pipeline",
}
APPLIES = {
    WIN_RATE: (
        "The share of deals created after the as-of date that are won, for organic, "
        "hire-generated and program pipeline alike. Open deals and actuals are untouched."
    ),
    WON_ARR: (
        "The mean ARR of each win among deals created after the as-of date. Creation counts "
        "and the program dollars-to-deals conversion are unchanged."
    ),
    CYCLE_DAYS: (
        "Days from creation to win for deals created after the as-of date. Each win-time "
        "sample is scaled and rounded up to whole days; weights, probability and size are "
        "unchanged."
    ),
}
PRODUCTIVITY_ADOPTED = (
    "created deals per ramped AE-month",
    (
        "Deals created per ramped AE-month, for the signed roster and any planned hires, after "
        "the as-of date. Open deals and actuals are untouched."
    ),
)
PRODUCTIVITY_FLAT = (
    "organic deals per day",
    (
        "Organic deals created per day after the as-of date. The capacity term is not in use "
        "for this company, so headcount is not tied to creation here. Open deals and actuals "
        "are untouched."
    ),
)

GATE_WORDS = {
    WIN_RATE: "A quarter counts when its deals have had the full horizon to win and at least "
    "twenty deals were created in it.",
    WON_ARR: "A quarter counts when its deals have had the full horizon to win and at least "
    "five of them were won.",
    CYCLE_DAYS: "A quarter counts when its deals have had the full horizon to win and at least "
    "five of them were won.",
    PRODUCTIVITY: "A quarter counts when at least twenty deals were created in it and there was "
    "capacity to divide by. Creation is final the day a quarter ends, so there is no waiting.",
}
SETTINGS_RULE = (
    "The low and high settings are the means of the lower and the upper half of the observed "
    "quarters; with an odd number of quarters the middle one is in neither half."
)

OUTCOME_LABELS = {
    wd.SOLVES: "Solves mathematically: this value, alone, takes fiscal-year bookings to target.",
    wd.COVERED: "Already at or ahead of target: nothing needs to change.",
    wd.CANNOT: "Cannot close the gap alone.",
}
STEPPED_LABEL = (
    "Solves mathematically, stepped: win times are whole days, so there is no exact root. This "
    "is the largest setting that reaches the target, and it overshoots by the amount shown."
)
REASON_LABELS = {
    wd.BOUNDED_AT_ONE: (
        "Even a win rate of one hundred percent leaves fiscal-year bookings short of target; the "
        "bookings reached at that bound are shown."
    ),
    wd.NO_EFFECT: (
        "Changing it does not move expected bookings inside the fiscal year, so no value closes "
        "the gap."
    ),
    wd.ZERO_DAYS_SHORT: (
        "Even if every new win came on the day its deal was created, fiscal-year bookings stay "
        "short of target, because too little pipeline is created inside the year; the bookings "
        "reached at zero days are shown."
    ),
}
INSIDE_LABEL = (
    "Inside what the company has done: the value lies between the lowest and the highest "
    "quarter observed."
)
BEYOND_LABEL = (
    "Beyond any observed quarter: the value lies outside the lowest and the highest quarter "
    "observed, so reaching it is an extrapolation that the history does not show."
)
NO_HISTORY_LABEL = (
    "No historical range is offered, so this value cannot be set beside what the company has "
    "done."
)
GATE_FAILED = (
    "Too few quarters pass the gate, so no historical settings are offered and there are no "
    "bars. A stress value can still be entered."
)
RECENCY_LIMITATION = (
    "The fit in use learns from every deal created in its recent window, young deals included, "
    "while these quarters are complete and matured, so they are older than that fit and may "
    "not describe it."
)
RAMP_LIMITATION = (
    "Each quarter is read against the current fitted ramp curve and the roster that actually "
    "worked, not against a curve refitted for that quarter."
)
FLAT_LIMITATION = (
    "Each quarter is organic deals created per day of the quarter; the capacity term is not in "
    "use, so headcount plays no part."
)
CYCLE_LIMITATION = (
    "A quarter's cycle is the plain mean days of its wins, while the fit in use weights each "
    "day, so the two are close in kind but not the same measure."
)


NO_WIN_TIMES = (
    "There is no win-time evidence for new pipeline, so its cycle length has no current value and "
    "cannot be moved."
)
ZERO_CYCLE = (
    "Wins already come on the day a deal is created, so scaling the cycle cannot change it: there "
    "is no setting to move to and no historical setting to offer."
)
SUB_CENT_NOTE = "The shortfall is less than one cent, so the figures shown look equal; the gap is not closed."


def _fmt(driver: str, value: Decimal) -> str:
    if driver == WON_ARR:
        return money(value)
    return number(value, rules.PRECISION[driver])


def _per_window(values: dict[str, Decimal]) -> dict[str, str]:
    return {w: money(values[w]) for w in WINDOWS}


def _ref(value, source: str) -> dict:
    return {"value": value, "source": source}


# ------------------------------------------------------------------ the drivers


@dataclass(frozen=True)
class Context:
    """What the driver rows read, none of it changed."""

    g: Ground
    probe: wd.Probe
    quarters: Sequence[Quarter]
    params: FitParams
    fy_target: Decimal


def unit_for(adopted: bool, driver: str) -> tuple[str, str, str, str]:
    """(unit, unit label, display, what it applies to)."""
    if driver == PRODUCTIVITY:
        unit, applies = PRODUCTIVITY_ADOPTED if adopted else PRODUCTIVITY_FLAT
        return unit, unit, "decimal", applies
    unit, label, display = FORMS[driver]
    return unit, label, display, APPLIES[driver]


def fit_window(driver: str, p: FitParams, as_of: date) -> tuple[date, date]:
    """The creation dates the fit in use learns this driver's current value from."""
    if driver == PRODUCTIVITY:
        return as_of - timedelta(days=p.trailing_days - 1), as_of
    if p.estimator == RECENCY:
        return add_months(as_of, -p.recency_months) + timedelta(days=1), as_of
    end = as_of - timedelta(days=p.horizon_days)
    return end - timedelta(days=p.trailing_days - 1), end


def limitation_text(
    driver: str, gate_passed: bool, estimator: str, adopted: bool
) -> str | None:
    """The limitation sentence, from the driver, the gate, the fit in use and the capacity term."""
    parts = []
    if not gate_passed:
        parts.append(GATE_FAILED)
    if driver != PRODUCTIVITY and estimator == RECENCY:
        parts.append(RECENCY_LIMITATION)
    if driver == PRODUCTIVITY:
        parts.append(RAMP_LIMITATION if adopted else FLAT_LIMITATION)
    if driver == CYCLE_DAYS:
        parts.append(CYCLE_LIMITATION)
    return " ".join(parts) or None


def _limitation(c: Context, driver: str, gate_passed: bool) -> str | None:
    return limitation_text(driver, gate_passed, c.params.estimator, c.g.cap.adopted)


def _observations(c: Context, driver: str) -> tuple[list[dict], list[Decimal]]:
    rows, values = [], []
    for q in c.quarters:
        ok, why = rules.eligible(q, driver)
        value = rules.value_of(q, driver)
        if ok and value is not None:
            values.append(value)
        rows.append(
            {
                "quarter": q.label,
                "start": q.start.isoformat(),
                "end": q.end.isoformat(),
                "value": None if value is None else _fmt(driver, value),
                "created": q.created,
                "wins": q.wins,
                "exposure": number(q.exposure, 2) if driver == PRODUCTIVITY else None,
                "mature": q.mature,
                "eligible": ok,
                "not_eligible_because": why,
            }
        )
    return rows, values


def _change_at(c: Context, driver: str, setting: Decimal) -> dict[str, str]:
    f = c.probe.forecast(wd.with_setting(c.g, driver, setting))
    return _per_window(c.probe.change(f))


def _needed(c: Context, driver: str, current: Decimal | None, observed) -> dict | None:
    """What alone closes the gap. The classification is by exact bookings against the exact
    target; the figures written are to the cent (money) and to the driver's places (settings),
    with a setting rounded up so that entering it reaches the target."""
    g, probe = c.g, c.probe
    if current is None:
        return None
    base_fy = probe.fiscal_year(probe.base)

    def fy_for(adjusted: Ground) -> Decimal:
        return probe.fiscal_year(probe.forecast(adjusted))

    if driver == CYCLE_DAYS:
        samples = g.model.new_pipeline.timing.samples

        def at_scale(s: Fraction) -> Decimal:
            return base_fy if s == 1 else fy_for(wd.with_cycle_scale(g, s))

        r = wd.solve_cycle(at_scale, samples, c.fy_target)
        value = current if r.outcome == wd.COVERED else wd.realized_cycle(g, r.scale)
        scale = (
            None
            if r.outcome == wd.COVERED
            else f"{r.scale.numerator}/{r.scale.denominator}"
        )
    else:

        def at_value(v: Decimal) -> Decimal:
            return base_fy if v == current else fy_for(wd.with_setting(g, driver, v))

        upper = Decimal(1) if driver == WIN_RATE else None
        r = wd.solve_linear(at_value, current, c.fy_target, upper)
        r = wd.round_solution(at_value, r, driver, c.fy_target, upper)
        value, scale = r.value, None
    label = (
        STEPPED_LABEL
        if driver == CYCLE_DAYS and r.outcome == wd.SOLVES
        else OUTCOME_LABELS[r.outcome]
    )
    inside = None
    if observed is not None and value is not None and r.outcome == wd.SOLVES:
        inside = observed.minimum <= value <= observed.maximum
    target_shown, achieved_shown = money(c.fy_target), money(r.achieved)
    return {
        "outcome": r.outcome,
        "outcome_label": label,
        "reaches_target": r.outcome != wd.CANNOT,
        "reason": r.reason,
        "reason_label": REASON_LABELS.get(r.reason) if r.reason else None,
        "value": None if value is None else _fmt(driver, value),
        "achieved_fiscal_year_bookings": achieved_shown,
        "target": target_shown,
        "overshoot": None if r.overshoot is None else money(r.overshoot),
        "precision_note": SUB_CENT_NOTE
        if r.outcome == wd.CANNOT and achieved_shown == target_shown
        else None,
        "stepped": driver == CYCLE_DAYS,
        "scale": scale,
        "inside_observed_range": inside,
        "history_label": (
            None
            if r.outcome != wd.SOLVES
            else NO_HISTORY_LABEL
            if inside is None
            else INSIDE_LABEL
            if inside
            else BEYOND_LABEL
        ),
    }


def driver_row(c: Context, driver: str) -> dict:
    current = wd.current_value(c.g, driver)
    unit, unit_label, display, applies = unit_for(c.g.cap.adopted, driver)
    rows, values = _observations(c, driver)
    settings = rules.historical_settings(values)
    gate_passed = settings is not None
    fit_from, fit_to = fit_window(driver, c.params, c.g.as_of)
    cannot_scale = None
    if driver == CYCLE_DAYS and not current:
        cannot_scale = NO_WIN_TIMES if current is None else ZERO_CYCLE
    if cannot_scale is not None:
        historical, why = None, cannot_scale
    elif settings is None:
        historical, why = None, GATE_FAILED
    else:
        historical, why = (
            {
                "low": _setting(c, driver, settings.low),
                "high": _setting(c, driver, settings.high),
                "minimum": _fmt(driver, settings.minimum),
                "maximum": _fmt(driver, settings.maximum),
                "rule": SETTINGS_RULE,
            },
            None,
        )
    return {
        "driver": driver,
        "label": LABELS[driver],
        "applies_to": applies,
        "unit": unit,
        "unit_label": unit_label,
        "display": display,
        "places": rules.PRECISION[driver],
        "cannot_scale_because": cannot_scale,
        "current": {
            "value": None if current is None else _fmt(driver, current),
            "fit_in_use": c.params.estimator,
            "creation_from": fit_from.isoformat(),
            "creation_to": fit_to.isoformat(),
        },
        "evidence": {
            "gate": GATE_WORDS[driver],
            "required_quarters": rules.REQUIRED_QUARTERS,
            "eligible_quarters": len(values),
            "gate_passed": gate_passed,
            "quarters": rows,
        },
        "historical": historical,
        "historical_unavailable_because": why,
        "needed_alone": _needed(c, driver, current, settings),
        "limitation": _limitation(c, driver, gate_passed),
    }


def _setting(c: Context, driver: str, setting: Decimal) -> dict:
    return {"setting": _fmt(driver, setting), "change": _change_at(c, driver, setting)}


def rank_by_window(
    magnitudes: list[dict[str, Decimal] | None],
) -> list[dict[str, int | None]]:
    """For each window, 1 for the largest absolute change in that window within the group, ties
    in the listed order; None where there is no change to rank. The browser never sorts."""
    ranks: list[dict[str, int | None]] = [{} for _ in magnitudes]
    for w in WINDOWS:
        order = sorted(
            (i for i, m in enumerate(magnitudes) if m is not None),
            key=lambda i: (-abs(magnitudes[i][w]), i),
        )
        position = {i: k for k, i in enumerate(order, start=1)}
        for i in range(len(magnitudes)):
            ranks[i][w] = position.get(i)
    return ranks


def _driver_magnitudes(row: dict) -> dict[str, Decimal] | None:
    h = row["historical"]
    if h is None:
        return None
    return {
        w: max(
            abs(Decimal(h["low"]["change"][w])), abs(Decimal(h["high"]["change"][w]))
        )
        for w in WINDOWS
    }


def _action_magnitudes(row: dict) -> dict[str, Decimal] | None:
    gained = row["bookings_gained"]["value"]
    return None if gained is None else {w: abs(Decimal(gained[w])) for w in WINDOWS}


# ------------------------------------------------------------------ restated and referenced


def _action_rows(actions_section: dict) -> dict:
    """The two unit actions and what closes the gap alone, restated from ``actions``."""
    close = actions_section["close_the_fiscal_year_gap"]
    rows = []
    for i, row in enumerate(actions_section["comparison"]):
        closing = close["hires" if row["kind"] == "hire" else "program"]
        rows.append(
            {
                "kind": row["kind"],
                "action": _ref(row["action"], f"/actions/comparison/{i}/action"),
                "status": _ref(row["status"], f"/actions/comparison/{i}/status"),
                "bookings_gained": _ref(
                    row["bookings_gained"], f"/actions/comparison/{i}/bookings_gained"
                ),
                "closes_alone_outcome": _ref(
                    closing["outcome"],
                    f"/actions/close_the_fiscal_year_gap/{'hires' if row['kind'] == 'hire' else 'program'}/outcome",
                ),
                "closes_alone_label": _closes_alone_label(
                    row["kind"], closing["outcome"]
                ),
            }
        )
    for row, rank in zip(rows, rank_by_window([_action_magnitudes(r) for r in rows])):
        row["rank"] = rank
    return {"basis": "as signed", "note": ACTIONS_NOTE, "rows": rows}


def _closes_alone_label(kind: str, outcome: str) -> str:
    unit = "hires" if kind == "hire" else "program pipeline"
    return {
        "already covered": "The gap is already covered, so none is needed.",
        "feasible": f"Closes the gap alone with the {unit} shown in the actions section, inside its bound.",
        "unreachable": f"Cannot close the gap alone within the bound on {unit}.",
    }.get(outcome, "Not valued by this history, so there is nothing to solve for.")


def _bridge(plan_section: dict | None, gap: dict) -> tuple[dict, list[Check]]:
    year = gap["fiscal_year"]
    signed = Decimal(year["expected"])
    steps = [
        {
            "kind": "as_signed",
            "label": "As signed",
            "change": None,
            "from": None,
            "to": year["expected"],
            "valued": True,
            "note": None,
            "source": "/gap/fiscal_year/expected",
        }
    ]
    contributions = []
    running = signed
    if plan_section is not None:
        for i, item in enumerate(plan_section["items"]):
            c = item["contribution"]
            change = Decimal(c[REST_OF_FY]) if c else ZERO
            steps.append(
                {
                    "kind": item["kind"],
                    "label": item["label"],
                    "change": money(change),
                    "from": money(running),
                    "to": money(running + change),
                    "valued": c is not None,
                    "note": item.get("note"),
                    "source": f"/plan/items/{i}/contribution/{REST_OF_FY}",
                }
            )
            contributions.append(
                {
                    "label": item["label"],
                    "kind": item["kind"],
                    "valued": c is not None,
                    REST_OF_FY: None if c is None else c[REST_OF_FY],
                    NEXT_12: None if c is None else c[NEXT_12],
                }
            )
            running += change
        working, working_source = (
            plan_section["expected_fiscal_year"],
            "/plan/expected_fiscal_year",
        )
        remaining = plan_section["gap"]["fiscal_year"]["gap_with_plan"]
        remaining_source = "/plan/gap/fiscal_year/gap_with_plan"
    else:
        working, working_source = year["expected"], "/gap/fiscal_year/expected"
        remaining, remaining_source = year["gap"], "/gap/fiscal_year/gap"
    steps.append(
        {
            "kind": "working_plan",
            "label": "Working plan",
            "change": None,
            "from": None,
            "to": working,
            "valued": True,
            "note": None,
            "source": working_source,
        }
    )
    steps.append(
        {
            "kind": "remaining_gap",
            "label": "Remaining gap to target",
            "change": None,
            "from": None,
            "to": remaining,
            "valued": True,
            "note": None,
            "source": remaining_source,
        }
    )
    sums = cents(running) == Decimal(working)
    closes = (
        abs(Decimal(str(year["target"])) - Decimal(working) - Decimal(remaining))
        <= CENT
    )
    bridge = {
        "order": BRIDGE_ORDER_NOTE,
        "measure": "fiscal-year bookings expected",
        "target": _ref(year["target"], "/gap/fiscal_year/target"),
        "steps": steps,
        "contributions": contributions,
    }
    checks = [
        Check(
            "worksheet bridge steps sum to the working plan",
            sums,
            f"{money(signed)} plus the contributions is {money(running)}; the working plan is {working}",
        ),
        Check(
            "worksheet working plan and remaining gap close on the target",
            closes,
            f"target {year['target']} less {working} is {remaining}",
        ),
    ]
    return bridge, checks


def _summary(plan_section: dict | None, gap: dict) -> dict:
    year = gap["fiscal_year"]
    summary = {
        "fiscal_year_target": _ref(year["target"], "/gap/fiscal_year/target"),
        "as_signed": _ref(year["expected"], "/gap/fiscal_year/expected"),
    }
    if plan_section is None:
        summary |= {
            "working_plan": _ref(year["expected"], "/gap/fiscal_year/expected"),
            "remaining_gap": _ref(year["gap"], "/gap/fiscal_year/gap"),
            "twelve_month_gain": None,
            "cash_cost_in_twelve_months": None,
            "no_plan_note": "No plan is in force, so the working plan is the as-signed forecast and there is no gain or cost to show.",
        }
        return summary
    summary |= {
        "working_plan": _ref(
            plan_section["expected_fiscal_year"], "/plan/expected_fiscal_year"
        ),
        "remaining_gap": _ref(
            plan_section["gap"]["fiscal_year"]["gap_with_plan"],
            "/plan/gap/fiscal_year/gap_with_plan",
        ),
        "twelve_month_gain": _ref(
            plan_section["difference"][NEXT_12], f"/plan/difference/{NEXT_12}"
        ),
        "cash_cost_in_twelve_months": _ref(
            plan_section["cash_cost_in_twelve_months"],
            "/plan/cash_cost_in_twelve_months",
        ),
        "no_plan_note": None,
    }
    return summary


def _chain(gap: dict, required: dict) -> dict:
    base = {"basis": "as signed", "note": CHAIN_NOTE}
    if "unavailable" in required:
        return base | {"unavailable": required["unavailable"], "quarters": []}
    gap_index = {q["quarter"]: i for i, q in enumerate(gap["quarters"])}
    quarters = []
    for j, q in enumerate(required["quarters"]):
        if q["status"] == "closed":
            continue
        i = gap_index[q["quarter"]]
        r, gq = f"/required_pipeline/quarters/{j}", f"/gap/quarters/{i}"
        gapq = gap["quarters"][i]
        quarters.append(
            {
                "quarter": q["quarter"],
                "status": _ref(q["status"], f"{r}/status"),
                "bookings": {
                    "target": _ref(gapq["target"], f"{gq}/target"),
                    "expected": _ref(gapq["expected"], f"{gq}/expected"),
                    "gap": _ref(gapq["gap"], f"{gq}/gap"),
                },
                "created_pipeline": {
                    "required": _ref(
                        q["total_created_in_span"], f"{r}/total_created_in_span"
                    ),
                    "required_note": _ref(
                        q["total_created_note"], f"{r}/total_created_note"
                    ),
                    "expected": _ref(
                        q["expected_created_pipeline"], f"{r}/expected_created_pipeline"
                    ),
                    "created_between": _ref(
                        q["created_between"], f"{r}/created_between"
                    ),
                    "outcome": _ref(q["outcome"], f"{r}/outcome"),
                    "headline": _ref(q["headline"], f"{r}/headline"),
                },
                "per_ramped_ae_month": {
                    "required": _ref(
                        q["per_ramped_ae_month"]["required_total"],
                        f"{r}/per_ramped_ae_month/required_total",
                    ),
                    "expected": _ref(
                        q["per_ramped_ae_month"]["expected"],
                        f"{r}/per_ramped_ae_month/expected",
                    ),
                    "decides": _ref(
                        q["per_ramped_ae_month"]["decides"],
                        f"{r}/per_ramped_ae_month/decides",
                    ),
                    "note": _ref(
                        q["per_ramped_ae_month"]["note"],
                        f"{r}/per_ramped_ae_month/note",
                    ),
                },
                "timing": {
                    "applies": _ref(q["too_late"]["applies"], f"{r}/too_late/applies"),
                    "label": _ref(q["too_late"]["label"], f"{r}/too_late/label"),
                    "reasons": _ref(q["too_late"]["reasons"], f"{r}/too_late/reasons"),
                },
            }
        )
    return base | {"unavailable": None, "quarters": quarters}


# ------------------------------------------------------------------ the section


def company_quarters(g: Ground) -> tuple[Quarter, ...]:
    """The company's past by fiscal creation quarter. It depends on the files and the as-of
    date alone, so ``prepare`` computes it once for every plan."""
    if g.cap.adopted:

        def exposure(start: date, end: date) -> Decimal:
            return ramped_ae_months(
                g.cap.members, g.cap.fit.curve, start - timedelta(days=1), end
            )
    else:

        def exposure(start: date, end: date) -> Decimal:
            return Decimal((end - start).days + 1)

    return tuple(
        observe(g.pop.deals, g.as_of, g.fy_start, g.model.params.horizon_days, exposure)
    )


def static_texts(plan_in_force: bool, with_actions: bool = False) -> dict:
    """The section's fixed sentences and flags, which depend only on whether a plan is in force
    and whether it carries driver actions."""
    return {
        "definition": (
            "What moves the outcome: four operating drivers, each changed alone for deals "
            "created after the as-of date, measured around the plan in force."
        ),
        "plan_in_force": plan_in_force,
        "measured_around": (
            "the plan in force: its hires, program pipeline and driver actions, as applied"
            if with_actions
            else "the plan in force: its hires and program pipeline, as applied"
            if plan_in_force
            else "the roster as signed and nothing planned"
        ),
        "windows": list(WINDOWS),
        "expectation_note": EXPECTATION_NOTE,
        "sensitivity_note": SENSITIVITY_NOTE,
        "history_note": rules.HISTORY_PROMISES_NOTHING,
    }


def worksheet_section(
    g: Ground,
    quarters: Sequence[Quarter],
    params: FitParams,
    plan_section: dict | None,
    hires: Sequence[Member],
    inflows: Sequence[Inflow],
    actions_section: dict,
    gap: dict,
    required: dict,
    lift: Lift | None = None,
) -> tuple[dict, list[Check]]:
    probe = wd.Probe(g, hires, inflows, lift)
    c = Context(g, probe, quarters, params, g.fy_target)
    drivers = [driver_row(c, d) for d in DRIVERS]
    for row, rank in zip(
        drivers, rank_by_window([_driver_magnitudes(r) for r in drivers])
    ):
        row["rank"] = rank
    bridge, checks = _bridge(plan_section, gap)
    expected_in_force = money(g.fytd + probe.shown(probe.base)[REST_OF_FY])
    reference = (
        plan_section["expected_fiscal_year"]
        if plan_section is not None
        else gap["fiscal_year"]["expected"]
    )
    checks.append(
        Check(
            "worksheet baseline is the report's own expected fiscal year",
            expected_in_force == reference,
            f"the probe's baseline {expected_in_force} against the report's {reference}",
        )
    )
    for row in drivers:
        n = row["needed_alone"]
        if n is None:
            continue
        reached, target = (
            Decimal(n["achieved_fiscal_year_bookings"]),
            Decimal(n["target"]),
        )
        if n["outcome"] == wd.SOLVES:
            ok = (
                reached >= target
                and abs(Decimal(n["overshoot"]) - (reached - target)) <= CENT
            )
        elif n["outcome"] == wd.COVERED:
            ok = reached >= target
        else:
            ok = reached <= target
        checks.append(
            Check(
                f"worksheet {row['driver']} needed alone agrees with the target",
                ok,
                f"{n['outcome']}: {reached} against {target}",
            )
        )
    section = {
        **static_texts(
            plan_section is not None,
            plan_section is not None
            and any(i["kind"] == "actions" for i in plan_section["items"]),
        ),
        "drivers": drivers,
        "actions": _action_rows(actions_section),
        "bridge": bridge,
        "summary": _summary(plan_section, gap),
        "chain": _chain(gap, required),
        "checks": [
            {"name": k.name, "passed": k.passed, "detail": k.detail} for k in checks
        ],
    }
    return section, checks
