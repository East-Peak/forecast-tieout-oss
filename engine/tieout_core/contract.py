"""The contract for report.json: a hand-written, versioned JSON Schema.

It is written from the report's code and rules, not inferred from sample files,
and it is strict: every object lists its keys and refuses others, so a report
that drifts fails a test rather than reaching the app. Each branch the report
can take is its own variant (capacity adopted, not shown or unavailable; with or
without a plan; a forecast unavailable for short history; a missing cost or
target), and "unavailable" is a shape of its own, never a zero.

Money and quantities are decimal strings of a constrained kind (see ``$defs``);
the fields that are free text are ``Text``. Bump ``SCHEMA_VERSION`` whenever the
shape changes; ``report.schema.json`` (committed beside this file) is derived
from this module and a test keeps the two equal.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from .adoption import ADOPTED, NOT_SHOWN, UNAVAILABLE
from .lever import COVERED, FEASIBLE, UNREACHABLE
from .plan import NEXT_12, REST_OF_FY
from .rates import rate_unit

SCHEMA_VERSION = "2.0.0"
SCHEMA_PATH = Path(__file__).with_name("report.schema.json")

# ---------------------------------------------------------------- small builders


def ref(name: str) -> dict:
    return {"$ref": f"#/$defs/{name}"}


def obj(props: dict, optional: tuple[str, ...] = ()) -> dict:
    """A closed object: these keys, all required but ``optional``, no others."""
    return {
        "type": "object",
        "properties": props,
        "required": [k for k in props if k not in optional],
        "additionalProperties": False,
    }


def arr(items: dict, **kw) -> dict:
    return {"type": "array", "items": items, **kw}


def record(value: dict, keys: str | None = None) -> dict:
    """An object whose keys are data (months, segments), every value alike."""
    out: dict = {"type": "object", "additionalProperties": value}
    if keys:
        out["propertyNames"] = {"pattern": keys}
    return out


def maybe(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def pair(item: dict) -> dict:
    return arr(item, minItems=2, maxItems=2)


def const(value) -> dict:
    return {"const": value}


def enum(*values) -> dict:
    return {"enum": list(values)}


def one_of(*variants: dict) -> dict:
    return {"oneOf": list(variants)}


INT = {"type": "integer"}
BOOL = {"type": "boolean"}
NULL = {"type": "null"}
FRACTION = {"type": "number", "minimum": 0, "maximum": 1}
TEXT = ref("Text")
MONEY = ref("Money")
DECIMAL = ref("Decimal")
MONTH = ref("Month")
DATE = ref("Date")
MONEY_OR_NULL = maybe(MONEY)
DECIMAL_OR_NULL = maybe(DECIMAL)
CHECK = ref("Check")
PER_WINDOW = obj(
    {REST_OF_FY: MONEY, NEXT_12: MONEY}
)  # a figure for each of the two windows
SPREAD = obj(
    {
        "mean": MONEY,
        "median": MONEY,
        "range80": ref("MoneyRange"),
        "range95": ref("MoneyRange"),
    }
)
OUTCOME_OF_LEVER = enum(COVERED, FEASIBLE, UNREACHABLE)
CAPACITY_DECISION = enum(ADOPTED, NOT_SHOWN, UNAVAILABLE)
COST_STATUS = enum("entered", "cost not entered")

DEFS: dict = {
    # Free text: prose the report writes for a reader. The browser shows it verbatim.
    "Text": {"type": "string"},
    # Dollars to the cent, e.g. "-1234.50".
    "Money": {"type": "string", "pattern": r"^-?\d+\.\d{2}$"},
    # An exact decimal or a fixed-place quantity, no exponent, e.g. "8000000" or "0.8214".
    "Decimal": {"type": "string", "pattern": r"^-?\d+(\.\d+)?$"},
    "Month": {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
    "Date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "Quarter": {"type": "string", "pattern": r"^Q[1-4]FY\d{2}$"},
    "MoneyRange": pair(MONEY),
    "Check": obj({"name": TEXT, "passed": BOOL, "detail": TEXT}),
}


# ---------------------------------------------------------------- sections


def _inputs() -> dict:
    return obj(
        {
            "identity": obj({"company": TEXT, "scenario": TEXT}),
            "profile": TEXT,
            "data": TEXT,
            "as_of": DATE,
            "fiscal_year": TEXT,
            "fiscal_year_start": DATE,
            "fiscal_year_end": DATE,
            "measure": TEXT,
            "fit": TEXT,
            "ranges": TEXT,
            "simulation": obj({"draws": INT, "seed": INT}),
            "capacity": obj({"decision": CAPACITY_DECISION, "forecast_uses": TEXT}),
        }
    )


def _reconciliation() -> dict:
    count_arr = obj({"count": INT, "arr": DECIMAL})
    return obj(
        {
            "source_rows": INT,
            "source_arr_total": DECIMAL,
            "included_rows": INT,
            "bookings_by_month": record(DECIMAL, DEFS_MONTH_KEY),
            "bookings_fytd": DECIMAL,
            "excluded_motions": record(
                obj({"rows": INT, "arr": DECIMAL, "won_fytd_arr": DECIMAL})
            ),
            "pipeline_flow": obj(
                {
                    "open at fiscal-year start": count_arr,
                    "created": count_arr,
                    "won": count_arr,
                    "lost": count_arr,
                    "open at as-of": count_arr,
                }
            ),
            "exclusions": arr(
                obj(
                    {
                        "row": INT,
                        "deal_id": TEXT,
                        "reason": TEXT,
                        "arr": DECIMAL_OR_NULL,
                    }
                )
            ),
            "checks": arr(CHECK),
        }
    )


def _history() -> dict:
    return obj(
        {
            "facts": obj(
                {
                    "first_deal_created": maybe(DATE),
                    "months_of_history": INT,
                    "new_business_deals": INT,
                    "closed_outcomes": INT,
                    "earliest_close": maybe(DATE),
                    "deal_observations": BOOL,
                    "matured_snapshots": INT,
                    "backtest_folds": record(INT),
                }
            ),
            "limitations": arr(TEXT),
        }
    )


def _method() -> dict:
    """One forecast method: available with its months, or unavailable with its reason."""
    shared = {
        "method": enum("trailing run-rate", "stage-weighted pipeline", "fitted model"),
        "components": record(record(MONEY, DEFS_MONTH_KEY)),
        "assumptions": arr(TEXT),
    }
    available = obj(
        {
            **shared,
            "available": const(True),
            "unavailable_reason": const(""),
            "by_window": record(MONEY, DEFS_MONTH_KEY),
            "horizons": PER_WINDOW,
        }
    )
    unavailable = obj(
        {
            **shared,
            "available": const(False),
            "unavailable_reason": {"type": "string", "minLength": 1},
            "by_window": {"type": "object", "maxProperties": 0},
            "horizons": {"type": "object", "maxProperties": 0},
        }
    )
    return one_of(available, unavailable)


def _forecasts() -> dict:
    cell = obj(
        {
            "horizon_months": INT,
            "folds_with_a_range": INT,
            "coverage80": maybe(FRACTION),
            "coverage95": maybe(FRACTION),
            "median_width80": MONEY_OR_NULL,
            "label": TEXT,
            "coverage_judgment": TEXT,
        }
    )
    horizon_spread = obj({"status": TEXT, **SPREAD["properties"]})
    ranged = obj(
        {
            "status": {"type": "string", "pattern": r"^(?!unavailable: )"},
            "cells": arr(cell),
            "by_window": record(SPREAD, DEFS_MONTH_KEY),
            "horizons": obj({REST_OF_FY: horizon_spread, NEXT_12: horizon_spread}),
        }
    )
    ranges_unavailable = obj(
        {
            "status": {"type": "string", "pattern": r"^unavailable: "},
            "cells": arr(cell),
            "by_window": {"type": "object", "maxProperties": 0},
            "horizons": {"type": "object", "maxProperties": 0},
        }
    )
    return obj(
        {
            "windows": arr(MONTH),
            "horizon_windows": obj({REST_OF_FY: arr(MONTH), NEXT_12: arr(MONTH)}),
            "methods": arr(_method(), minItems=3, maxItems=3),
            "fitted_ranges": one_of(ranged, ranges_unavailable),
        }
    )


def _rates() -> dict:
    return arr(
        obj(
            {
                "name": TEXT,
                "label": maybe(TEXT),
                "unit": enum("share", "dollars", "number"),
                "value": DECIMAL,
                "definition": TEXT,
                "numerator": TEXT,
                "denominator": TEXT,
                "cohort": TEXT,
                "horizon": TEXT,
                "sample_size": INT,
                "source": TEXT,
                "range95": maybe(pair({"type": "number"})),
            }
        )
    )


def _lever() -> dict:
    """The pipeline lever: solved, unavailable with the forecast, or no target."""
    solved = obj(
        {
            "lever": TEXT,
            "outcome": OUTCOME_OF_LEVER,
            "headline": TEXT,
            "required": DECIMAL_OR_NULL,
            "cap": MONEY,
            "cap_rule": TEXT,
            "schedule": TEXT,
            "forecast_without_lever": MONEY,
            "forecast_with_lever": MONEY,
            "target": DECIMAL,
            "bookings_gained": PER_WINDOW,
            "bookings_gained_at": TEXT,
            "meaning": TEXT,
            "note": TEXT,
        },
        optional=("note",),
    )
    unavailable = obj(
        {
            "lever": TEXT,
            "outcome": const("unavailable"),
            "headline": const("unavailable"),
            "reason": TEXT,
            "target": DECIMAL_OR_NULL,
            "meaning": TEXT,
        }
    )
    no_target = obj(
        {
            "lever": TEXT,
            "outcome": const("no target in this window"),
            "headline": TEXT,
            "reason": TEXT,
        }
    )
    return one_of(solved, unavailable, no_target)


def _gap() -> dict:
    status = enum("closed", "in progress", "not started")
    quarter_available = obj(
        {
            "quarter": ref("Quarter"),
            "status": status,
            "target": DECIMAL,
            "actual": DECIMAL,
            "forecast": MONEY,
            "expected": MONEY,
            "gap": MONEY,
            "expected_range80": ref("MoneyRange"),
        }
    )
    quarter_unavailable = obj(
        {
            "quarter": ref("Quarter"),
            "status": status,
            "target": DECIMAL,
            "actual": DECIMAL,
            "forecast": MONEY_OR_NULL,
            "expected": MONEY_OR_NULL,
            "gap": MONEY_OR_NULL,
            "expected_range80": NULL,
        }
    )
    year_available = obj(
        {
            "target": DECIMAL,
            "actual_to_date": DECIMAL,
            "forecast_rest_of_year": MONEY,
            "expected": MONEY,
            "gap": MONEY,
            "expected_range80": ref("MoneyRange"),
            "expected_range95": ref("MoneyRange"),
        }
    )
    year_unavailable = obj(
        {
            "target": DECIMAL,
            "actual_to_date": DECIMAL,
            "forecast_rest_of_year": NULL,
            "expected": NULL,
            "gap": NULL,
            "expected_range80": NULL,
            "expected_range95": NULL,
        }
    )
    untargeted = obj({"months": arr(MONTH), "forecast": MONEY_OR_NULL, "note": TEXT})
    window = arr(MONTH, maxItems=2)
    twelve_targeted = obj(
        {
            "window": window,
            "targets_through": DATE,
            "quarters": arr(ref("Quarter")),
            "target": DECIMAL,
            "actual": DECIMAL,
            "forecast": MONEY_OR_NULL,
            "gap": MONEY_OR_NULL,
            "untargeted": untargeted,
        }
    )
    twelve_untargeted = obj(
        {
            "window": window,
            "targets_through": NULL,
            "quarters": arr(ref("Quarter")),
            "target": NULL,
            "actual": NULL,
            "forecast": NULL,
            "gap": NULL,
            "untargeted": untargeted,
        }
    )
    return obj(
        {
            "measure": TEXT,
            "forecast_method": TEXT,
            "quarters": arr(one_of(quarter_available, quarter_unavailable)),
            "fiscal_year": one_of(year_available, year_unavailable),
            "next_twelve_months": one_of(twelve_targeted, twelve_untargeted),
            "lever": _lever(),
            "lever_next_twelve_months": _lever(),
        }
    )


def _backtest() -> dict:
    by_method = record(MONEY_OR_NULL)
    horizon = obj(
        {
            "horizon_months": INT,
            "folds": INT,
            "mean_absolute_error": by_method,
            "signed_bias": by_method,
            "range_coverage": obj(
                {
                    "folds_with_a_range": INT,
                    "80%": maybe(FRACTION),
                    "95%": maybe(FRACTION),
                }
            ),
        }
    )
    fold = obj(
        {
            "cutoff": DATE,
            "horizon_months": INT,
            "actual": DECIMAL,
            "forecasts": by_method,
        }
    )
    recency = obj(
        {
            "rule": TEXT,
            "incumbent": TEXT,
            "candidate": TEXT,
            "mean_absolute_error": record(by_method),
            "folds": record(INT),
            "adopted": BOOL,
            "reason": TEXT,
            "fit_in_use": TEXT,
        }
    )
    return obj(
        {
            "scoring": TEXT,
            "horizons": arr(horizon),
            "folds": arr(fold),
            "notes": arr(TEXT),
            "verdict": ref("BetterVerdict"),
            "reason": TEXT,
            "candidates": obj({"recency": recency}),
        }
    )


def _verdicts() -> dict:
    return obj(
        {
            "software_correct": obj(
                {
                    "verdict": enum("yes", "no"),
                    "summary": TEXT,
                    "checks": arr(CHECK),
                    "scope": TEXT,
                }
            ),
            "forecast_better_than_baselines": obj(
                {"verdict": ref("BetterVerdict"), "reason": TEXT}
            ),
        }
    )


def _roster_capacity() -> dict:
    decision = obj(
        {
            "outcome": CAPACITY_DECISION,
            "reason": TEXT,
            "scored_on": TEXT,
            "label": TEXT,
            "declared_rule": TEXT,
            "staffing_variation": DECIMAL_OR_NULL,
            "scored_period": maybe(pair(DATE)),
            "horizons": arr(
                obj(
                    {
                        "horizon_months": INT,
                        "folds": INT,
                        "mean_absolute_error_flat": MONEY,
                        "mean_absolute_error_capacity": MONEY,
                        "improvement": DECIMAL,
                    }
                )
            ),
            "forecast_uses": TEXT,
            "association": TEXT,
        }
    )
    roster_unavailable = obj({"unavailable": TEXT, "rows": INT})
    roster = obj(
        {
            "rows": INT,
            "quota_carrying_rows": INT,
            "other_roles_counted_no_capacity": record(INT),
            "excluded": arr(obj({"id": TEXT, "role": TEXT, "reason": TEXT})),
            "heads_at_as_of": INT,
            "ramped_equivalents_at_as_of": DECIMAL_OR_NULL,
            "headcount_target_this_month": maybe(INT),
            "headcount_target_note": TEXT,
            "signed_hires": arr(obj({"id": TEXT, "segment": TEXT, "start": DATE})),
            "departed_to_date": INT,
        }
    )
    ramp = obj(
        {
            "source": TEXT,
            "sample": TEXT,
            "why_not_fitted": TEXT,
            "fitted_through": maybe(TEXT),
            "deals_left_out": obj({"count": INT, "why": maybe(TEXT)}),
            "limitation": maybe(TEXT),
            "weights": arr(
                obj(
                    {
                        "tenure_month": INT,
                        "weight": DECIMAL,
                        # a range, or the words that say the weight is at its ceiling
                        "range95": {"anyOf": [pair(DECIMAL), TEXT, NULL]},
                    }
                )
            ),
            "after": TEXT,
            "definition": TEXT,
        }
    )
    attrition = obj(
        {
            "monthly_rate": DECIMAL,
            "source": TEXT,
            "sample": TEXT,
            "range95": maybe(pair(DECIMAL)),
            "why_not_fitted": TEXT,
            "forward": TEXT,
        }
    )
    creation = obj(
        {
            "deals_per_ramped_ae_month": DECIMAL,
            "trailing_deals": INT,
            "trailing_ramped_ae_months": DECIMAL,
            "window": TEXT,
        }
    )
    past = obj(
        {
            "month": MONTH,
            "kind": const("past"),
            "heads": INT,
            "ramped": DECIMAL,
            "departures": INT,
            "headcount_target": maybe(INT),
            "heads_with_plan": NULL,
        }
    )
    forward = obj(
        {
            "month": MONTH,
            "kind": const("forward"),
            "heads": DECIMAL,
            "ramped": DECIMAL,
            "departures": DECIMAL,
            "headcount_target": maybe(INT),
            "heads_with_plan": DECIMAL_OR_NULL,
        }
    )
    diagnostic = obj(
        {
            "label": TEXT,
            "bookings_with_capacity_projection": PER_WINDOW,
            "bookings_with_flat_rate": PER_WINDOW,
            "hiring_action": TEXT,
        }
    )
    return obj(
        {
            "decision": decision,
            "roster": one_of(roster_unavailable, roster),
            "limitations": arr(TEXT),
            # present when the capacity fit could be made / a projection exists / it was not adopted
            "ramp": ramp,
            "attrition": attrition,
            "creation_rate": creation,
            "months": arr(one_of(past, forward)),
            "diagnostic": diagnostic,
        },
        optional=("ramp", "attrition", "creation_rate", "months", "diagnostic"),
    )


def _quota_productivity() -> dict:
    block = obj(
        {
            "reps": INT,
            "prorated_quota": MONEY,
            "wins_credited": MONEY,
            "attainment": DECIMAL_OR_NULL,
            "spread_across_reps": maybe(
                obj({k: DECIMAL for k in ("min", "p25", "median", "p75", "max")})
            ),
            "spread_reps": INT,
        }
    )
    unavailable = obj({"unavailable": TEXT, "limits": arr(TEXT)})
    available = obj(
        {
            "window": TEXT,
            "definition": TEXT,
            "spread_min_days": INT,
            "by_segment": record(block),
            "all_reps": block,
            "wins_in_window": MONEY,
            "wins_credited": MONEY,
            "wins_unattributed": MONEY,
            "unattributed_note": TEXT,
            "reps_without_quota": INT,
            "total_quota": obj(
                {
                    "annual_quota_of_people_employed_at_as_of": DECIMAL,
                    "fiscal_year_target": DECIMAL,
                    "quota_over_target": DECIMAL_OR_NULL,
                    "people": INT,
                    "note": TEXT,
                }
            ),
            "limits": arr(TEXT),
        }
    )
    return one_of(unavailable, available)


def _required_pipeline() -> dict:
    unavailable = obj({"unavailable": TEXT})
    open_pipeline = obj(
        {
            "open_arr": MONEY,
            "expected_contribution": MONEY,
            "needed_contribution": MONEY,
            "expected_share_of_open": DECIMAL_OR_NULL,
            "needed_share_of_open": DECIMAL_OR_NULL,
            "possible": BOOL,
            "statement": TEXT,
        }
    )
    quarter = obj(
        {
            "quarter": ref("Quarter"),
            "in_fiscal_year": BOOL,
            "status": enum("closed", "in progress", "not started"),
            "target": DECIMAL,
            "actual": DECIMAL,
            "outcome": OUTCOME_OF_LEVER,
            "headline": TEXT,
            "required_extra_pipeline": MONEY_OR_NULL,
            "bookings_without_own_pipeline": MONEY,
            "bookings_with_own_pipeline": MONEY,
            "bookings_under_completed_schedule": MONEY_OR_NULL,
            "surplus_over_target": MONEY_OR_NULL,
            "surplus_statement": maybe(TEXT),
            "created_between": pair(DATE),
            "expected_created_pipeline": MONEY,
            "earlier_assigned_in_span": MONEY,
            "total_created_in_span": MONEY_OR_NULL,
            "total_created_note": maybe(TEXT),
            "would_take": MONEY_OR_NULL,
            "ramped_ae_months": DECIMAL_OR_NULL,
            "per_day": obj(
                {
                    "expected": MONEY_OR_NULL,
                    "required_total": MONEY_OR_NULL,
                    "required_against_team_best": DECIMAL_OR_NULL,
                    "note": maybe(TEXT),
                }
            ),
            "per_ramped_ae_month": obj(
                {
                    "expected": MONEY_OR_NULL,
                    "required_total": MONEY_OR_NULL,
                    "required_against_team_best": DECIMAL_OR_NULL,
                    "note": maybe(TEXT),
                    "decides": BOOL,
                }
            ),
            "cap_left_before": MONEY,
            "cents_booked_in_quarter_per_dollar": DECIMAL,
            "too_late": obj(
                {
                    "applies": BOOL,
                    "label": maybe(TEXT),
                    "legs": arr(TEXT),
                    "reasons": arr(TEXT),
                    "diagnostics": arr(TEXT),
                    "open_pipeline": maybe(open_pipeline),
                }
            ),
        }
    )
    fiscal_year = obj(
        {
            "name": TEXT,
            "too_late_quarters": arr(ref("Quarter")),
            "solvable_total": MONEY_OR_NULL,
            "solvable_quarters": arr(ref("Quarter")),
            "unreachable_quarters": arr(ref("Quarter")),
            "quarters_remaining": INT,
            "headline": TEXT,
            "single_spread": obj(
                {
                    "name": TEXT,
                    "headline": maybe(TEXT),
                    "outcome": maybe(TEXT),
                    "required": DECIMAL_OR_NULL,
                }
            ),
            "why_they_differ": TEXT,
        }
    )
    lead_time = obj(
        {
            "question": TEXT,
            "basis": TEXT,
            "created_between": pair(DATE),
            "quarters": arr(
                obj(
                    {
                        "quarter": TEXT,
                        "cents_booked_in_quarter": DECIMAL,
                        "cents_booked_by_quarter_end": DECIMAL,
                    }
                )
            ),
            "cents_booked_later": DECIMAL,
            "count_outcome": obj(
                {"meaning": TEXT, "win_within_horizon": DECIMAL, "do_not_win": DECIMAL}
            ),
        }
    )
    history = obj(
        {
            "unit": TEXT,
            "quarters": INT,
            "median": MONEY_OR_NULL,
            "best_four_quarter_average": MONEY_OR_NULL,
            "best_four_quarter_average_per_day": MONEY_OR_NULL,
            "per_day_unit": TEXT,
            "note": TEXT,
        }
    )
    available = obj(
        {
            "method": TEXT,
            "forward_function": TEXT,
            "cap": MONEY,
            "cap_rule": TEXT,
            "quarters": arr(quarter),
            "fiscal_year": fiscal_year,
            "per_rep_rule": obj({"applies": BOOL, "why": TEXT}),
            "too_late_rule": TEXT,
            "lead_time": lead_time,
            "per_ramped_ae_month_label": TEXT,
            "team_history": history,
            "meaning": TEXT,
            "expected_basis": TEXT,
        }
    )
    return one_of(unavailable, available)


def _plan() -> dict:
    cost = {
        "cash_cost_in_twelve_months": MONEY_OR_NULL,
        "cash_cost_total": MONEY_OR_NULL,
    }
    hires_valued = obj(
        {"kind": const("hires"), "label": TEXT, "detail": TEXT, "valued": const(True),
         "contribution": PER_WINDOW, **cost}
    )  # fmt: skip
    hires_not_valued = obj(
        {"kind": const("hires"), "label": TEXT, "detail": TEXT, "valued": const(False),
         "note": TEXT, "contribution": NULL, **cost}
    )  # fmt: skip
    program = obj(
        {"kind": const("program"), "label": TEXT, "detail": TEXT, "valued": const(True),
         "contribution": PER_WINDOW, **cost, "payment_schedule": TEXT}
    )  # fmt: skip
    twelve = obj(
        {
            "target": DECIMAL,
            "actual_to_date": DECIMAL,
            "baseline_gap": MONEY,
            "gap_with_plan": MONEY,
            "forecast_with_plan": MONEY,
            "note": TEXT,
        }
    )
    plan_quarter = obj(
        {
            "quarter": ref("Quarter"),
            "status": enum("closed", "in progress", "not started"),
            "target": DECIMAL,
            "actual": DECIMAL,
            "forecast": MONEY,
            "expected": MONEY,
            "gap": MONEY,
            "expected_range80": ref("MoneyRange"),
        }
    )
    full = obj(
        {
            "file": TEXT,
            "order": TEXT,
            "baseline_definition": TEXT,
            "items": arr(one_of(hires_valued, hires_not_valued, program)),
            "baseline": PER_WINDOW,
            "with_plan": PER_WINDOW,
            "difference": PER_WINDOW,
            "contributions_total": PER_WINDOW,
            # 1.1.0: the with-plan figures a screen shows, by month, by quarter and for the year
            "with_plan_by_window": record(MONEY, DEFS_MONTH_KEY),
            "expected_fiscal_year": MONEY,
            "with_plan_quarters": arr(plan_quarter),
            "gap": obj(
                {
                    "fiscal_year": obj(
                        {
                            "target": DECIMAL,
                            "actual_to_date": DECIMAL,
                            "baseline_gap": MONEY,
                            "gap_with_plan": MONEY,
                        }
                    ),
                    "next_twelve_months": maybe(twelve),
                }
            ),
            "cash_cost_in_twelve_months": MONEY_OR_NULL,
            "cost_note": TEXT,
            "ranges": obj(
                {
                    "status": TEXT,
                    "bookings_in_window": obj(
                        {
                            w: obj(
                                {
                                    "median": MONEY,
                                    "range80": ref("MoneyRange"),
                                    "range95": ref("MoneyRange"),
                                }
                            )
                            for w in (REST_OF_FY, NEXT_12)
                        }
                    ),
                    "fiscal_year_expected_range80": ref("MoneyRange"),
                    "fiscal_year_expected_range95": ref("MoneyRange"),
                    "by_window": record(SPREAD, DEFS_MONTH_KEY),
                    "draws": INT,
                    "what_is_drawn": TEXT,
                }
            ),
        }
    )
    return one_of(obj({"unavailable": TEXT}), full)


def _actions() -> dict:
    valued = obj(
        {
            "action": TEXT,
            "kind": enum("hire", "program"),
            "not_ranked_because": maybe(const("cost not entered")),
            "status": const("valued"),
            "bookings_gained": PER_WINDOW,
            "starts_paying": maybe(MONTH),
            "cash_cost_in_twelve_months": MONEY_OR_NULL,
            "cost_status": COST_STATUS,
            "gain_per_dollar": DECIMAL_OR_NULL,
            "rank": maybe(INT),
        }
    )
    not_valued = obj(
        {
            "action": TEXT,
            "kind": enum("hire", "program"),
            "not_ranked_because": TEXT,
            "status": {"type": "string", "pattern": r"^(?!valued$)"},
            "bookings_gained": NULL,
            "starts_paying": NULL,
            "cash_cost_in_twelve_months": NULL,
            "gain_per_dollar": NULL,
            "rank": NULL,
        }
    )
    hires_solved = obj(
        {
            "outcome": enum("already covered", "feasible", "unreachable"),
            "count": maybe(INT),
            "overshoot": MONEY_OR_NULL,
            "fiscal_year_bookings_with": MONEY,
            "fiscal_year_bookings_one_fewer": MONEY_OR_NULL,
            "bound": INT,
            "bound_basis": TEXT,
            "cash_cost_in_twelve_months": MONEY_OR_NULL,
            "cost_status": COST_STATUS,
            "cash_cost_note": maybe(TEXT),
        }
    )
    hires_not_valued = obj({"outcome": TEXT, "count": NULL, "note": TEXT})
    program = obj(
        {
            "outcome": enum("already covered", "feasible", "unreachable"),
            "dollars": MONEY_OR_NULL,
            "needed_but_over_the_cap": MONEY_OR_NULL,
            "cap": MONEY,
            "cap_rule": TEXT,
            "fiscal_year_bookings_with": MONEY,
            "overshoot": MONEY_OR_NULL,
            "share_booking_in_fiscal_year": DECIMAL_OR_NULL,
            "cash_cost_in_twelve_months": MONEY_OR_NULL,
            "cost_status": COST_STATUS,
            "cash_cost_note": maybe(TEXT),
        }
    )
    full = obj(
        {
            "definition": TEXT,
            "program_shape": TEXT,
            "comparison": arr(one_of(valued, not_valued)),
            "close_the_fiscal_year_gap": obj(
                {
                    "fiscal_year_gap": MONEY,
                    "basis": TEXT,
                    "hires": one_of(hires_solved, hires_not_valued),
                    "program": program,
                }
            ),
            "meaning": TEXT,
        }
    )
    return one_of(obj({"unavailable": TEXT}), full)


DEFS_MONTH_KEY = r"^\d{4}-(0[1-9]|1[0-2])$"

DEFS["BetterVerdict"] = enum("yes", "no", "not enough history to say")


def _fitted_forecast_unavailable_together() -> dict:
    """When the fitted forecast is unavailable, everything solved through it is too:
    the ranges, the gap, the requirement, the plan and the actions. When it is
    available none of them may say otherwise."""
    fitted_unavailable = {
        "properties": {
            "forecasts": {
                "properties": {
                    "methods": {
                        "contains": {
                            "properties": {
                                "method": const("fitted model"),
                                "available": const(False),
                            },
                            "required": ["method", "available"],
                        }
                    }
                },
                "required": ["methods"],
            }
        },
        "required": ["forecasts"],
    }
    says_unavailable = {"required": ["unavailable"]}
    return {
        "if": fitted_unavailable,
        "then": {
            "properties": {
                "actions": says_unavailable,
                "required_pipeline": says_unavailable,
                "plan": says_unavailable,
                "gap": {
                    "properties": {"fiscal_year": {"properties": {"expected": NULL}}}
                },
                "forecasts": {
                    "properties": {
                        "fitted_ranges": {
                            "properties": {"status": {"pattern": "^unavailable: "}}
                        }
                    }
                },
            }
        },
        "else": {
            "properties": {
                "actions": {"not": says_unavailable},
                "required_pipeline": {"not": says_unavailable},
                "plan": {"not": says_unavailable},
                "gap": {
                    "properties": {"fiscal_year": {"properties": {"expected": MONEY}}}
                },
            }
        },
    }


def schema() -> dict:
    """The JSON Schema (draft 2020-12) for report.json at ``SCHEMA_VERSION``."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://forecast-tieout.example/schema/report-{SCHEMA_VERSION}.json",
        "title": "TieoutReport",
        "description": "report.json written by `python -m engine.tieout_core report`.",
        "type": "object",
        "properties": {
            "inputs": _inputs(),
            "reconciliation": _reconciliation(),
            "history": _history(),
            "forecasts": _forecasts(),
            "rates": _rates(),
            "gap": _gap(),
            "backtest": _backtest(),
            "verdicts": _verdicts(),
            "roster_capacity": _roster_capacity(),
            "quota_productivity": _quota_productivity(),
            "required_pipeline": _required_pipeline(),
            # present only when a plan file was given
            "plan": _plan(),
            "actions": _actions(),
            "schema_version": const(SCHEMA_VERSION),
        },
        "required": [
            "inputs",
            "reconciliation",
            "history",
            "forecasts",
            "rates",
            "gap",
            "backtest",
            "verdicts",
            "roster_capacity",
            "quota_productivity",
            "required_pipeline",
            "actions",
            "schema_version",
        ],
        "additionalProperties": False,
        "allOf": [_fitted_forecast_unavailable_together()],
        "$defs": DEFS,
    }


def schema_text() -> str:
    """The committed form: stable key order, two-space indent, trailing newline."""
    return json.dumps(schema(), indent=2, sort_keys=True) + "\n"


def validator() -> Draft202012Validator:
    return Draft202012Validator(schema())


# ---------------------------------------------------------------- cross-field rules

METHOD_NAMES = ("trailing run-rate", "stage-weighted pipeline", "fitted model")


def validate(report: dict) -> list[str]:
    """Every problem with ``report``: the schema's, then the rules a schema cannot say
    (one of each method, month completeness, availability agreeing across sections,
    the capacity outcome's payload). Empty when the report satisfies the contract."""
    found = [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}"
        for e in validator().iter_errors(report)
    ]
    return found or _cross_rules(report)


def _cross_rules(r: dict) -> list[str]:
    found: list[str] = []

    def rule(ok: bool, message: str) -> None:
        if not ok:
            found.append(message)

    f = r["forecasts"]
    windows = f["windows"]
    names = sorted(m["method"] for m in f["methods"])
    rule(
        names == sorted(METHOD_NAMES),
        f"forecasts.methods must hold each method once, not {names}",
    )
    for m in f["methods"]:
        if m["available"]:
            rule(
                list(m["by_window"]) == windows,
                f"{m['method']} is available but its months are not the report's windows",
            )
    fit = next((m for m in f["methods"] if m["method"] == "fitted model"), None)
    fa = bool(fit and fit["available"])
    ranges = f["fitted_ranges"]
    if fa:
        rule(
            list(ranges["by_window"]) == windows,
            "fitted ranges must cover every window",
        )
        rule(
            bool(ranges["horizons"]),
            "an available fitted forecast needs its horizon ranges",
        )
    else:
        rule(
            not ranges["by_window"] and not ranges["horizons"],
            "an unavailable fitted forecast has no ranges",
        )

    gap = r["gap"]
    for q in gap["quarters"]:
        open_quarter = q["status"] != "closed"
        if fa:
            rule(
                all(
                    q[k] is not None
                    for k in ("forecast", "expected", "gap", "expected_range80")
                ),
                f"{q['quarter']}: the fitted forecast is available, so the quarter needs its figures and range",
            )
        elif open_quarter:
            rule(
                all(
                    q[k] is None
                    for k in ("forecast", "expected", "gap", "expected_range80")
                ),
                f"{q['quarter']}: the fitted forecast is unavailable, so an open quarter carries no figure",
            )
    year = gap["fiscal_year"]
    year_keys = (
        "forecast_rest_of_year",
        "expected",
        "gap",
        "expected_range80",
        "expected_range95",
    )
    rule(
        all((year[k] is not None) == fa for k in year_keys),
        "the fiscal year's figures are present exactly when the fitted forecast is available",
    )
    nxt = gap["next_twelve_months"]
    rule(
        (nxt["untargeted"]["forecast"] is not None) == fa,
        "the twelve months' untargeted forecast is present exactly when the fitted forecast is available",
    )
    if nxt["targets_through"] is not None:
        rule(
            all((nxt[k] is not None) == fa for k in ("forecast", "gap")),
            "the twelve months' forecast and gap are present exactly when the fitted forecast is available",
        )
    for lever in (gap["lever"], gap["lever_next_twelve_months"]):
        rule(
            (lever["outcome"] != "unavailable") or not fa,
            "a lever cannot be unavailable while the fitted forecast is available",
        )
    rule(
        (gap["lever"]["outcome"] == "unavailable") == (not fa),
        "the fiscal-year lever is unavailable exactly when the fitted forecast is",
    )

    plan = r.get("plan")
    if plan is not None and "unavailable" not in plan:
        rule(
            list(plan["with_plan_by_window"]) == windows,
            "plan figures must cover every window",
        )
        rule(
            list(plan["ranges"]["by_window"]) == windows,
            "plan ranges must cover every window",
        )
        rule(
            [q["quarter"] for q in plan["with_plan_quarters"]]
            == [q["quarter"] for q in gap["quarters"]],
            "plan quarters must be the report's quarters",
        )

    decision = r["roster_capacity"]["decision"]
    outcome = decision["outcome"]
    rc = r["roster_capacity"]
    rule(
        r["inputs"]["capacity"]["decision"] == outcome,
        "inputs.capacity.decision disagrees with the decision's outcome",
    )
    adopted = outcome == "adopted"
    rule(
        r["inputs"]["capacity"]["forecast_uses"].startswith("capacity term") == adopted,
        "inputs.capacity.forecast_uses disagrees with the outcome",
    )
    rule(
        decision["forecast_uses"].startswith("the capacity term") == adopted,
        "the decision's forecast_uses disagrees with the outcome",
    )
    fitted_parts = [k in rc for k in ("ramp", "attrition", "creation_rate")]
    rule(
        all(fitted_parts) or not any(fitted_parts),
        "ramp, attrition and creation_rate come together",
    )
    rule(
        ("months" in rc) == all(fitted_parts),
        "the roster's months are present exactly when the capacity fit is",
    )
    if adopted:
        rule(
            all(fitted_parts) and "months" in rc,
            "an adopted report carries the ramp, attrition, creation rate and months",
        )
        rule("diagnostic" not in rc, "an adopted report has no diagnostic")
    if "diagnostic" in rc:
        rule(
            not adopted and all(fitted_parts),
            "a diagnostic belongs to a fitted capacity that was not adopted",
        )
    rule(
        r["required_pipeline"].get("per_rep_rule", {}).get("applies", adopted)
        == adopted,
        "the per-rep rule applies exactly when capacity is adopted",
    )
    if plan is not None and "unavailable" not in plan:
        for item in plan["items"]:
            if item["kind"] == "hires":
                rule(
                    item["valued"] == adopted,
                    "hires are valued exactly when capacity is adopted",
                )
    for rate in r["rates"]:
        try:
            unit = rate_unit(rate["name"])
        except KeyError:
            rule(False, f"rate '{rate['name']}' has no unit declared")
            continue
        rule(
            rate["unit"] == unit,
            f"rate '{rate['name']}' says its unit is {rate['unit']}, the name's unit is {unit}",
        )
        rule(
            rate["range95"] is None or rate["unit"] == "share",
            f"rate '{rate['name']}' carries a range but is not a share",
        )
    required = r["required_pipeline"]
    for q in required.get("quarters", []):
        surplus, said = q["surplus_over_target"], q["surplus_statement"]
        where = f"required_pipeline quarter {q['quarter']}"
        rule(
            (surplus is None) == (said is None),
            f"{where}: the surplus and its statement are present together",
        )
        rule(
            (q["total_created_in_span"] is None)
            == (q["total_created_note"] is not None),
            f"{where}: the total created and its note are present together",
        )
        for part in ("per_day", "per_ramped_ae_month"):
            p = q[part]
            missing = (
                p["required_total"] is None or p["required_against_team_best"] is None
            )
            rule(
                missing == (p["note"] is not None),
                f"{where}: {part} has a note exactly when one of its figures is missing",
            )
        if surplus is not None and said is not None:
            sign = Decimal(surplus)
            start = (
                "ahead of"
                if sign > 0
                else "still short of"
                if sign < 0
                else "exactly on"
            )
            rule(
                said.startswith(start),
                f"{where}: the surplus statement does not agree in sign with the surplus {surplus}",
            )
    actions = r["actions"]
    if "unavailable" not in actions:
        closing = actions["close_the_fiscal_year_gap"]
        for kind, part in (
            ("hires", closing["hires"]),
            ("program", closing["program"]),
        ):
            if "cash_cost_note" in part:
                rule(
                    (part["cash_cost_in_twelve_months"] is None)
                    == (part["cash_cost_note"] is not None),
                    f"the {kind} cost and its note are present together",
                )
        hires = actions["close_the_fiscal_year_gap"]["hires"]
        rule(
            ("bound" in hires) == adopted,
            "the hires solve is present exactly when capacity is adopted",
        )
        for row in actions["comparison"]:
            if row["kind"] == "hire":
                rule(
                    (row["status"] == "valued") == adopted,
                    "the hire action is valued exactly when capacity is adopted",
                )
    return found
