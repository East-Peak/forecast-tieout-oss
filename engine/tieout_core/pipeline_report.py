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
from .requirement import (
    History,
    QuarterResult,
    solve_quarters,
    spread_over,
    summarise_history,
)
from .roster import ramped_ae_months

ZERO = Decimal(0)
PER_BASIS_ADOPTED = "the forecast's basis"
PER_BASIS_DIAGNOSTIC = "diagnostic, not the forecast's basis"


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
        "fiscal_year": summarise_fiscal_year(results, fy_quarters, single_spread_lever),
        "per_ramped_ae_month_label": PER_BASIS_ADOPTED
        if cap.adopted
        else PER_BASIS_DIAGNOSTIC,
        "team_history": _history(history, cap),
        "meaning": "'required' means achievable inside the model's bounds (fitted conversion and "
        "timing, the cap above), not operationally achievable",
        "expected_basis": "expected pipeline is what the forward function in use creates; the "
        "ramped AE-months beside it are the roster's expected ones"
        + ("" if cap.adopted else " (a diagnostic here: capacity was not adopted)"),
    }
    checks = quarter_checks(
        results, model, pop, as_of, windows, creation, actual, targets, lever_cap
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


def summarise_fiscal_year(
    results: list[QuarterResult], fy_quarters, single_spread=None
) -> dict:
    """The total for meeting every remaining quarter's target, honestly named:
    when a quarter is unreachable it is a partial total, never a bare number."""
    fy = [r for r in results if r.quarter in fy_quarters]
    solvable = [r for r in fy if r.outcome != UNREACHABLE]
    unreachable = [r.quarter for r in fy if r.outcome == UNREACHABLE]
    total = sum((r.required for r in solvable if r.outcome == FEASIBLE), ZERO)
    if not fy:
        headline = "no remaining quarter in the fiscal year has a target"
    elif not unreachable:
        headline = (
            f"${total:,.2f} of extra pipeline to meet every remaining quarter's target"
        )
    else:
        headline = (
            f"partial: {len(solvable)} of {len(fy)} quarters solvable "
            f"(unreachable: {', '.join(unreachable)})"
            + (f"; ${total:,.2f} covers only the solvable ones" if solvable else "")
        )
    return {
        "name": "pipeline to meet every remaining quarter's target",
        "solvable_total": money(total) if solvable else None,
        "solvable_quarters": [r.quarter for r in solvable],
        "unreachable_quarters": unreachable,
        "quarters_remaining": len(fy),
        "headline": headline,
        "single_spread": {
            "name": "pipeline to meet the fiscal-year total, spread evenly to year end (section 5)",
            "headline": None
            if single_spread is None
            else single_spread.get("headline"),
        },
        "why_they_differ": "Meeting every quarter's own target is stricter than meeting the year's "
        "total: a quarter that is ahead cannot lend its surplus to one that is behind, and pipeline "
        "created in a quarter mostly books after it.",
    }


def quarter_checks(
    results, model, pop, as_of, windows, creation, actual, targets, cap
) -> list[Check]:
    """Independent of the solve's own arithmetic. The solved schedule is run
    through the production forward function once: each solvable quarter's
    bookings meet its stated target to the cent (covered ones already do). Each
    unreachable quarter is shown to be genuinely over the cap, or to be beyond
    the selling window (no pipeline created in time books inside it)."""
    inflows = tuple(f for r in results for f in r.inflows)
    f = model_forecast(model, pop, as_of, windows, creation=creation, inflows=inflows)
    bad = []

    def quarter_total(forecast, quarter):
        qw = targets[quarter][0]
        months = [w.label for w in windows if qw.contains(w.end)]
        return actual.get(quarter, ZERO) + sum(
            (forecast.window_total(m) for m in months), ZERO
        )

    spent = ZERO
    earlier: tuple = ()
    for r in results:
        got = quarter_total(f, r.quarter)
        if r.outcome == FEASIBLE and abs(got - r.target) > CENT:
            bad.append(f"{r.quarter}: {got:.2f} against target {r.target}")
        if r.outcome == COVERED and got < r.target:
            bad.append(f"{r.quarter}: covered but {got:.2f} < {r.target}")
        if r.outcome == UNREACHABLE:
            room = cap - spent
            piece = [
                w for w in windows if r.piece[0] <= w.start and w.end <= r.piece[1]
            ]
            without = model_forecast(
                model, pop, as_of, windows, creation=creation, inflows=earlier
            )
            with_cap = model_forecast(
                model, pop, as_of, windows, creation=creation,
                inflows=(*earlier, *spread_over(piece, as_of, room)) if piece and room > 0 else earlier,
            )  # fmt: skip
            gain = quarter_total(with_cap, r.quarter) - quarter_total(
                without, r.quarter
            )
            if r.required is None:
                if gain > CENT:  # something created in time does book in the quarter
                    bad.append(
                        f"{r.quarter}: called beyond the selling window but the cap books {gain:.2f}"
                    )
            elif not (
                r.required > room and quarter_total(with_cap, r.quarter) < r.target
            ):
                bad.append(
                    f"{r.quarter}: called over the cap but ${room:,.2f} of cap reaches it"
                )
        earlier = (*earlier, *r.inflows)
        spent += r.assigned
    solvable = sum(1 for r in results if r.outcome != UNREACHABLE)
    return [
        Check(
            "quarterly requirements, run together through the forward function, meet each solvable quarter's target",
            not bad,
            f"{solvable} solvable quarters re-run as one schedule; "
            f"{len(results) - solvable} unreachable checked against the cap and the selling window"
            + ("" if not bad else "; " + "; ".join(bad)),
        )
    ]
