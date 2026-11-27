"""Section 10 of the report: required against expected pipeline, by quarter,
and the team's own created pipeline per ramped AE-month to hold it against."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .capacity_report import Capacity
from .figures import CENT, exact, money, number
from .fiscal import Window, add_months
from .fit import Model
from .forecast import Creation, model_forecast
from .history import creation_amounts
from .lever import COVERED, FEASIBLE, UNREACHABLE
from .records import Check, Dataset
from .requirement import History, QuarterResult, solve_quarters, summarise_history
from .roster import ramped_ae_months

ZERO = Decimal(0)


def observed_history(
    cap: Capacity, pop: Dataset, as_of: date, fy_start: date
) -> History:
    """Created pipeline dollars per ramped AE-month in each complete fiscal
    quarter the files cover, with today's roster and ramp (a stated limit)."""
    if cap.fit is None or not pop.deals:
        return History(0, None, None)
    first = min(d.created for d in pop.deals)
    amounts = creation_amounts(pop)
    rows = []
    k = -40
    while True:
        start = add_months(fy_start, 3 * k)
        end = add_months(start, 3) - timedelta(days=1)
        k += 1
        if end > as_of:
            break
        if start < first:
            continue
        created = sum(
            (
                amounts[d.id]
                for d in pop.deals
                if start <= d.created <= end and amounts.get(d.id) is not None
            ),
            ZERO,
        )
        months = ramped_ae_months(
            cap.members, cap.fit.curve, start - timedelta(days=1), end
        )
        rows.append((created, months))
    return summarise_history(rows)


def required_pipeline(
    cap: Capacity,
    model: Model,
    pop: Dataset,
    as_of: date,
    windows: list[Window],
    targets: dict,
    actual: dict[str, Decimal],
    fy_quarters: tuple[str, ...],
    lever_cap: Decimal,
    single_spread_lever: dict,
    fy_start: date,
) -> tuple[dict, list[Check], list[QuarterResult]]:
    creation: Creation | None = cap.creation
    ramped = cap.projection.ramped_ae_months if cap.projection is not None else ()
    results = solve_quarters(
        model, pop, as_of, windows, targets, actual, creation, lever_cap, ramped
    )
    history = observed_history(cap, pop, as_of, fy_start)
    rows = [_row(r, r.quarter in fy_quarters) for r in results]
    fy = [r for r in results if r.quarter in fy_quarters]
    feasible = [r for r in fy if r.outcome == FEASIBLE]
    out = {
        "method": "one deterministic solve in quarter order; each quarter's pipeline is spread "
        "evenly over the months from the as-of date (or the previous quarter's end) to its end, "
        "and meets that quarter's target given its actual bookings, the pipeline already open and "
        "what earlier quarters were assigned; an unreachable quarter is assigned nothing",
        "forward_function": "the capacity term"
        if cap.adopted
        else "the flat trailing rate",
        "cap": money(lever_cap),
        "cap_rule": "one cap across the quarters: three times the new-business pipeline created in "
        "the trailing 365 days, less what earlier quarters were assigned",
        "quarters": rows,
        "fiscal_year": {
            "sum_of_quarters": money(sum((r.required for r in feasible), ZERO)),
            "quarters_needing_pipeline": [r.quarter for r in feasible],
            "quarters_unreachable": [r.quarter for r in fy if r.outcome == UNREACHABLE],
            "single_spread_lever": single_spread_lever.get("headline"),
            "relation": "The fiscal-year lever, quarter by quarter: the sum of the quarters' "
            "requirements, each quarter's target met on its own. The single-spread lever in "
            "section 5 meets only the year's total with one even spread to year end.",
        },
        "team_history": _history(history, cap),
        "meaning": "'required' means achievable inside the model's bounds (fitted conversion and "
        "timing, the cap above), not operationally achievable",
        "expected_basis": "expected pipeline is what the forward function in use creates; the "
        "ramped AE-months beside it are the roster's expected ones"
        + ("" if cap.adopted else " (a diagnostic here: capacity was not adopted)"),
    }
    checks = _checks(
        results, fy_quarters, model, pop, as_of, windows, creation, actual, targets
    )
    return out, checks, results


def _row(r: QuarterResult, in_fy: bool) -> dict:
    needed = r.required if r.outcome == FEASIBLE else None
    total = None if needed is None else r.expected_created + needed
    months = r.ramped_ae_months

    def per(x):
        return None if x is None or not months else money(x / months)

    if r.outcome == UNREACHABLE:
        headline = (
            "unreachable: pipeline created in time cannot book inside the quarter"
            if r.required is None
            else f"unreachable within the cap (it would take ${r.required:,.2f})"
        )
    else:
        headline = (
            "already covered"
            if r.outcome == COVERED
            else f"required: ${r.required:,.2f}"
        )
    return {
        "quarter": r.quarter,
        "in_fiscal_year": in_fy,
        "status": r.status,
        "target": exact(r.target),
        "actual": exact(r.actual),
        "outcome": r.outcome,
        "headline": headline,
        "required_extra_pipeline": None if needed is None else money(needed),
        "bookings_without_own_pipeline": money(r.forecast_without),
        "bookings_with_own_pipeline": money(r.forecast_with),
        "created_between": [r.piece[0].isoformat(), r.piece[1].isoformat()],
        "expected_created_pipeline": money(r.expected_created),
        "required_total_created_pipeline": None if total is None else money(total),
        "ramped_ae_months": None if months is None else number(months, 1),
        "per_ramped_ae_month": {
            "expected": per(r.expected_created),
            "required_total": per(total),
        },
        "cap_left_before": money(r.cap_left),
        "share_booking_in_quarter": None
        if needed is None or not needed
        else number((r.forecast_with - r.forecast_without) / needed, 3),
    }


def _history(h: History, cap: Capacity) -> dict:
    return {
        "unit": "created pipeline dollars per ramped AE-month",
        "quarters": h.quarters,
        "median": None if h.median is None else money(h.median),
        "best_four_quarter_average": None
        if h.best_four is None
        else money(h.best_four),
        "note": "Observed over the complete fiscal quarters in the files, with today's roster and "
        "ramp; fewer than four quarters has no four-quarter average"
        if cap.fit is not None
        else "unavailable: no usable roster history",
    }


def _checks(
    results, fy_quarters, model, pop, as_of, windows, creation, actual, targets
) -> list[Check]:
    """The quarterly solve, put back through the forward function once, as one
    schedule: every feasible quarter meets its target to the cent and every
    covered one already does; the fiscal-year total is the sum of the pieces."""
    inflows = tuple(f for r in results for f in r.inflows)
    f = model_forecast(model, pop, as_of, windows, creation=creation, inflows=inflows)
    bad = []
    for r in results:
        # a quarter's own months, not the months of the piece it was spread over
        qw = targets[r.quarter][0]
        months = [w.label for w in windows if qw.contains(w.end)]
        got = actual.get(r.quarter, ZERO) + sum(
            (f.window_total(m) for m in months), ZERO
        )
        if r.outcome == FEASIBLE and abs(got - r.target) > CENT:
            bad.append(f"{r.quarter}: {got:.2f} against target {r.target}")
        if r.outcome == COVERED and got < r.target:
            bad.append(f"{r.quarter}: covered but {got:.2f} < {r.target}")
    fy_sum = sum(
        (
            r.required
            for r in results
            if r.quarter in fy_quarters and r.outcome == FEASIBLE
        ),
        ZERO,
    )
    schedule = sum(
        (i.dollars for r in results if r.quarter in fy_quarters for i in r.inflows),
        ZERO,
    )
    tie = abs(fy_sum - schedule) < Decimal("1e-9")
    if not tie:
        bad.append(f"sum of quarters {fy_sum} against schedule {schedule}")
    n = sum(1 for r in results if r.outcome == FEASIBLE)
    return [
        Check(
            "quarterly requirements agree with the forward function and sum to the fiscal-year lever",
            not bad,
            f"{n} feasible quarters re-run together as one schedule; fiscal-year total {fy_sum:.2f}"
            + ("" if not bad else "; " + "; ".join(bad)),
        )
    ]
