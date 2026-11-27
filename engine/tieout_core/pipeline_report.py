"""Section 10 of the report: what must be created from now, by quarter, and which
quarters are already too late to fund with new pipeline; the team's own created
pipeline per ramped AE-month to hold it against; and the lead-time table."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .capacity_report import Capacity
from .figures import CENT, exact, money, number
from .fiscal import FiscalYear, Window, add_months
from .fit import Model
from .forecast import ADDED, Creation, model_forecast
from .history import creation_amounts
from .lever import COVERED, FEASIBLE, UNREACHABLE
from .records import Check, Dataset
from .requirement import (
    History,
    LeadTimes,
    QuarterResult,
    close_with_open_pipeline,
    lead_times,
    next_quarters,
    schedule,
    solve_quarters,
    summarise_history,
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
    fy: FiscalYear | None = None,
) -> tuple[dict, list[Check], list[QuarterResult]]:
    creation: Creation | None = cap.creation
    ramped = cap.projection.ramped_ae_months if cap.projection is not None else ()
    results = solve_quarters(
        model, pop, as_of, windows, targets, actual, creation, lever_cap, ramped
    )
    history = observed_history(cap, pop, as_of, fy_start)
    per_rep = cap.adopted
    rows = [
        _row(r, r.quarter in fy_quarters, history.best_four, per_rep) for r in results
    ]
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
        "fiscal_year": summarise_fiscal_year(
            results, fy_quarters, single_spread_lever, _late_quarters(rows)
        ),
        "per_rep_rule": _per_rep_rule(cap),
        "too_late_rule": "a quarter is too late to fund with new pipeline when what it needs is over "
        "the cap (or no pipeline created in time can book inside it), or, where the per-ramped-AE-month "
        "comparison applies, when its requirement per ramped AE-month is above the team's best "
        "four-quarter average",
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
        lead_check(lead, model),
    ]
    return out, checks, results


def _row(r: QuarterResult, in_fy: bool, best_four, per_rep_applies: bool) -> dict:
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
    reasons = too_late(r, best_four, per_rep_applies)
    versus = None
    if total is not None and months and best_four:
        versus = number(total / months / best_four, 2)
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
            "required_against_team_best": versus,
        },
        "cap_left_before": money(r.cap_left),
        "cents_booked_in_quarter_per_dollar": number(r.yield_per_dollar * 100, 2),
        "too_late": {
            "applies": bool(reasons),
            "label": TOO_LATE if reasons else None,
            "reasons": list(reasons),
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
            f"the open pipeline's ${c.open_arr:,.0f} would have to book ${c.needed:,.0f} inside the "
            f"quarter ({pct(c.needed_share)} of its dollars) against the {pct(c.expected_share)} "
            "expected; this is arithmetic on the figures above, not a lever the model solves"
        )
    else:
        statement = (
            f"no win rate on the open pipeline closes it: ${c.needed:,.0f} would have to book "
            f"from ${c.open_arr:,.0f} open (arithmetic on the figures above, not a lever)"
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
            "fair ceiling on what the team can create",
        }
    return {
        "applies": False,
        "why": "capacity was not shown to explain pipeline in this history, so the per-ramped-AE-month "
        "comparison is a diagnostic only and the cap decides alone",
    }


def _lead_time(lt: LeadTimes) -> dict:
    cumulative = dict(lt.cumulative)
    return {
        "question": "of a dollar of pipeline created next month, the share booked by the end of each "
        "of the next four quarters",
        "basis": "the production forward function's own timing, on a probe dollar-amount created "
        "evenly through the month; independent of the capacity decision",
        "created_between": [
            lt.created_between[0].isoformat(),
            lt.created_between[1].isoformat(),
        ],
        "quarters": [
            {
                "quarter": k,
                "booked_in_quarter": number(v, 6),
                "booked_by_quarter_end": number(cumulative[k], 6),
            }
            for k, v in lt.booked
        ],
        "booked_later": number(lt.later, 6),
        "never_booked": number(lt.never, 6),
        "never_booked_meaning": "the dollars that do not win (lost or never closing)",
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


def lead_check(lt: LeadTimes, model: Model) -> Check:
    """The lead-time shares and the share never booked sum to one, and the share
    never booked equals the dollars that do not win, worked out from the fitted
    win rate and deal sizes rather than from the forward function."""
    new = model.new_pipeline
    wins = (
        new.win_rate * new.mean_won_arr / new.mean_created_arr
        if new.mean_created_arr
        else ZERO
    )
    total = sum((v for _, v in lt.booked), ZERO) + lt.later + lt.never
    bad = []
    if abs(total - 1) > Decimal("1e-9"):
        bad.append(f"shares sum to {total:.9f}")
    if abs(lt.never - (1 - wins)) > Decimal("1e-9"):
        bad.append(
            f"never booked {lt.never:.6f} against {1 - wins:.6f} from the win rate"
        )
    return Check(
        "lead-time shares plus the share never booked sum to one, and never booked is the dollars that do not win",
        not bad,
        f"never booked {lt.never:.4f}, booked later {lt.later:.4f}"
        + ("" if not bad else "; " + "; ".join(bad)),
    )
