"""Section 10 of the report: what must be created from now, by quarter, and which
quarters are already too late to fund with new pipeline; the team's own created
pipeline per ramped AE-month to hold it against; and the lead-time table."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from .capacity_report import Capacity
from .figures import CENT, exact, money, number
from .fiscal import FiscalYear, Window, add_months
from .fit import Model
from .forecast import ADDED, Creation, Inflow, model_forecast
from .history import creation_amounts
from .lever import COVERED, FEASIBLE, UNREACHABLE
from .records import Check, Dataset
from .requirement import (
    PROBE,
    History,
    LeadTimes,
    QuarterResult,
    best_four_per_day,
    close_with_open_pipeline,
    lead_times,
    lead_windows,
    next_quarters,
    per_rep_excess,
    schedule,
    solve_quarters,
    summarize_history,
    too_late,
)
from .roster import ramped_ae_months

ZERO = Decimal(0)
PER_BASIS_ADOPTED = "the forecast's basis"
PER_BASIS_DIAGNOSTIC = "diagnostic, not the forecast's basis"
TOO_LATE = "too late to fund with new pipeline: this quarter depends on the pipeline already open"


def observed_history(
    cap: Capacity, pop: Dataset, as_of: date, fy_start: date
) -> History:
    """Created pipeline in each complete fiscal quarter the files cover: per day (an
    observed fact, no roster needed) and, where a ramp is fitted, per ramped AE-month
    with today's roster and ramp (a stated limit)."""
    if not pop.deals:
        return History(0, None, None)
    first = min(d.created for d in pop.deals)
    amounts = creation_amounts(pop)
    by_ae, by_day = [], []
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
        by_day.append((created, (end - start).days + 1))
        if cap.fit is not None:
            by_ae.append(
                (
                    created,
                    ramped_ae_months(
                        cap.members, cap.fit.curve, start - timedelta(days=1), end
                    ),
                )
            )
    per_day = best_four_per_day(by_day)
    if cap.fit is None:
        return History(len(by_day), None, None, per_day)
    return replace(summarize_history(by_ae), best_four_per_day=per_day)


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
    fy: FiscalYear | None = None,
) -> tuple[dict, list[Check], list[QuarterResult]]:
    creation: Creation | None = cap.creation
    ramped = cap.projection.ramped_ae_months if cap.projection is not None else ()
    results = solve_quarters(
        model, pop, as_of, windows, targets, actual, creation, lever_cap, ramped
    )
    history = observed_history(cap, pop, as_of, fy_start)
    per_rep = cap.adopted
    rows = [_row(r, r.quarter in fy_quarters, history, per_rep) for r in results]
    fy = fy or FiscalYear(fy_start)
    lead = lead_times(model, pop, as_of, next_quarters(fy, as_of))
    out = {
        "method": "one deterministic solve in quarter order; each quarter's pipeline is created "
        "evenly on every day from the day after the as-of date to its end (creation starts now), "
        "and meets that quarter's target given its actual bookings, the pipeline already open and "
        "what earlier quarters were assigned; an unreachable quarter is assigned nothing. "
        "Pipeline assigned to a later quarter is also created in the earlier quarters' months, "
        "so it can only add to them",
        "forward_function": "the capacity term"
        if cap.adopted
        else "the flat trailing rate",
        "cap": money(lever_cap),
        "cap_rule": "one cap across the quarters: three times the new-business pipeline created in "
        "the trailing 365 days, less what earlier quarters were assigned",
        "quarters": rows,
        "fiscal_year": summarize_fiscal_year(
            results, fy_quarters, single_spread_lever, _late_quarters(rows)
        ),
        "per_rep_rule": _per_rep_rule(cap),
        "too_late_rule": "a quarter is too late to fund with new pipeline when its requirement is over the "
        "cap (or the cap is used up, or no pipeline created in time can book inside it), or when "
        "everything created in its span (expected, earlier quarters' assignments and its own "
        "requirement) per day is above the team's best four-quarter average of total created "
        "pipeline per day, or, only where capacity is the forecast's basis, when that total per "
        "ramped AE-month is above the team's best; the reason names exactly the legs that fired",
        "lead_time": _lead_time(lead),
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
    checks = [
        *quarter_checks(
            results, model, pop, as_of, windows, creation, actual, targets, lever_cap
        ),
        yield_check(results, model, pop, as_of, windows, targets),
        lead_check(lead, model, pop, as_of, next_quarters(fy, as_of)),
    ]
    return out, checks, results


NO_EXTRA = "no extra pipeline is required: the quarter is already covered"
FEW_QUARTERS = (
    "unavailable: the team has fewer than four complete quarters to compare with"
)
NO_RAMP = "unavailable: no ramp is fitted, so there are no ramped AE-months"
NO_DAYS = "unavailable: the span has no days"


def quarter_notes(outcome, total, months, days, best_day, best_ae) -> dict:
    """Why a requirement figure is missing, so a screen can tell 'nothing is required' from 'unavailable'.
    Each entry is None when its figures are all there."""
    per_day = per_ae = None
    if total is None:
        per_day = NO_EXTRA
    elif not days:
        per_day = NO_DAYS
    elif best_day is None:
        per_day = FEW_QUARTERS
    if not months:
        per_ae = NO_RAMP
    elif total is None:
        per_ae = NO_EXTRA
    elif best_ae is None:
        per_ae = FEW_QUARTERS
    return {
        "total": NO_EXTRA if total is None else None,
        "per_day": per_day,
        "per_ae": per_ae,
    }


def surplus_statement(surplus: Decimal | None) -> str | None:
    """A quarter's surplus over target in words: a negative one is a shortfall that
    remains, never a negative requirement."""
    if surplus is None:
        return None
    surplus = surplus.quantize(CENT)  # as the report's own figure is rounded
    tail = "once every quarter's schedule is created"
    shown = f"${abs(surplus):,.0f}"
    if surplus > 0:
        return f"ahead of target by {shown} {tail}"
    if surplus < 0:
        return f"still short of target by {shown} even {tail}"
    return f"exactly on target {tail}"


def _row(
    r: QuarterResult, in_fy: bool, history: History, per_rep_applies: bool
) -> dict:
    needed = r.required if r.outcome == FEASIBLE else None
    # an over-the-cap quarter shows what it would take: the rule compares that total
    total = None if r.outcome == COVERED else r.total_in_span
    months, days = r.ramped_ae_months, r.span_days
    best_ae, best_day = history.best_four, history.best_four_per_day

    def per(x, n):
        return None if x is None or not n else money(x / n)

    def against(x, n, best):
        return None if x is None or not n or not best else number(x / n / best, 2)

    if r.outcome == UNREACHABLE:
        if r.required is not None:
            headline = f"unreachable within the cap (it would take ${r.required:,.2f})"
        elif r.yield_per_dollar > 0:
            headline = (
                "unreachable: the cap is used up by earlier quarters' assignments"
            )
        else:
            headline = (
                "unreachable: pipeline created in time cannot book inside the quarter"
            )
    else:
        headline = (
            "already covered"
            if r.outcome == COVERED
            else f"required: ${r.required:,.2f}"
        )
    notes = quarter_notes(
        r.outcome, total, months, days, best_day=best_day, best_ae=best_ae
    )
    reasons = too_late(r, best_ae, best_day, per_rep_applies)
    diagnostics = []
    excess = per_rep_excess(r, best_ae)
    if excess is not None and not per_rep_applies and r.outcome != COVERED:
        diagnostics.append(
            f"per ramped AE-month it would need ${excess:,.0f}, above the team's best of "
            f"${best_ae:,.0f}: a diagnostic here, it does not decide"
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
        "bookings_under_completed_schedule": None
        if r.full_bookings is None
        else money(r.full_bookings),
        "surplus_over_target": None if r.surplus is None else money(r.surplus),
        "surplus_statement": surplus_statement(r.surplus),
        "created_between": [r.piece[0].isoformat(), r.piece[1].isoformat()],
        "expected_created_pipeline": money(r.expected_created),
        "earlier_assigned_in_span": money(r.earlier_assigned),
        "total_created_in_span": None if total is None else money(total),
        "total_created_note": notes["total"],
        "would_take": money(r.required)
        if r.outcome == UNREACHABLE and r.required is not None
        else None,
        "ramped_ae_months": None if months is None else number(months, 1),
        "per_day": {
            "expected": per(r.expected_created, days),
            "required_total": per(total, days),
            "required_against_team_best": against(total, days, best_day),
            "note": notes["per_day"],
        },
        "per_ramped_ae_month": {
            "expected": per(r.expected_created, months),
            "required_total": per(total, months),
            "required_against_team_best": against(total, months, best_ae),
            "decides": per_rep_applies,
            "note": notes["per_ae"],
        },
        "cap_left_before": money(r.cap_left),
        "cents_booked_in_quarter_per_dollar": number(r.yield_per_dollar * 100, 2),
        "too_late": {
            "applies": bool(reasons),
            "label": TOO_LATE if reasons else None,
            "legs": [c for c, _ in reasons],
            "reasons": [t for _, t in reasons],
            "diagnostics": diagnostics,
            "open_pipeline": _open_pipeline(r) if reasons else None,
        },
    }


def _open_pipeline(r: QuarterResult) -> dict:
    """What the open pipeline contributes, and what win rate on it would close the
    quarter: arithmetic on figures the report already holds, not a solved lever."""
    c = close_with_open_pipeline(r)

    def pct(x):
        return "n/a" if x is None else f"{float(x):.1%}"

    if c.open_arr == 0:
        statement = "no open pipeline to win from"
    elif c.possible:
        statement = (
            f"to close it, ${c.needed:,.0f} of the open pipeline would have to book inside the "
            f"quarter ({pct(c.needed_share)} of its dollars) against the {pct(c.expected_share)} "
            "expected (arithmetic on the figures above, not a lever the model solves)"
        )
    else:
        statement = (
            f"no win rate on the open pipeline closes it: ${c.needed:,.0f} would have to book "
            f"from ${c.open_arr:,.0f} open (arithmetic on the figures above, not a lever the model solves)"
        )
    return {
        "open_arr": money(c.open_arr),
        "expected_contribution": money(c.expected),
        "needed_contribution": money(c.needed),
        "expected_share_of_open": None
        if c.expected_share is None
        else number(c.expected_share, 4),
        "needed_share_of_open": None
        if c.needed_share is None
        else number(c.needed_share, 4),
        "possible": c.possible,
        "statement": statement,
    }


def _late_quarters(rows: list[dict]) -> list[str]:
    return [r["quarter"] for r in rows if r["too_late"]["applies"]]


def _per_rep_rule(cap: Capacity) -> dict:
    if cap.adopted:
        return {
            "applies": True,
            "why": "capacity is the forecast's basis, so the team's best per ramped AE-month is a "
            "third leg beside the cap and the total rate",
        }
    return {
        "applies": False,
        "why": "capacity was not shown to explain pipeline in this history, so the per-ramped-AE-month "
        "comparison is a diagnostic only and does not decide; the cap and the total rate do",
    }


def _lead_time(lt: LeadTimes) -> dict:
    cumulative = dict(lt.cumulative)
    return {
        "question": "of a dollar of pipeline created next month (at its first recorded amount), the "
        "cents booked by the end of each of the next four quarters",
        "basis": "the production forward function's own timing, on a probe dollar-amount created "
        "evenly through the month; independent of the capacity decision. These are dollar yields, "
        "not probabilities: amounts change between creation and win, so they can exceed or fall "
        "short of what the deal counts imply and are not forced to sum to one",
        "created_between": [
            lt.created_between[0].isoformat(),
            lt.created_between[1].isoformat(),
        ],
        "quarters": [
            {
                "quarter": k,
                "cents_booked_in_quarter": number(v * 100, 2),
                "cents_booked_by_quarter_end": number(cumulative[k] * 100, 2),
            }
            for k, v in lt.booked
        ],
        "cents_booked_later": number(lt.later * 100, 2),
        "count_outcome": {
            "meaning": "of the deals created, from the fit in use; counts, so these sum to one",
            "win_within_horizon": number(lt.win_share, 6),
            "do_not_win": number(lt.not_win_share, 6),
        },
    }


def _history(h: History, cap: Capacity) -> dict:
    return {
        "unit": "created pipeline dollars per ramped AE-month",
        "quarters": h.quarters,
        "median": None if h.median is None else money(h.median),
        "best_four_quarter_average": None
        if h.best_four is None
        else money(h.best_four),
        "best_four_quarter_average_per_day": None
        if h.best_four_per_day is None
        else money(h.best_four_per_day),
        "per_day_unit": "total created pipeline dollars per day, over four consecutive complete "
        "fiscal quarters (observed; needs no roster)",
        "note": "Observed over the complete fiscal quarters in the files, with today's roster and "
        "ramp; fewer than four quarters has no four-quarter average"
        if cap.fit is not None
        else "per ramped AE-month unavailable: no usable roster history",
    }


def summarize_fiscal_year(
    results: list[QuarterResult], fy_quarters, single_spread=None, late=()
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
    late = [q for q in late if q in fy_quarters]
    if late:
        headline += f"; too late to fund with new pipeline: {', '.join(late)}"
    return {
        "name": "pipeline to meet every remaining quarter's target",
        "too_late_quarters": late,
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
            "outcome": None if single_spread is None else single_spread.get("outcome"),
            "required": None
            if single_spread is None
            else single_spread.get("required"),
        },
        "why_they_differ": "Meeting every quarter's own target is stricter than meeting the year's "
        "total: a quarter that is ahead cannot lend its surplus to one that is behind, and pipeline "
        "created in a quarter mostly books after it.",
    }


def quarter_checks(
    results, model, pop, as_of, windows, creation, actual, targets, cap
) -> list[Check]:
    """Independent of the solve's own arithmetic, in two checks.

    First: the schedules up to and including each quarter's own are run through the
    production forward function and each solvable quarter's bookings meet its stated
    target to the cent (covered ones already do). Each unreachable quarter is shown
    to be genuinely over the cap, to have had the cap used up by earlier quarters
    (while a probe that ignores the cap does book in it), or to be beyond the
    selling window (the probe books nothing in it).

    Second: the completed schedule, every quarter's pipeline created together, books
    in each quarter what the report states, rebuilt by adding each quarter's own
    schedule to the no-pipeline forecast (the forward function is linear in it); a
    solvable quarter is never below target, only above it."""
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
        # solved in order: the schedules up to and including this quarter's own
        f = model_forecast(
            model,
            pop,
            as_of,
            windows,
            creation=creation,
            inflows=(*earlier, *r.inflows),
        )
        got = quarter_total(f, r.quarter)
        if r.outcome == FEASIBLE and abs(got - r.target) > CENT:
            bad.append(f"{r.quarter}: {got:.2f} against target {r.target}")
        if r.outcome == COVERED and got < r.target:
            bad.append(f"{r.quarter}: covered but {got:.2f} < {r.target}")
        if r.outcome == UNREACHABLE:
            room = cap - spent
            without = model_forecast(
                model, pop, as_of, windows, creation=creation, inflows=earlier
            )
            with_cap = model_forecast(
                model, pop, as_of, windows, creation=creation,
                inflows=(*earlier, *schedule(as_of, r.piece[1], max(room, ZERO))),
            )  # fmt: skip
            gain = quarter_total(with_cap, r.quarter) - quarter_total(
                without, r.quarter
            )
            probe = model_forecast(
                model, pop, as_of, windows, creation=creation,
                inflows=(*earlier, *schedule(as_of, r.piece[1], PROBE)),
            )  # fmt: skip
            probe_gain = quarter_total(probe, r.quarter) - quarter_total(
                without, r.quarter
            )
            if r.required is None and r.yield_per_dollar > 0:
                if room > 0 or probe_gain <= CENT:
                    bad.append(
                        f"{r.quarter}: called cap-used-up but ${room:,.2f} is left and a probe books {probe_gain:.2f}"
                    )
            elif r.required is None:
                if gain > CENT or probe_gain > CENT:  # something created in time books
                    bad.append(
                        f"{r.quarter}: called beyond the selling window but a probe books {probe_gain:.2f}"
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
            "each solvable quarter meets its target under the schedules solved up to and including it",
            not bad,
            f"{solvable} solvable quarters re-run through the forward function, each with the "
            f"schedules solved up to and including its own; {len(results) - solvable} unreachable "
            "checked against the cap, the cap left and the selling window"
            + ("" if not bad else "; " + "; ".join(bad)),
        ),
        _completed_check(
            results, model, pop, as_of, windows, creation, actual, targets
        ),
    ]


def _completed_check(
    results, model, pop, as_of, windows, creation, actual, targets
) -> Check:
    base = model_forecast(model, pop, as_of, windows, creation=creation)
    own = [
        model_forecast(model, pop, as_of, windows, creation=creation, inflows=r.inflows)
        for r in results
    ]
    bad = []
    for r in results:
        labels = [w.label for w in windows if targets[r.quarter][0].contains(w.end)]
        total = actual.get(r.quarter, ZERO) + sum(
            (base.window_total(m) for m in labels), ZERO
        )
        for f in own:
            if ADDED in f.components:
                total += sum((f.components[ADDED][m] for m in labels), ZERO)
        if r.full_bookings is None or abs(total - r.full_bookings) > CENT:
            bad.append(
                f"{r.quarter}: rebuilt {total:.2f} against stated {r.full_bookings}"
            )
        elif r.outcome != UNREACHABLE and total < r.target - CENT:
            bad.append(f"{r.quarter}: {total:.2f} under its target {r.target}")
    return Check(
        "the completed schedule books each quarter's stated bookings and surplus over target",
        not bad,
        f"{len(results)} quarters rebuilt by adding each quarter's own schedule to the "
        "no-pipeline forecast" + ("" if not bad else "; " + "; ".join(bad)),
    )


def yield_check(results, model, pop, as_of, windows, targets) -> Check:
    """Each solved quarter's yield is re-derived from its own solved schedule (not
    the probe amount the figure came from): the dollars it books inside the quarter
    over the dollars it creates must equal the stated share."""
    bad, checked = [], 0
    for r in results:
        if r.outcome != FEASIBLE or not r.required:
            continue
        qw = targets[r.quarter][0]
        labels = [w.label for w in windows if qw.contains(w.end)]
        f = model_forecast(model, pop, as_of, windows, inflows=r.inflows)
        got = sum((f.components[ADDED][m] for m in labels), ZERO) / r.required
        checked += 1
        if abs(got - r.yield_per_dollar) > Decimal("1e-9"):
            bad.append(
                f"{r.quarter}: {got:.6f} against stated {r.yield_per_dollar:.6f}"
            )
    return Check(
        "cents booked in each quarter, re-derived from the solved schedule, match the stated yield",
        not bad,
        f"{checked} solved schedules re-run on their own"
        + ("" if not bad else "; " + "; ".join(bad)),
    )


def lead_check(lt: LeadTimes, model: Model, pop, as_of, quarters) -> Check:
    """Each quarter's yield is checked against an independent run of the forward
    function on a different probe: another dollar amount, created through the month
    as two inflows split at its middle. The count shares (deals expected to win,
    and not) sum to one and the win share is the fitted win rate."""
    windows, first, last = lead_windows(model, as_of, quarters)
    n, a0 = (last - first).days, (first - as_of).days
    half = n // 2
    amount = Decimal(250_000)
    f = model_forecast(
        model, pop, as_of, windows,
        inflows=(
            Inflow(a0, a0 + half, amount * half / n),
            Inflow(a0 + half, a0 + n, amount * (n - half) / n),
        ),
    )  # fmt: skip
    bad = []
    for (k, got), (_, qw) in zip(lt.booked, quarters):
        probe = (
            sum(
                (f.components[ADDED][w.label] for w in windows if qw.contains(w.end)),
                ZERO,
            )
            / amount
        )
        if abs(probe - got) > Decimal("1e-9"):
            bad.append(f"{k}: probe {probe:.6f} against stated {got:.6f}")
    total = lt.win_share + lt.not_win_share
    if abs(total - 1) > Decimal("1e-12") or lt.win_share != model.new_pipeline.win_rate:
        bad.append(
            f"count shares {lt.win_share} + {lt.not_win_share} against the fitted win rate"
        )
    return Check(
        "lead-time yields match an independent forward run on a probe schedule, and the count shares sum to one",
        not bad,
        f"{len(lt.booked)} quarters checked on a ${amount:,.0f} probe in two parts; win share "
        f"{lt.win_share:.4f}, not {lt.not_win_share:.4f}"
        + ("" if not bad else "; " + "; ".join(bad)),
    )
