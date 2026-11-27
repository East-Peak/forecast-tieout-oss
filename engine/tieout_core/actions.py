"""Sections 11 and 12: the plan, and two actions compared.

Everything goes through the one forward function (``Scenario.forecast``). When
the capacity term was adopted a hire raises the roster's ramped AE-months;
when it was not, a hire is "unsupported by this history" and not valued, and
only programme pipeline (which enters through created pipeline, as the lever
does) is. A missing cost is "cost not entered" and the action is not ranked.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .adoption import NOT_SHOWN
from .capacity import daily_survival, project
from .capacity_report import Capacity
from .figures import CENT, cents, money, number
from .fiscal import Window, add_months
from .fit import Model
from .forecast import Forecast, Inflow, model_forecast, simulate
from .lever import COVERED, FEASIBLE, UNREACHABLE, solve_added_pipeline
from .plan import (
    DEFAULT_PROGRAMME_RAMP_MONTHS,
    NEXT_12,
    REST_OF_FY,
    Plan,
    PlanHire,
    PlanProgramme,
    next_month_start,
    programme_cost,
    programme_cost_in_window,
    programme_inflows,
    segment_words,
)
from .records import Check, Dataset
from .roster import Member

ZERO = Decimal(0)
FEASIBLE_HIRES = "feasible"
ACTION_PROGRAMME_DOLLARS = Decimal(1_000_000)
UNSUPPORTED = "unsupported by this history"
PAYING_SHARE = Decimal(
    "0.01"
)  # an action "starts paying" in the first month it adds this share of its year's gain


@dataclass(frozen=True)
class Ground:
    """What the plan and the actions read from the rest of the report."""

    cap: Capacity
    model: Model
    pop: Dataset
    as_of: date
    windows: list[Window]
    rest_labels: list[str]
    twelve_labels: list[str]
    targeted_labels: list[str]  # twelve-month months that meet a target
    fytd: Decimal
    fy_target: Decimal
    fy_start: date
    fy_end: date
    goal12: Decimal | None  # targets of the quarters ending in the window
    actual12: Decimal
    lever_cap: Decimal
    horizon_days: int
    draws: int = 2000
    seed: int = 0
    # (quarter, status, target, booked, month labels) for each quarter with a target
    quarters: tuple = ()


class Scenario:
    """The forward function, with people and pipeline added to it."""

    def __init__(self, g: Ground) -> None:
        self.g = g

    def creation(self, hires: Sequence[Member] = ()):
        g = self.g
        if not g.cap.adopted:
            return None
        return project(g.cap.fit, [*g.cap.members, *hires], g.as_of, g.horizon_days)

    def forecast(
        self, hires: Sequence[Member] = (), inflows: Sequence[Inflow] = ()
    ) -> Forecast:
        g = self.g
        creation = self.creation(hires)
        return model_forecast(
            g.model,
            g.pop,
            g.as_of,
            g.windows,
            creation=creation,
            inflows=tuple(inflows),
        )

    def shown(self, f: Forecast, labels: list[str]) -> Decimal:
        """A displayed total: the sum of the months each to the cent."""
        return sum((cents(f.window_total(m)) for m in labels), ZERO)

    def exact(self, f: Forecast, labels: list[str]) -> Decimal:
        return sum((f.window_total(m) for m in labels), ZERO)

    def bookings(self, f: Forecast) -> dict[str, Decimal]:
        return {
            REST_OF_FY: self.shown(f, self.g.rest_labels),
            NEXT_12: self.shown(f, self.g.twelve_labels),
        }

    def fiscal_year(self, f: Forecast) -> Decimal:
        """Fiscal-year bookings expected: to date plus the rest of the year."""
        return self.g.fytd + self.exact(f, self.g.rest_labels)


# ---------------------------------------------------------------- helpers


def employed_months(
    start: date, windows: list[Window], as_of: date, survival: Decimal
) -> Decimal:
    """Expected months of cost for a person starting on ``start``: each month
    window counts the days employed over the days in that calendar month, each
    day weighted by the chance of still being there (1 on the first day)."""
    total = ZERO
    for w in windows:
        lo, hi = max(w.start + timedelta(days=1), start), w.end
        if lo > hi:
            continue
        alive = sum(
            (
                survival ** (d - start.toordinal())
                for d in range(lo.toordinal(), hi.toordinal() + 1)
            ),
            ZERO,
        )
        total += alive / Decimal(_days_in_month(w.end))
    return total


def _days_in_month(d: date) -> int:
    return (add_months(date(d.year, d.month, 1), 1) - date(d.year, d.month, 1)).days


def closing_cost_note(kind: str, outcome: str, cost_status: str, cost) -> str | None:
    """Why a closing action shows no cost, from its own outcome and cost status; None when there is a cost."""
    if cost is not None:
        return None
    if cost_status != "entered":
        return "cost not entered"
    if outcome == "already covered":
        return "no cost: the gap is already covered, so nothing needs adding"
    if outcome == "unreachable":
        what = "number of hires" if kind == "hires" else "amount of pipeline"
        where = "within the bound" if kind == "hires" else "within the cap"
        return f"no cost: no {what} closes the gap {where}"
    return "no cost to show"


def hires_bound(members, fy_start: date, as_of: date, entered: int | None):
    """The most whole hires the solve will try, and why."""
    if entered is not None:
        return entered, "entered in capacity.yaml"
    per_quarter: dict[int, int] = {}
    for m in members:
        if m.start <= as_of:
            k = (
                (m.start.year - fy_start.year) * 12 + m.start.month - fy_start.month
            ) // 3
            per_quarter[k] = per_quarter.get(k, 0) + 1
    return max(
        per_quarter.values(), default=0
    ), "the most the company has started in one fiscal quarter"


@dataclass(frozen=True)
class HiresSolve:
    outcome: str  # "already covered", FEASIBLE_HIRES or "unreachable"
    count: int | None
    overshoot: Decimal | None
    forecast_with: Decimal
    forecast_one_fewer: Decimal | None
    bound: int


def solve_hires(
    expected: Callable[[int], Decimal], target: Decimal, bound: int
) -> HiresSolve:
    """The smallest whole number of hires whose fiscal-year bookings reach the
    target, trying 0 up to ``bound``."""
    base = expected(0)
    if base >= target:
        return HiresSolve("already covered", 0, ZERO, base, None, bound)
    previous = base
    for n in range(1, bound + 1):
        got = expected(n)
        if got >= target:
            return HiresSolve(FEASIBLE_HIRES, n, got - target, got, previous, bound)
        previous = got
    return HiresSolve("unreachable", None, None, previous, None, bound)


def first_paying_month(gains: list[tuple[str, Decimal]]) -> str | None:
    """The first month whose gain is at least PAYING_SHARE of the total gain."""
    total = sum((g for _, g in gains), ZERO)
    if total <= 0:
        return None
    return next((m for m, g in gains if g >= PAYING_SHARE * total), None)


def rank(rows: list[dict]) -> list[dict]:
    """Rows with a gain per dollar, best first, then the rest unranked."""
    valued = sorted(
        (r for r in rows if r["gain_per_dollar"] is not None),
        key=lambda r: r["gain_per_dollar"],
        reverse=True,
    )
    out = [{**r, "rank": i} for i, r in enumerate(valued, start=1)]
    return out + [{**r, "rank": None} for r in rows if r["gain_per_dollar"] is None]


# ---------------------------------------------------------------- section 11


def plan_section(
    g: Ground, scen: Scenario, plan: Plan, path: Path
) -> tuple[dict, list[Check]]:
    cfg = g.cap.cfg
    adopted = g.cap.adopted
    base = scen.forecast()
    prev = scen.bookings(base)
    baseline = dict(prev)
    base_targeted = scen.shown(base, g.targeted_labels)
    hires: list[Member] = []
    inflows: list[Inflow] = []
    items, total_cost, cost_missing = [], ZERO, False
    survival = daily_survival(g.cap.fit.attrition.rate) if g.cap.fit else Decimal(1)
    ramp_default = (
        cfg.programme_ramp_months if cfg else None
    ) or DEFAULT_PROGRAMME_RAMP_MONTHS
    for index, item in enumerate(plan.items()):
        total = None
        if isinstance(item, PlanHire):
            people = plan.members_for(index)
            cost = (
                None
                if cfg is None or cfg.loaded_cost_per_ae_month is None
                else cfg.loaded_cost_per_ae_month
                * employed_months(item.start, g.windows, g.as_of, survival)
                * item.count
            )
            total = cost
            row = {
                "kind": "hires",
                "label": item.label,
                "detail": f"{item.count} AE(s), segment {segment_words(item.segment)}, starting {item.start}",
            }
            if adopted:
                hires.extend(people)
            else:
                row |= {"valued": False, "note": f"hiring is {UNSUPPORTED}: not valued"}
        else:
            flows = programme_inflows(item, g.windows, g.as_of, g.fy_end, ramp_default)
            per_dollar = cfg.programme_cost_per_dollar if cfg else None
            cost = programme_cost_in_window(item, per_dollar, flows, g.windows[-1].end)
            total = programme_cost(item, per_dollar)
            inflows.extend(flows)
            row = {
                "kind": "programme",
                "label": item.label,
                "detail": f"${item.pipeline:,.0f} of created pipeline from {item.start:%Y-%m}",
            }
        if row.get("valued", True):
            f = scen.forecast(tuple(hires), tuple(inflows))
            now = scen.bookings(f)
            row |= {
                "valued": True,
                "contribution": {h: money(now[h] - prev[h]) for h in now},
            }
            prev = now
        else:
            row["contribution"] = None
        row["cash_cost_in_twelve_months"] = None if cost is None else money(cost)
        row["cash_cost_total"] = None if total is None else money(total)
        if row["kind"] == "programme":
            row["payment_schedule"] = (
                "the plan's payments"
                if item.payments is not None
                else "paid in step with the pipeline it creates"
            )
        if cost is None:
            cost_missing = True
        else:
            total_cost += cost
        items.append(row)
    final = scen.forecast(tuple(hires), tuple(inflows))
    with_plan = scen.bookings(final)
    diff = {h: with_plan[h] - baseline[h] for h in baseline}
    summed = {
        h: sum(
            (Decimal(r["contribution"][h]) for r in items if r["contribution"]), ZERO
        )
        for h in baseline
    }

    def fy_gap(total):
        return g.fy_target - g.fytd - total

    quarter_labels = {q: list(labels) for q, _, _, _, labels in g.quarters}
    sim = simulate(
        g.model, g.pop, g.as_of, g.windows, draws=g.draws, seed=g.seed,
        groups={**quarter_labels, REST_OF_FY: g.rest_labels, NEXT_12: g.twelve_labels},
        creation=scen.creation(tuple(hires)), inflows=tuple(inflows),
    )  # fmt: skip
    expected_total = float(final.total())
    sd_mean = (
        sum((x - sim.total.mean) ** 2 for x in sim.samples_total)
        / max(1, sim.draws - 1)
    ) ** 0.5 / sim.draws**0.5
    centred = abs(sim.total.mean - expected_total) <= 4 * sd_mean + 0.01
    section = {
        "file": str(path),
        "order": "hires first, then programmes, each in the plan file's order; each contribution is "
        "the extra bookings from adding that item to everything above it, so they sum to the difference",
        "baseline_definition": "the roster as signed and nothing planned"
        + (
            ""
            if adopted
            else "; the capacity term was not adopted, so hires are listed but not valued"
        ),
        "items": items,
        "baseline": {h: money(v) for h, v in baseline.items()},
        "with_plan": {h: money(v) for h, v in with_plan.items()},
        "difference": {h: money(v) for h, v in diff.items()},
        "contributions_total": {h: money(v) for h, v in summed.items()},
        "gap": {
            "fiscal_year": {
                "target": g.fy_target and str(g.fy_target),
                "actual_to_date": str(g.fytd),
                "baseline_gap": money(fy_gap(baseline[REST_OF_FY])),
                "gap_with_plan": money(fy_gap(with_plan[REST_OF_FY])),
            },
            "next_twelve_months": None
            if g.goal12 is None
            else {
                "target": str(g.goal12),
                "actual_to_date": str(g.actual12),
                "baseline_gap": money(g.goal12 - g.actual12 - base_targeted),
                "gap_with_plan": money(
                    g.goal12 - g.actual12 - scen.shown(final, g.targeted_labels)
                ),
                "note": "against the quarters with a target that end in the window; later months are bookings alone",
            },
        },
        "cash_cost_in_twelve_months": None if cost_missing else money(total_cost),
        "cost_note": "a missing cost is shown as 'cost not entered' and left out of the total"
        if cost_missing
        else "hires at loaded cost per AE-month over expected months employed; programmes at their cost, "
        "paid in step with the pipeline they create (or on the plan's own payment schedule), counting "
        "only what falls inside the twelve months",
        "ranges": {
            "status": "unvalidated: these ranges include the plan"
            + (" and the capacity term" if adopted else "")
            + "; they have not been back-tested",
            "bookings_in_window": {
                h: {
                    "median": f"{spread.p50:.2f}",
                    "range80": [f"{spread.p10:.2f}", f"{spread.p90:.2f}"],
                    "range95": [f"{spread.p2_5:.2f}", f"{spread.p97_5:.2f}"],
                }
                for h, spread in sim.by_group.items()
                if h in (REST_OF_FY, NEXT_12)
            },
            "fiscal_year_expected_range80": [
                f"{float(g.fytd) + sim.by_group[REST_OF_FY].p10:.2f}",
                f"{float(g.fytd) + sim.by_group[REST_OF_FY].p90:.2f}",
            ],
            "draws": g.draws,
            "what_is_drawn": "deal outcomes"
            + (", future departures" if adopted else "")
            + ", with the planned hires and programme pipeline in the scenario",
        },
    }
    # Goal 3A: the with-plan figures a screen shows, by month, by quarter and for the year
    section["with_plan_by_window"] = {
        w.label: money(final.window_total(w.label)) for w in g.windows
    }
    section["expected_fiscal_year"] = money(g.fytd + with_plan[REST_OF_FY])
    section["with_plan_quarters"] = [
        _plan_quarter(final, scen, sim, q, status, target, booked, labels)
        for q, status, target, booked, labels in g.quarters
    ]
    section["ranges"]["by_window"] = {
        label: _spread(s) for label, s in sim.by_window.items()
    }
    section["ranges"]["fiscal_year_expected_range95"] = [
        f"{float(g.fytd) + sim.by_group[REST_OF_FY].p2_5:.2f}",
        f"{float(g.fytd) + sim.by_group[REST_OF_FY].p97_5:.2f}",
    ]
    if section["gap"]["next_twelve_months"] is not None:
        section["gap"]["next_twelve_months"]["forecast_with_plan"] = money(
            scen.shown(final, g.targeted_labels)
        )
    check = Check(
        "plan contributions sum to the difference",
        summed == diff,
        "; ".join(
            f"{h}: {money(summed[h])} = {money(with_plan[h])} - {money(baseline[h])}"
            for h in diff
        ),
    )
    sim_check = Check(
        "plan simulation centred on its expectation",
        centred,
        f"simulated mean {sim.total.mean:,.2f} vs expected {expected_total:,.2f} ({g.draws} draws)",
    )
    return section, [check, sim_check]


def _spread(s) -> dict:
    return {
        "mean": f"{s.mean:.2f}",
        "median": f"{s.p50:.2f}",
        "range80": [f"{s.p10:.2f}", f"{s.p90:.2f}"],
        "range95": [f"{s.p2_5:.2f}", f"{s.p97_5:.2f}"],
    }


def _plan_quarter(final, scen, sim, quarter, status, target, booked, labels) -> dict:
    """One quarter with the plan: the same arithmetic as the gap table's rows."""
    forecast = scen.shown(final, list(labels))
    spread = sim.by_group[quarter]
    return {
        "quarter": quarter,
        "status": status,
        "target": str(target),
        "actual": str(booked),
        "forecast": money(forecast),
        "expected": money(booked + cents(forecast)),
        "gap": money(target - booked - cents(forecast)),
        "expected_range80": [
            f"{float(booked) + spread.p10:.2f}",
            f"{float(booked) + spread.p90:.2f}",
        ],
    }


# ---------------------------------------------------------------- section 12


def actions_section(g: Ground, scen: Scenario) -> tuple[dict, list[Check]]:
    cfg, cap = g.cap.cfg, g.cap
    start = next_month_start(g.as_of)
    base = scen.forecast()
    base_book = scen.bookings(base)
    survival = daily_survival(cap.fit.attrition.rate) if cap.fit else Decimal(1)
    ramp_default = (
        cfg.programme_ramp_months if cfg else None
    ) or DEFAULT_PROGRAMME_RAMP_MONTHS
    hire = Member("ACTION-HIRE", "ae", "", start, None, None)
    programme = PlanProgramme("programme pipeline", ACTION_PROGRAMME_DOLLARS, start)

    def row(action, kind, forecast, cost, unsupported=""):
        out = {"action": action, "kind": kind, "not_ranked_because": None}
        if unsupported:
            return out | {
                "status": unsupported, "bookings_gained": None, "starts_paying": None,
                "cash_cost_in_twelve_months": None, "gain_per_dollar": None,
                "not_ranked_because": unsupported,
            }  # fmt: skip
        now = scen.bookings(forecast)
        gained = {h: now[h] - base_book[h] for h in now}
        paying = first_paying_month(
            [
                (w.label, forecast.window_total(w.label) - base.window_total(w.label))
                for w in g.windows
            ]
        )
        gpd = None if cost is None or not cost else gained[NEXT_12] / cost
        out |= {
            "status": "valued",
            "bookings_gained": {h: money(v) for h, v in gained.items()},
            "starts_paying": paying,
            "cash_cost_in_twelve_months": None if cost is None else money(cost),
            "cost_status": "entered" if cost is not None else "cost not entered",
            "gain_per_dollar": gpd,
        }
        if cost is None:
            out["not_ranked_because"] = "cost not entered"
        return out

    # --- hire one AE
    if cap.adopted:
        hire_cost = (
            None
            if cfg.loaded_cost_per_ae_month is None
            else cfg.loaded_cost_per_ae_month
            * employed_months(start, g.windows, g.as_of, survival)
        )
        hire_row = row(
            f"Hire one AE starting {start}", "hire", scen.forecast((hire,)), hire_cost
        )
    else:
        why = (
            UNSUPPORTED
            if cap.adoption.outcome == NOT_SHOWN
            else f"unavailable: {cap.adoption.reason}"
        )
        hire_row = row(
            f"Hire one AE starting {start}", "hire", None, None, unsupported=why
        )
    # --- one million dollars of programme pipeline
    flows = programme_inflows(programme, g.windows, g.as_of, g.fy_end, ramp_default)
    prog_cost = programme_cost_in_window(
        programme,
        cfg.programme_cost_per_dollar if cfg else None,
        flows,
        g.windows[-1].end,
    )
    prog_row = row(
        f"Add ${ACTION_PROGRAMME_DOLLARS:,.0f} of programme pipeline starting {start}",
        "programme", scen.forecast(inflows=flows), prog_cost,
    )  # fmt: skip
    ranked = rank([hire_row, prog_row])
    for r in ranked:  # numbers for the report dict
        gpd = r["gain_per_dollar"]
        r["gain_per_dollar"] = None if gpd is None else number(gpd, 2)

    # --- what closes the fiscal-year gap alone
    gap = g.fy_target - scen.fiscal_year(base)
    closing: dict = {
        "fiscal_year_gap": money(gap),
        "basis": "the baseline forecast (the roster as signed, nothing planned), each action alone",
    }
    checks: list[Check] = []
    # hires
    if cap.adopted:
        bound, basis = hires_bound(cap.members, g.fy_start, g.as_of, cfg.hires_bound)

        def with_n(n: int) -> Decimal:
            people = tuple(
                Member(f"ACTION-HIRE-{i}", "ae", "", start, None, None)
                for i in range(n)
            )
            return scen.fiscal_year(scen.forecast(people))

        solved = solve_hires(with_n, g.fy_target, bound)
        per_hire = (
            None
            if cfg.loaded_cost_per_ae_month is None
            else cfg.loaded_cost_per_ae_month
            * employed_months(start, g.windows, g.as_of, survival)
        )
        closing["hires"] = {
            "outcome": solved.outcome,
            "count": solved.count,
            "overshoot": None if solved.overshoot is None else money(solved.overshoot),
            "fiscal_year_bookings_with": money(solved.forecast_with),
            "fiscal_year_bookings_one_fewer": None
            if solved.forecast_one_fewer is None
            else money(solved.forecast_one_fewer),
            "bound": bound,
            "bound_basis": basis,
            "cash_cost_in_twelve_months": None
            if per_hire is None or not solved.count
            else money(per_hire * solved.count),
            "cost_status": "entered" if per_hire is not None else "cost not entered",
        }
        closing["hires"]["cash_cost_note"] = closing_cost_note(
            "hires",
            solved.outcome,
            closing["hires"]["cost_status"],
            closing["hires"]["cash_cost_in_twelve_months"],
        )
        smallest = solved.outcome != FEASIBLE_HIRES or (
            solved.forecast_with >= g.fy_target
            and (solved.forecast_one_fewer or ZERO) < g.fy_target
        )
        checks.append(
            Check(
                "hires solve returns the smallest whole number that closes the gap",
                smallest,
                f"{solved.outcome}: {solved.count} hires give {money(solved.forecast_with)}"
                + (
                    f", one fewer {money(solved.forecast_one_fewer)}"
                    if solved.forecast_one_fewer is not None
                    else ""
                )
                + f" against {g.fy_target}",
            )
        )
    else:
        closing["hires"] = {
            "outcome": hire_row["status"],
            "count": None,
            "note": "the hiring action is not valued, so there is no number of hires to solve for",
        }

    # programme dollars
    def forward_programme(dollars: Decimal) -> Decimal:
        p = PlanProgramme("solve", dollars, start)
        f = scen.forecast(
            inflows=programme_inflows(p, g.windows, g.as_of, g.fy_end, ramp_default)
        )
        return scen.fiscal_year(f)

    solved_p = solve_added_pipeline(forward_programme, g.fy_target, g.lever_cap)
    cost_per_dollar = cfg.programme_cost_per_dollar if cfg else None
    closing["programme"] = {
        "outcome": {
            COVERED: "already covered",
            FEASIBLE: "feasible",
            UNREACHABLE: "unreachable",
        }[solved_p.outcome],
        "dollars": None
        if solved_p.required is None or solved_p.outcome == UNREACHABLE
        else money(solved_p.required),
        "needed_but_over_the_cap": money(solved_p.required)
        if solved_p.outcome == UNREACHABLE and solved_p.required is not None
        else None,
        "cap": money(g.lever_cap),
        "cap_rule": "the Goal 1 cap: three times the new-business pipeline created in the trailing 365 days",
        "fiscal_year_bookings_with": money(solved_p.achieved),
        "overshoot": money(solved_p.achieved - g.fy_target)
        if solved_p.outcome == FEASIBLE
        else None,
        "share_booking_in_fiscal_year": None
        if solved_p.outcome != FEASIBLE or not solved_p.required
        else number((solved_p.achieved - solved_p.base) / solved_p.required, 3),
        "cash_cost_in_twelve_months": None
        if cost_per_dollar is None or solved_p.outcome != FEASIBLE
        else money(
            programme_cost_in_window(
                PlanProgramme("solve", solved_p.required, start),
                cost_per_dollar,
                programme_inflows(
                    PlanProgramme("solve", solved_p.required, start),
                    g.windows,
                    g.as_of,
                    g.fy_end,
                    ramp_default,
                ),
                g.windows[-1].end,
            )
        ),
        "cost_status": "entered" if cost_per_dollar is not None else "cost not entered",
    }
    closing["programme"]["cash_cost_note"] = closing_cost_note(
        "programme",
        closing["programme"]["outcome"],
        closing["programme"]["cost_status"],
        closing["programme"]["cash_cost_in_twelve_months"],
    )
    fresh = (
        forward_programme(solved_p.required) if solved_p.outcome == FEASIBLE else None
    )
    ok = (
        abs(fresh - g.fy_target) <= CENT
        if fresh is not None
        else (
            solved_p.base >= g.fy_target
            if solved_p.outcome == COVERED
            else solved_p.achieved < g.fy_target
        )
    )
    checks.append(
        Check(
            "programme solve agrees with the forward function",
            ok,
            f"{solved_p.outcome}: forward({money(solved_p.required) if solved_p.required is not None else 'cap'}) "
            f"= {money(fresh if fresh is not None else solved_p.achieved)} against {g.fy_target}",
        )
    )
    section = {
        "definition": "Two unit actions through the same forward function, the roster as signed: hire one "
        f"AE starting {start}; add ${ACTION_PROGRAMME_DOLLARS:,.0f} of programme pipeline starting {start}. "
        "Gain per dollar is the bookings gained in the next twelve months over the cash cost inside the "
        f"same twelve months. An action starts paying in the first month it adds at least "
        f"{PAYING_SHARE:.0%} of its twelve-month gain.",
        "programme_shape": f"created from {start:%Y-%m} to the fiscal-year end, ramping up over the entered "
        f"ramp ({ramp_default} months unless capacity.yaml says otherwise)",
        "comparison": ranked,
        "close_the_fiscal_year_gap": closing,
        "meaning": "'feasible' means achievable inside the model's bounds, not operationally achievable; "
        "that a new hire adds pipeline at the fitted rate is an assumption",
    }
    return section, checks
