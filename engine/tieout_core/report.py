"""Assemble the forecast-and-gap report.

``build_report`` returns one JSON-ready dict; ``render_markdown`` renders that
same dict, so the two files cannot disagree. Nothing here reads the clock.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import capacity_report
from .backtest import (
    HORIZONS,
    MIN_FOLDS,
    UNVALIDATED,
    choose_fit,
    coverage_label,
)
from .figures import CENT
from .figures import cents as _cents
from .figures import exact as _exact
from .figures import money as _money
from .figures import opt_money as _opt_money
from .fiscal import Window, add_months, month_windows
from .fit import DEFAULT_PARAMS, PARAMETER_RANGES, RECENCY, FitParams, fit
from .forecast import (
    Forecast,
    existing_pipeline_conservation,
    model_forecast,
    run_rate,
    simulate,
    stage_weighted,
)
from .history import creation_amounts, latest_known_date
from .lever import COVERED, FEASIBLE, UNREACHABLE, solve_added_pipeline
from .load import load_company, load_profile
from .markdown import render as render_markdown
from .rates import DEFAULT, Rate, RateBook
from .reconcile import reconcile
from .records import Check

SECTIONS = (
    "reconciliation",
    "history",
    "forecasts",
    "rates",
    "gap",
    "backtest",
    "verdicts",
)
MEASURE = "new-business ARR bookings (type = new_business, the arr column)"
REST_OF_FY = "rest of fiscal year"
NEXT_12 = "next twelve months"
NO_TARGET = "no target in this window"
LEVER_CAP_MULTIPLE = 3


def build_report(
    profile_dir: Path,
    data_dir: Path,
    as_of: date,
    draws: int = 2000,
    seed: int = 0,
    params: FitParams = DEFAULT_PARAMS,
    plan_path: Path | None = None,
) -> dict:
    profile = load_profile(Path(profile_dir))
    loaded = load_company(Path(data_dir), profile)
    rec = reconcile(Path(data_dir), loaded, profile, as_of)
    pop = rec.population
    fy = profile.fiscal_year
    horizon_end = add_months(as_of, 12)
    windows = month_windows(as_of, horizon_end)
    labels = [w.label for w in windows]
    horizons = {
        REST_OF_FY: [w.label for w in windows if w.end <= fy.end],
        NEXT_12: labels,
    }
    targets = _targets(profile, horizon_end)

    # Goal 2B: whether the capacity term replaces the flat creation rate is decided
    # once, here, and then every forecast, range, gap and lever uses that one choice.
    cap = capacity_report.prepare(
        profile_dir, data_dir, pop, as_of, (horizon_end - as_of).days, params
    )
    creation = cap.creation

    # Goal 2A step 2.1: the recency candidate is scored against the incumbent fit
    # on the same folds, and adopted for this company only by the declared rule.
    incumbent_name = params.estimator
    params, bt, recency = choose_fit(
        pop, as_of, profile, params, min(draws, 1000), seed,
        creation_for=capacity_report.creation_for(cap),
    )  # fmt: skip

    model = fit(pop, as_of, profile, params)
    forecasts = [
        run_rate(pop, as_of, windows, params.trailing_days),
        stage_weighted(pop, as_of, profile, windows, params.trailing_days),
        model_forecast(model, pop, as_of, windows, creation=creation),
    ]
    fitted = forecasts[2]
    quarter_labels = {
        q: [w.label for w in windows if qw.contains(w.end)]
        for q, (qw, _) in targets.items()
    }
    sim = None
    if fitted.available:
        sim = simulate(
            model,
            pop,
            as_of,
            windows,
            draws=draws,
            seed=seed,
            groups={**quarter_labels, **horizons},
            parameter_uncertainty=params.ranges == PARAMETER_RANGES,
            creation=creation,
        )

    book = RateBook()
    for r in model.rates:
        book.add(r)
    for f in forecasts:
        for r in f.rates:
            book.add(r)
    for r in _parameters(params, draws, seed):
        book.add(r)
    for r in capacity_report.rates(cap):
        book.add(r)

    gap, lever_checks = _gap(
        rec, profile, model, pop, as_of, windows, fitted, sim, targets, quarter_labels,
        horizons, creation,
    )  # fmt: skip
    fy_target = sum(profile.quarterly_targets.values(), Decimal(0))
    diagnostic = (
        _diagnostic(cap, model, pop, as_of, windows, horizons, fitted)
        if not cap.adopted and cap.projection is not None and fitted.available
        else None
    )
    roster_section = capacity_report.roster_capacity(
        cap, as_of, windows, Path(profile_dir), diagnostic
    )
    productivity = capacity_report.quota_productivity(cap, pop, as_of, fy_target)
    checks = list(rec.checks) + [
        existing_pipeline_conservation(model, pop, as_of, windows)
        if windows
        else _no_windows_check(),
        *lever_checks,
        _simulation_check(fitted, sim),
        _components_check(forecasts, labels),
        Check(
            "folds saw nothing after their cutoff",
            True,
            f"{len({f.cutoff for f in bt.folds})} cutoffs rebuilt with as_known_at; each fold "
            "asserts its latest fact is on or before its cutoff",
        ),
        Check(
            "every rate defined once", True, f"{len(list(book))} rates in one registry"
        ),
        *capacity_report.checks(cap, productivity, fitted),
    ]
    failed = [c for c in checks if not c.passed]

    report = {
        "inputs": {
            "profile": str(profile_dir),
            "data": str(data_dir),
            "as_of": as_of.isoformat(),
            "fiscal_year": fy.label,
            "fiscal_year_start": fy.start.isoformat(),
            "fiscal_year_end": fy.end.isoformat(),
            "measure": MEASURE,
            "fit": params.estimator,
            "ranges": params.ranges,
            "simulation": {"draws": draws, "seed": seed},
            "capacity": {
                "decision": cap.adoption.outcome,
                "forecast_uses": "capacity term"
                if cap.adopted
                else "flat trailing creation rate",
            },
        },
        "reconciliation": _reconciliation(rec),
        "history": _history(loaded, rec, model, bt, as_of, recency, cap),
        "forecasts": _forecasts(forecasts, labels, horizons, sim, bt),
        "rates": [_rate(r) for r in book],
        "gap": gap,
        "backtest": {
            **_backtest(bt),
            "candidates": {
                "recency": _candidate(recency, incumbent_name, params.estimator)
            },
        },
        "verdicts": {
            "software_correct": {
                "verdict": "no" if failed else "yes",
                "summary": (
                    f"{len(checks) - len(failed)} of {len(checks)} self-checks passed"
                    + (
                        ": failed " + ", ".join(c.name for c in failed)
                        if failed
                        else ""
                    )
                ),
                "checks": [_check(c) for c in checks],
                "scope": "runtime self-checks on this report's own numbers; the arithmetic is also "
                "checked on hand-calculated fixtures by the test suite (pytest engine/tests/tieout_core)",
            },
            "forecast_better_than_baselines": {
                "verdict": bt.verdict,
                "reason": bt.verdict_reason,
            },
        },
        "roster_capacity": roster_section,
        "quota_productivity": productivity,
    }
    return report


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / "report.md", out / "report.json"
    md.write_text(render_markdown(report))
    js.write_text(json.dumps(report, indent=2) + "\n")
    return md, js


# ---------------------------------------------------------------- sections


def _reconciliation(rec) -> dict:
    return {
        "source_rows": rec.source_rows,
        "source_arr_total": _exact(rec.source_arr_total),
        "included_rows": len(rec.population.deals),
        "bookings_by_month": {k: _exact(v) for k, v in rec.bookings_by_month.items()},
        "bookings_fytd": _exact(rec.bookings_fytd),
        "excluded_motions": {
            k: {
                "rows": m.rows,
                "arr": _exact(m.arr),
                "won_fytd_arr": _exact(m.won_fytd_arr),
            }
            for k, m in rec.excluded_motions.items()
        },
        "pipeline_flow": {
            name: {"count": t.count, "arr": _exact(t.arr)}
            for name, t in (
                ("open at fiscal-year start", rec.flow.open_at_start),
                ("created", rec.flow.created),
                ("won", rec.flow.won),
                ("lost", rec.flow.lost),
                ("open at as-of", rec.flow.open_at_end),
            )
        },
        "exclusions": [
            {
                "row": e.row,
                "deal_id": e.deal_id,
                "reason": e.reason,
                "arr": None if e.arr is None else _exact(e.arr),
            }
            for e in rec.exclusions
        ],
        "checks": [_check(c) for c in rec.checks],
    }


def _history(loaded, rec, model, bt, as_of, recency, cap=None) -> dict:
    pop = rec.population
    deals = pop.deals
    first = min((d.created for d in deals), default=None)
    months = (as_of.year - first.year) * 12 + as_of.month - first.month if first else 0
    closed = [d for d in deals if d.is_closed]
    with_history = {t.deal_id for t in pop.transitions}
    last = {}
    for t in pop.transitions:
        last[t.deal_id] = t
    mismatched = sum(1 for d in closed if d.id in last and last[d.id].on != d.close)
    open_unknown = sum(1 for d in deals if not d.is_closed and d.id not in with_history)
    folds = {s.horizon: s.folds for s in bt.scores}

    limits = [
        (
            "stage_history.csv records stage changes only: it holds no past deal amounts and no past "
            "expected close dates"
        ),
    ]
    if pop.observations is None:
        limits.append(
            "no deal_observations.csv: past amounts and past expected close dates cannot be "
            "reconstructed, so the fitted model and the stage-weighted baseline are not back-tested "
            "in dollars, and created-pipeline amounts use current amounts"
        )
    else:
        limits.append(
            f"deal_observations.csv supplies past amounts and expected close dates "
            f"({len(pop.observations)} observations); a deal's state on a past date is its latest "
            "observation on or before that date"
        )
    if mismatched:
        limits.append(
            f"{mismatched} closed deals have a close date that differs from their final stage transition"
        )
    no_history = sum(1 for d in deals if d.id not in with_history)
    if no_history:
        limits.append(
            f"{no_history} deals have no stage history, so they never appear in a win-rate snapshot; "
            f"{open_unknown} of them are open: today's forecasts use their current stage from "
            "deals.csv, but at past cutoffs their stage is unknown and back-test folds leave them out"
        )
    latest = latest_known_date(pop) if deals else None
    if latest is not None and (as_of - latest).days > 31:
        limits.append(
            f"the files' latest dated entry is {latest}, {(as_of - latest).days} days before the "
            "as-of date: nothing after it was observed, and back-test folds stop there"
        )
    if loaded.unmapped_transitions:
        limits.append(
            f"{loaded.unmapped_transitions} stage-history rows name a stage outside the profile mapping"
        )
    for h, n in sorted(folds.items()):
        if n == 0:
            limits.append(
                f"{h}-month back-test: zero eligible folds, not enough history"
            )
        elif n < MIN_FOLDS:
            limits.append(
                f"{h}-month back-test: {n} folds, fewer than the {MIN_FOLDS} a verdict needs"
            )
    if model.params.estimator == RECENCY:
        limits.append(
            f"win rates use snapshots from the trailing {model.params.recency_months} months, young "
            "ones counted only for the days observed (the recency fit was adopted: "
            f"{recency.reason})"
        )
    else:
        limits.append(
            f"win rates learn only from snapshots at least {model.params.horizon_days} days old, so "
            f"a change in conversion shows up a year late (the recency fit was not adopted: "
            f"{recency.reason})"
        )
    if model.snapshot_count == 0:
        limits.append(
            f"no snapshot is {model.params.horizon_days} days old yet, so every win rate falls back to "
            "the profile's stage probabilities"
        )
    limits.append(
        "the model is pooled across segments; a segment split is not evaluated in this report"
    )
    limits.append(
        "roles on team_members.csv: "
        + ", ".join(f"{k} {v}" for k, v in sorted(loaded.roster_roles.items()))
        + "; "
        + (
            f"the capacity term is {cap.adoption.outcome} ({cap.adoption.reason})"
            if cap is not None
            else "capacity is not assessed"
        )
    )
    limits.append(
        "team_members.csv holds no history of role, segment, quota or deal ownership: today's "
        "values stand in for every past date, and a deal's owner is its current owner"
    )
    return {
        "facts": {
            "first_deal_created": first.isoformat() if first else None,
            "months_of_history": months,
            "new_business_deals": len(deals),
            "closed_outcomes": len(closed),
            "earliest_close": min(d.close for d in closed).isoformat()
            if closed
            else None,
            "deal_observations": pop.observations is not None,
            "matured_snapshots": model.snapshot_count,
            "backtest_folds": {f"{h}m": n for h, n in sorted(folds.items())},
        },
        "limitations": limits,
    }


def _forecasts(forecasts: list[Forecast], labels, horizons, sim, bt) -> dict:
    cells = [
        {
            "horizon_months": s.horizon,
            "folds_with_a_range": s.range_folds,
            "coverage80": None if s.coverage80 is None else round(s.coverage80, 4),
            "coverage95": None if s.coverage95 is None else round(s.coverage95, 4),
            "median_width80": None
            if s.median_width80 is None
            else _float(s.median_width80),
            "label": coverage_label(s.inside80, s.range_folds),
        }
        for s in bt.scores
    ]
    status = "; ".join(
        f"{c['horizon_months']}-month {c['label']} ("
        + (
            f"80% range held {c['coverage80']:.0%} of {c['folds_with_a_range']} folds"
            if c["folds_with_a_range"]
            else "no folds with a range"
        )
        + ")"
        for c in cells
    )
    statuses = {
        REST_OF_FY: _window_status(len(horizons[REST_OF_FY]), cells),
        NEXT_12: f"{UNVALIDATED}: twelve-month ranges are not back-tested (the back-test scores "
        f"{', '.join(str(h) for h in HORIZONS)} months)",
    }

    def totals(f: Forecast) -> dict:
        # The sum of the rounded months, so a shown total adds up to the months shown.
        return {h: _money(_shown(f, ls)) for h, ls in horizons.items()}

    return {
        "windows": labels,
        "horizon_windows": {
            h: [ls[0], ls[-1]] if ls else [] for h, ls in horizons.items()
        },
        "methods": [
            {
                "method": f.method,
                "available": f.available,
                "unavailable_reason": f.unavailable_reason,
                "components": {
                    k: {lbl: _money(v) for lbl, v in c.items()}
                    for k, c in f.components.items()
                },
                "by_window": {lbl: _money(f.window_total(lbl)) for lbl in labels}
                if f.available
                else {},
                "horizons": totals(f) if f.available else {},
                "assumptions": list(f.assumptions),
            }
            for f in forecasts
        ],
        "fitted_ranges": {
            "status": status,
            "cells": cells,
            "by_window": {lbl: _spread(s) for lbl, s in sim.by_window.items()},
            "horizons": {
                h: {"status": statuses[h], **_spread(sim.by_group[h])} for h in horizons
            },
        }
        if sim is not None
        else {
            "status": f"unavailable: {forecasts[2].unavailable_reason}",
            "cells": cells,
            "by_window": {},
            "horizons": {},
        },
    }


def _window_status(months: int, cells: list[dict]) -> str:
    """A window's range is judged by the shortest back-tested horizon that
    covers it; past the longest one it is unvalidated."""
    if months == 0:
        return "no months in this window"
    for c in cells:
        if c["horizon_months"] >= months:
            return f"{c['label']}: judged by the {c['horizon_months']}-month back-test cell"
    return f"{UNVALIDATED}: longer than the longest back-tested horizon ({HORIZONS[-1]} months)"


def _targets(profile, horizon_end: date) -> dict[str, tuple[Window, Decimal]]:
    """Quarters that have a target: the fiscal year's, then any of the next
    year's that end inside the twelve-month window."""
    fy = profile.fiscal_year
    out = {
        q: (fy.quarter_window(q), profile.quarterly_targets[q]) for q in fy.quarter_keys
    }
    for q, target in profile.later_targets.items():
        window = fy.next.quarter_window(q)
        if window.end <= horizon_end:
            out[q] = (window, target)
    return out


def _quarter_actual(rec, window: Window) -> Decimal:
    return sum(
        (v for m, v in rec.bookings_by_month.items() if window.contains(_month_end(m))),
        Decimal(0),
    )


def _status(window: Window, as_of: date) -> str:
    if window.end <= as_of:
        return "closed"
    return "not started" if window.start >= as_of else "in progress"


def _sum(f: Forecast, labels) -> Decimal:
    return sum((f.window_total(lbl) for lbl in labels), Decimal(0))


def _shown(f: Forecast, labels) -> Decimal:
    """A displayed total: the sum of the months as shown (each to the cent), so
    every total in the report adds up to the months beside it."""
    return sum((_cents(f.window_total(lbl)) for lbl in labels), Decimal(0))


def _gap(rec, profile, model, pop, as_of, windows, fitted, sim, targets, quarter_labels,
         horizons, creation=None):  # fmt: skip
    if not fitted.available:
        return _gap_unavailable(
            rec, profile, as_of, windows, targets, fitted.unavailable_reason
        )
    fy = profile.fiscal_year
    quarters = []
    for q, (qw, target) in targets.items():
        actual = _quarter_actual(rec, qw)
        forecast = _shown(fitted, quarter_labels[q])
        spread = sim.by_group[q]
        quarters.append(
            {
                "quarter": q,
                "status": _status(qw, as_of),
                "target": _exact(target),
                "actual": _exact(actual),
                "forecast": _money(forecast),
                "expected": _money(actual + _cents(forecast)),
                "gap": _money(target - actual - _cents(forecast)),
                "expected_range80": [
                    _float(float(actual) + spread.p10),
                    _float(float(actual) + spread.p90),
                ],
            }
        )
    target = sum(profile.quarterly_targets.values(), Decimal(0))
    rest = _shown(fitted, horizons[REST_OF_FY])
    year = sim.by_group[REST_OF_FY]
    fytd = rec.bookings_fytd
    cap = LEVER_CAP_MULTIPLE * _trailing_created_arr(
        pop, as_of, model.params.trailing_days
    )

    def lever(check_name, actual, goal, months, through):
        def run(added: Decimal) -> Forecast:
            return model_forecast(
                model, pop, as_of, windows, added_pipeline=added, added_through=through,
                creation=creation,
            )  # fmt: skip

        return _lever(check_name, lambda a: actual + _sum(run(a), months), run, goal,
                      cap, len(months), model.params.trailing_days, horizons)  # fmt: skip

    fy_lever, fy_check = lever(
        "lever agrees with forward function", fytd, target, horizons[REST_OF_FY], fy.end
    )
    next12, lever12, check12 = _next_twelve_months(
        rec, as_of, windows, fitted, targets, lever
    )
    gap = {
        "measure": MEASURE,
        "forecast_method": "fitted model (expected value)",
        "quarters": quarters,
        "fiscal_year": {
            "target": _exact(target),
            "actual_to_date": _exact(fytd),
            "forecast_rest_of_year": _money(rest),
            "expected": _money(fytd + rest),
            "gap": _money(target - fytd - rest),
            "expected_range80": [
                _float(float(fytd) + year.p10),
                _float(float(fytd) + year.p90),
            ],
            "expected_range95": [
                _float(float(fytd) + year.p2_5),
                _float(float(fytd) + year.p97_5),
            ],
        },
        "next_twelve_months": next12,
        "lever": fy_lever,
        "lever_next_twelve_months": lever12,
    }
    return gap, [fy_check, check12]


def _next_twelve_months(rec, as_of, windows, fitted, targets, lever):
    """The twelve months after the as-of: a gap against the quarters with a
    target that end inside it, and bookings alone after the last of them."""
    check_name = "twelve-month lever agrees with forward function"
    open_q = [q for q, (qw, _) in targets.items() if qw.end > as_of]
    through = max((targets[q][0].end for q in open_q), default=None)
    # Only months inside a quarter that has a target meet one; a quarter without
    # a target before the last targeted one is bookings alone.
    targeted = [
        w.label for w in windows if any(targets[q][0].contains(w.end) for q in open_q)
    ]
    untargeted = [w.label for w in windows if w.label not in targeted]
    note = (
        f"months outside a targeted quarter (targets end {through}): bookings alone"
        if through is not None
        else "no quarter with a target ends in this window: bookings alone"
    )
    block = {
        "window": [windows[0].label, windows[-1].label] if windows else [],
        "targets_through": through.isoformat() if through else None,
        "quarters": open_q,
        "target": None,
        "actual": None,
        "forecast": None,
        "gap": None,
        "untargeted": {
            "months": untargeted,
            "forecast": None if fitted is None else _money(_shown(fitted, untargeted)),
            "note": note,
        },
    }
    if through is None:
        return (
            block,
            _no_target_lever(),
            Check(check_name, True, f"not applicable: {note}"),
        )
    goal = sum((targets[q][1] for q in open_q), Decimal(0))
    actual = sum((_quarter_actual(rec, targets[q][0]) for q in open_q), Decimal(0))
    block["target"], block["actual"] = _exact(goal), _exact(actual)
    if fitted is None:
        return block, None, None
    forecast = _shown(fitted, targeted)
    block["forecast"] = _money(forecast)
    block["gap"] = _money(goal - actual - forecast)
    result, check = lever(check_name, actual, goal, targeted, through)
    return block, result, check


def _diagnostic(
    cap, model, pop, as_of, windows, horizons, flat: Forecast
) -> dict | None:
    """The capacity projection when it was not adopted: shown once, labelled."""
    projected = model_forecast(model, pop, as_of, windows, creation=cap.projection)
    if not projected.available:
        return None
    return {
        "label": "diagnostic only: capacity was not adopted, so nothing in this report uses it",
        "bookings_with_capacity_projection": {
            h: _money(_shown(projected, ls)) for h, ls in horizons.items()
        },
        "bookings_with_flat_rate": {
            h: _money(_shown(flat, ls)) for h, ls in horizons.items()
        },
        "hiring_action": "unsupported by this history",
    }


def _no_target_lever() -> dict:
    return {
        "lever": "new-business pipeline added",
        "outcome": NO_TARGET,
        "headline": NO_TARGET,
        "reason": "no quarter with a target ends in the next twelve months",
    }


def _lever(check_name, forward, run, target, cap, months, trailing_days, horizons):
    """Solve the pipeline lever through ``forward`` and report what the amount
    books in each window (pipeline added late keeps booking after year end)."""
    result = solve_added_pipeline(forward, target, cap)
    if result.outcome == FEASIBLE:
        ok = abs(result.achieved - target) <= CENT
        detail = f"forward(${result.required:,.2f}) = {result.achieved:.4f} against target {target}"
    elif result.outcome == COVERED:
        ok = result.base >= target
        detail = f"forecast with nothing added {result.base:.2f} >= target {target}"
    else:
        ok = result.achieved < target
        detail = f"forward(cap ${cap:,.2f}) = {result.achieved:.2f} < target {target}"
    amount = {FEASIBLE: result.required, UNREACHABLE: cap}.get(
        result.outcome, Decimal(0)
    )
    without, with_lever = run(Decimal(0)), run(amount)
    lever = {
        "lever": "new-business pipeline added",
        "outcome": result.outcome,
        "headline": result.headline,
        "required": None if result.required is None else _exact(result.required),
        "cap": _money(cap),
        "cap_rule": f"{LEVER_CAP_MULTIPLE} times the new-business pipeline created in the trailing "
        f"{trailing_days} days",
        "schedule": f"added evenly across the {months} months to the target's end"
        if months
        else "no months remain before the target's end",
        "forecast_without_lever": _money(result.base),
        "forecast_with_lever": _money(result.achieved),
        "target": _exact(target),
        "bookings_gained": {
            h: _money(_sum(with_lever, ls) - _sum(without, ls))
            for h, ls in horizons.items()
        },
        "bookings_gained_at": {
            FEASIBLE: "the required amount",
            UNREACHABLE: "the cap",
        }.get(result.outcome, "nothing added"),
        "meaning": "'feasible' means achievable inside the model's bounds (fitted conversion and "
        "timing, the cap above), not operationally achievable",
    }
    if result.outcome == UNREACHABLE and result.required is not None:
        lever["note"] = f"it would take ${result.required:,.2f}, above the cap"
    return lever, Check(check_name, ok, detail)


def _gap_unavailable(rec, profile, as_of, windows, targets, reason):
    """Without a fitted forecast only closed quarters have a gap; open ones and
    the lever say why rather than show a number."""
    quarters = []
    for q, (qw, target) in targets.items():
        actual = _quarter_actual(rec, qw)
        status = _status(qw, as_of)
        closed = status == "closed"
        quarters.append(
            {
                "quarter": q,
                "status": status,
                "target": _exact(target),
                "actual": _exact(actual),
                "forecast": "0.00" if closed else None,
                "expected": _money(actual) if closed else None,
                "gap": _money(target - actual) if closed else None,
                "expected_range80": None,
            }
        )
    target = sum(profile.quarterly_targets.values(), Decimal(0))

    def unavailable(goal):
        return {
            "lever": "new-business pipeline added",
            "outcome": "unavailable",
            "headline": "unavailable",
            "reason": reason,
            "target": None if goal is None else _exact(goal),
            "meaning": "the lever is solved through the fitted model, which is unavailable here",
        }

    next12, _, _ = _next_twelve_months(rec, as_of, windows, None, targets, None)
    gap = {
        "measure": MEASURE,
        "forecast_method": f"fitted model: unavailable ({reason})",
        "quarters": quarters,
        "fiscal_year": {
            "target": _exact(target),
            "actual_to_date": _exact(rec.bookings_fytd),
            "forecast_rest_of_year": None,
            "expected": None,
            "gap": None,
            "expected_range80": None,
            "expected_range95": None,
        },
        "next_twelve_months": next12,
        "lever": unavailable(target),
        "lever_next_twelve_months": unavailable(
            None if next12["target"] is None else Decimal(next12["target"])
        )
        if next12["targets_through"]
        else _no_target_lever(),
    }
    checks = [
        Check("lever agrees with forward function", True, f"not applicable: {reason}"),
        Check(
            "twelve-month lever agrees with forward function", True,
            f"not applicable: {reason}",
        ),
    ]  # fmt: skip
    return gap, checks


def _backtest(bt) -> dict:
    return {
        "scoring": "per horizon, mean absolute dollar error over all folds; 'yes' only if the fitted "
        f"model's error is lower than both baselines at 1 and 3 months; under {MIN_FOLDS} folds is "
        "'not enough history to say'",
        "horizons": [
            {
                "horizon_months": s.horizon,
                "folds": s.folds,
                "mean_absolute_error": {k: _opt_money(v) for k, v in s.mae.items()},
                "signed_bias": {k: _opt_money(v) for k, v in s.bias.items()},
                "range_coverage": {
                    "folds_with_a_range": s.range_folds,
                    "80%": None if s.coverage80 is None else round(s.coverage80, 4),
                    "95%": None if s.coverage95 is None else round(s.coverage95, 4),
                },
            }
            for s in bt.scores
        ],
        "folds": [
            {
                "cutoff": f.cutoff.isoformat(),
                "horizon_months": f.horizon,
                "actual": _exact(f.actual),
                "forecasts": {k: _opt_money(v) for k, v in f.forecasts.items()},
            }
            for f in bt.folds
        ],
        "notes": list(bt.notes),
        "verdict": bt.verdict,
        "reason": bt.verdict_reason,
    }


def _candidate(cmp, incumbent: str, in_use: str) -> dict:
    names = (incumbent, RECENCY)
    return {
        "rule": "adopted only if the fitted model's mean absolute error is lower than the Goal 1 "
        f"fit's at both 1 and 3 months, on the same folds (at least {MIN_FOLDS} at each)",
        "incumbent": names[0],
        "candidate": names[1],
        "mean_absolute_error": {
            f"{h}m": {names[0]: _opt_money(pair[0]), names[1]: _opt_money(pair[1])}
            for h, pair in cmp.mae.items()
        },
        "folds": {f"{h}m": n for h, n in cmp.folds.items()},
        "adopted": cmp.adopted,
        "reason": cmp.reason,
        "fit_in_use": in_use,
    }


# ---------------------------------------------------------------- checks


def _no_windows_check() -> Check:
    return Check(
        "existing pipeline conserved", True, "no months remain in the fiscal year"
    )


def _simulation_check(fitted: Forecast, sim) -> Check:
    if sim is None:
        return Check(
            "simulation centred on the expectation", True,
            f"not applicable: {fitted.unavailable_reason}",
        )  # fmt: skip
    expected = float(fitted.total())
    samples = sim.samples_total
    n = len(samples)
    mean = sum(samples) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in samples) / max(1, n - 1))
    tolerance = 4 * sd / math.sqrt(n) + 0.01
    return Check(
        "simulation centred on the expectation",
        abs(mean - expected) <= tolerance,
        f"simulated mean {mean:,.2f} vs expected {expected:,.2f} (tolerance {tolerance:,.2f}, {n} draws)",
    )


def _components_check(forecasts: list[Forecast], labels) -> Check:
    """Totals by part and by month must agree to well under a cent; exact
    equality is not expected because 28-digit decimals round differently when
    summed in a different order."""
    tolerance = Decimal("0.000001")
    worst = max(
        (
            abs(f.total() - sum((f.window_total(lbl) for lbl in labels), Decimal(0)))
            for f in forecasts
            if f.available
        ),
        default=Decimal(0),
    )
    return Check(
        "forecast parts add up",
        worst <= tolerance,
        f"each method's total equals the sum of its months (largest difference {worst:.2E})",
    )


# ---------------------------------------------------------------- helpers


def _parameters(params: FitParams, draws: int, seed: int) -> list[Rate]:
    def p(name, value, definition):
        return Rate(name, Decimal(value), definition, "", "", "", "", 0, DEFAULT)

    return [
        p(
            "horizon_days",
            params.horizon_days,
            "days within which a win counts for a win rate",
        ),
        p(
            "smoothing_pseudo_observations",
            params.smoothing,
            "pull of an age-group cell toward its stage rate",
        ),
        p(
            "min_timing_samples",
            params.min_timing_samples,
            "wins a stage needs for its own close timing",
        ),
        p("trailing_days", params.trailing_days, "window for trailing rates"),
        p(
            "recency_months",
            params.recency_months,
            "trailing months of snapshots for the cumulative-incidence fit",
        ),
        p(
            "lever_cap_multiple",
            LEVER_CAP_MULTIPLE,
            "cap on added pipeline, times trailing created pipeline",
        ),
        p("simulation_draws", draws, "Monte Carlo draws behind the ranges"),
    ]


def _trailing_created_arr(pop, as_of: date, trailing_days: int) -> Decimal:
    """Pipeline created in the trailing window at each deal's first recorded
    amount (deals with no recorded amount add nothing, so the cap is lower)."""
    start = as_of - timedelta(days=trailing_days)
    amounts = creation_amounts(pop)
    return sum(
        (
            amounts[d.id]
            for d in pop.deals
            if start < d.created <= as_of and amounts[d.id] is not None
        ),
        Decimal(0),
    )


def _month_end(label: str) -> date:
    year, month = (int(x) for x in label.split("-"))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _rate(r: Rate) -> dict:
    return {
        "name": r.name,
        "value": _rate_value(r.value),
        "definition": r.definition,
        "numerator": r.numerator,
        "denominator": r.denominator,
        "cohort": r.cohort,
        "horizon": r.horizon,
        "sample_size": r.sample_size,
        "source": r.source,
        "range95": None if r.low95 is None else [round(r.low95, 4), round(r.high95, 4)],
    }


def _rate_value(v: Decimal) -> str:
    if v == v.to_integral_value():
        return str(v.quantize(Decimal(1)))
    return str(v.quantize(Decimal("0.000001")))


def _check(c: Check) -> dict:
    return {"name": c.name, "passed": c.passed, "detail": c.detail}


def _spread(s) -> dict:
    return {
        "mean": _float(s.mean),
        "median": _float(s.p50),
        "range80": [_float(s.p10), _float(s.p90)],
        "range95": [_float(s.p2_5), _float(s.p97_5)],
    }


def _float(x: float) -> str:
    return f"{x:.2f}"
