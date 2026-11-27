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
from datetime import date
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from . import stretch_report
from . import stretch_rules as sr
from .adoption import ADOPTED, NOT_SHOWN, UNAVAILABLE
from .backtest import BASELINE_LOWER, BASELINES, MODEL_LOWER, TIE, VERDICT_HORIZONS
from .fiscal import add_months, month_end
from .lever import COVERED, FEASIBLE, UNREACHABLE
from .plan import NEXT_12, REST_OF_FY
from .rates import rate_unit
from .stretch import horizon_for
from .stretch_rules import HORIZONS

SCHEMA_VERSION = "2.4.0"
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
    # what stands behind a stretched range (null when it is not stretched)
    "RangeBasis": obj(
        {
            "factor_horizon_months": enum(1, 3, 6),
            "held": INT,
            "scored": INT,
            "stretched_side": enum("lower", "upper", "both", "neither"),
            "window_start": DATE,
            "window_end": DATE,
            "extrapolated": BOOL,
            "extrapolated_because": maybe(
                enum("longer_than_six_months", "not_the_tested_shape")
            ),
            "floored_at_zero_80": BOOL,
            "floored_at_zero_95": BOOL,
        }
    ),
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
    # the label beside each range: stretched by past misses (adopted) or simulated with its
    # back-test label; the 95% range is "not separately tested" either way
    horizon_spread = obj(
        {
            "status": TEXT,
            # a short label (cards, opened rows) and a full one (the line on how far to trust
            # the ranges), both built from the basis; the 95% range's label is short
            "label_short": TEXT,
            "label95": TEXT,
            "label_full": TEXT,
            "basis": maybe(ref("RangeBasis")),
            **SPREAD["properties"],
        }
    )
    ranged = obj(
        {
            "status": {"type": "string", "pattern": r"^(?!unavailable: )"},
            "cells": arr(cell),
            "by_window_label": TEXT,
            "by_window": record(SPREAD, DEFS_MONTH_KEY),
            "horizons": obj({REST_OF_FY: horizon_spread, NEXT_12: horizon_spread}),
        }
    )
    ranges_unavailable = obj(
        {
            "status": {"type": "string", "pattern": r"^unavailable: "},
            "cells": arr(cell),
            "by_window_label": TEXT,
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
            "label_short": TEXT,
            "range_basis": maybe(ref("RangeBasis")),
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
            "label_short": TEXT,
            "label95": TEXT,
            "range_basis": maybe(ref("RangeBasis")),
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


def _stretch_decision() -> dict:
    """Goal 2D: whether the simulated ranges are stretched by past misses, with the
    back-test evidence behind it, one row per tested horizon."""
    horizon = obj(
        {
            "horizon_months": enum(*HORIZONS),
            "eligible_folds": INT,
            "factors_learned": BOOL,
            "scored_folds": INT,
            "inside_simulated": INT,
            "inside_stretched": INT,
            "coverage_simulated": maybe(FRACTION),
            "coverage_stretched": maybe(FRACTION),
            "median_width80_simulated": MONEY_OR_NULL,
            "median_width80_stretched": MONEY_OR_NULL,
            # null when a side has no width to stretch
            "lower_factor": DECIMAL_OR_NULL,
            "upper_factor": DECIMAL_OR_NULL,
            # the reason a factor is null, and nothing otherwise
            "lower_reason": maybe(TEXT),
            "upper_reason": maybe(TEXT),
            # every scored past date, with where the actual fell and the factors used then
            "scored_dates": arr(
                obj(
                    {
                        "cutoff": DATE,
                        "inside_simulated": BOOL,
                        "inside_stretched": BOOL,
                        "lower_factor": DECIMAL_OR_NULL,
                        "upper_factor": DECIMAL_OR_NULL,
                    }
                )
            ),
        }
    )
    acceptance = obj(
        {
            "stretched_side": enum("lower", "upper", "both", "neither"),
            "one_sided": BOOL,
            "two_sided_coverage": FRACTION,
            "six_month_eligible_folds": INT,
            "six_month_scored_folds": INT,
            "floored_at_zero": arr(TEXT),
            "sentence": TEXT,
        }
    )
    return obj(
        {
            "rule": TEXT,
            "method": TEXT,
            "acceptance": maybe(acceptance),
            "decision": enum(sr.ADOPTED, sr.NOT_ADOPTED, sr.NOT_ENOUGH_HISTORY),
            "reason": TEXT,
            "pooled": maybe(
                obj(
                    {
                        "scored_folds": INT,
                        "coverage_simulated": FRACTION,
                        "coverage_stretched": FRACTION,
                    }
                )
            ),
            "horizons": arr(horizon, minItems=len(HORIZONS), maxItems=len(HORIZONS)),
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
            # whether the actual fell inside the simulated 80% range; null without a range
            "inside80": maybe(BOOL),
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
            "candidates": obj({"recency": recency, "ranges": _stretch_decision()}),
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
                {
                    "verdict": ref("BetterVerdict"),
                    "reason": TEXT,
                    # the reason in words with no figures, and the evidence behind the verdict:
                    # each verdict horizon's errors with which is lower (empty when the verdict
                    # is 'not enough history to say')
                    "in_words": TEXT,
                    "comparisons": arr(ref("HorizonComparison")),
                }
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
DEFS["ComparisonOutcome"] = enum(MODEL_LOWER, BASELINE_LOWER, TIE)
_AGAINST_A_BASELINE = obj(
    {"baseline_error": MONEY, "outcome": ref("ComparisonOutcome")}
)
DEFS["HorizonComparison"] = obj(
    {
        "horizon_months": INT,
        "model_error": MONEY,
        "against": obj({m: _AGAINST_A_BASELINE for m in BASELINES}),
    }
)


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


def _better_than_baselines_rules(r: dict, rule) -> None:
    """The verdict's comparisons are the back-test table's figures, each outcome is what
    the two errors say, and the verdict is what the outcomes say."""
    v = r["verdicts"]["forecast_better_than_baselines"]
    cs = v["comparisons"]
    rule(
        [c["horizon_months"] for c in cs] in ([], list(VERDICT_HORIZONS)),
        f"the verdict's comparisons are at the verdict horizons {list(VERDICT_HORIZONS)} or absent",
    )
    rule(
        bool(cs) == (v["verdict"] != "not enough history to say"),
        "the verdict's comparisons are present exactly when the verdict is not 'not enough history to say'",
    )
    table = {
        h["horizon_months"]: h["mean_absolute_error"] for h in r["backtest"]["horizons"]
    }
    for c in cs:
        errors_at = table.get(c["horizon_months"], {})
        rule(
            c["model_error"] == errors_at.get("fitted model"),
            f"{c['horizon_months']}m: the model's error is not the back-test table's",
        )
        for method, a in c["against"].items():
            rule(
                a["baseline_error"] == errors_at.get(method),
                f"{c['horizon_months']}m: the {method} error is not the back-test table's",
            )
            model, base = Decimal(c["model_error"]), Decimal(a["baseline_error"])
            # the table is rounded to the cent: equal figures may be a tie or a smaller difference
            rule(
                not model < base or a["outcome"] == MODEL_LOWER,
                f"{c['horizon_months']}m: the model's error is lower than {method}'s, which the outcome does not say",
            )
            rule(
                not model > base or a["outcome"] == BASELINE_LOWER,
                f"{c['horizon_months']}m: {method}'s error is lower than the model's, which the outcome does not say",
            )
    if cs:
        all_lower = all(
            a["outcome"] == MODEL_LOWER for c in cs for a in c["against"].values()
        )
        rule(
            (v["verdict"] == "yes") == all_lower,
            "the verdict is 'yes' exactly when the model's error is lower than both baselines at every verdict horizon",
        )


def _stretch_rules(r: dict, rule) -> None:
    """The stretch's evidence agrees with the back-test, its decision with the declared rule
    run on that evidence, and every label with the decision."""
    c = r["backtest"]["candidates"]["ranges"]
    cells = {x["horizon_months"]: x for x in r["forecasts"]["fitted_ranges"]["cells"]}
    rows = c["horizons"]
    rule(
        [h["horizon_months"] for h in rows] == list(HORIZONS),
        "the stretch evidence has one row per tested horizon, in order",
    )
    for h in rows:
        m, where = h["horizon_months"], f"stretch evidence at {h['horizon_months']}m"
        scored = h["scored_folds"]
        for side in ("lower_factor", "upper_factor"):
            rule(
                h[side] is None or Decimal(h[side]) >= 1,
                f"{where}: the {side.replace('_', ' ')} is below 1",
            )
        rule(
            h["factors_learned"] == (h["eligible_folds"] >= sr.MIN_ELIGIBLE_FOLDS),
            f"{where}: the factors are learned exactly from {sr.MIN_ELIGIBLE_FOLDS} eligible folds",
        )
        rule(
            h["factors_learned"]
            or (h["lower_factor"], h["upper_factor"]) == ("1.0000", "1.0000"),
            f"{where}: factors that were not learned must stay at 1",
        )
        rule(
            h["inside_simulated"] <= scored and h["inside_stretched"] <= scored,
            f"{where}: more folds inside than were scored",
        )
        for which in ("simulated", "stretched"):
            expected = round(h[f"inside_{which}"] / scored, 4) if scored else None
            rule(
                h[f"coverage_{which}"] == expected,
                f"{where}: the {which} coverage is not the folds inside over the folds scored",
            )
        rule(
            (h["median_width80_simulated"] is not None) == (scored > 0)
            and (h["median_width80_stretched"] is not None) == (scored > 0),
            f"{where}: the median widths are present exactly when folds were scored",
        )
        if scored:
            rule(
                Decimal(h["median_width80_stretched"])
                >= Decimal(h["median_width80_simulated"]),
                f"{where}: stretching by factors of at least 1 cannot narrow the median range",
            )
        for side in ("lower", "upper"):
            rule(
                (h[f"{side}_factor"] is None) == (h[f"{side}_reason"] is not None),
                f"{where}: the {side} factor is absent exactly when its reason is given",
            )
        _scored_dates_rules(r, h, rule, where)
        cell = cells.get(m)
        if cell is not None:
            rule(
                h["eligible_folds"] == cell["folds_with_a_range"],
                f"{where}: the eligible folds are not the back-test's folds with a range",
            )
            rule(
                scored <= cell["folds_with_a_range"],
                f"{where}: more folds scored than the back-test has",
            )
            if scored and scored == cell["folds_with_a_range"]:
                rule(
                    h["coverage_simulated"] == cell["coverage80"],
                    f"{where}: the simulated coverage is not the back-test's",
                )
    counts = [
        sr.Counts(
            h["horizon_months"],
            h["scored_folds"],
            h["inside_simulated"],
            h["inside_stretched"],
        )
        for h in rows
    ]
    decided = sr.decide(counts)
    rule(
        c["decision"] == decided.outcome,
        "the stretch decision is not what the declared rule gives on its own evidence",
    )
    rule(c["reason"] == decided.reason, "the stretch reason is not the declared rule's")
    rule(
        (c["pooled"] is None) == (decided.pooled is None),
        "the pooled coverage is present exactly when there is enough history to compare",
    )
    if c["pooled"] is not None and decided.pooled is not None:
        rule(
            c["pooled"]["scored_folds"]
            == sum(
                h["scored_folds"]
                for h in rows
                if h["horizon_months"] in sr.SCORED_HORIZONS
            )
            and c["pooled"]["coverage_simulated"] == round(float(decided.pooled[0]), 4)
            and c["pooled"]["coverage_stretched"] == round(float(decided.pooled[1]), 4),
            "the pooled coverage is not the sum of the horizons' folds",
        )
    ranges = r["forecasts"]["fitted_ranges"]
    adopted = decided.outcome == sr.ADOPTED
    by_h = {h["horizon_months"]: h for h in rows}
    six = by_h[6]
    rule(
        c["method"]
        == stretch_report.method_text(six["eligible_folds"], six["scored_folds"]),
        "the method text is not the declared rule's, with this report's six-month fold counts",
    )
    rule(
        (c["acceptance"] is not None) == adopted,
        "what the rule accepted is stated exactly when the stretch is adopted",
    )
    if not ranges["by_window"]:
        return
    _label_rules(r, c, ranges, by_h, adopted, rule)


def _scored_dates_rules(r: dict, h: dict, rule, where: str) -> None:
    """The scored dates are every back-test fold at this horizon with five eligible folds
    before it, each with the back-test's own outcome for the simulated range."""
    m = h["horizon_months"]
    folds = [f for f in r["backtest"]["folds"] if f["horizon_months"] == m]
    ranged = {f["cutoff"]: f for f in folds if f["inside80"] is not None}

    def ended_by(earlier: str, cutoff: str) -> bool:
        return add_months(date.fromisoformat(earlier), m) <= date.fromisoformat(cutoff)

    should = sorted(
        c
        for c in ranged
        if sum(ended_by(o, c) for o in ranged) >= sr.MIN_ELIGIBLE_FOLDS
    )
    dates = h["scored_dates"]
    rule(
        len(dates) == h["scored_folds"],
        f"{where}: the scored dates are not as many as the scored folds",
    )
    rule(
        [d["cutoff"] for d in dates] == should,
        f"{where}: the scored dates are not exactly the back-test folds with enough earlier folds",
    )
    for d in dates:
        fold = ranged.get(d["cutoff"])
        rule(
            fold is not None and fold["inside80"] == d["inside_simulated"],
            f"{where}: {d['cutoff']} disagrees with the back-test on whether the simulated range held",
        )
        for side in ("lower_factor", "upper_factor"):
            rule(
                d[side] is None or Decimal(d[side]) >= 1,
                f"{where}: {d['cutoff']} used a {side.replace('_', ' ')} below 1",
            )
    rule(
        sum(d["inside_simulated"] for d in dates) == h["inside_simulated"]
        and sum(d["inside_stretched"] for d in dates) == h["inside_stretched"],
        f"{where}: the counts are not the scored dates' outcomes",
    )
    hits = sum(f["inside80"] is True for f in folds)
    misses = sum(f["inside80"] is False for f in folds)
    rule(
        h["inside_simulated"] <= hits
        and h["scored_folds"] - h["inside_simulated"] <= misses,
        f"{where}: more hits or misses than the back-test has",
    )


def _basis_of(b: dict | None):
    if b is None:
        return None
    return stretch_report.Basis(
        b["factor_horizon_months"],
        b["held"],
        b["scored"],
        b["stretched_side"],
        date.fromisoformat(b["window_start"]),
        date.fromisoformat(b["window_end"]),
        b["extrapolated_because"],
        b["floored_at_zero_80"],
        b["floored_at_zero_95"],
    )


SIMULATED_95 = "simulated, not separately tested"


class _Factors:
    """The two factors of an evidence row, as stretch_report reads them to name a side."""

    def __init__(self, lower: str | None, upper: str | None):
        self.lower = None if lower is None else float(lower)
        self.upper = None if upper is None else float(upper)


def _label_rules(
    r: dict, c: dict, ranges: dict, by_h: dict, adopted: bool, rule
) -> None:
    """Every label is the sentence its structured basis gives, the basis agrees with the
    evidence, and a range has a basis exactly when the stretch is adopted and learned."""
    as_of = date.fromisoformat(r["inputs"]["as_of"])
    all_learned = all(h["factors_learned"] for h in by_h.values())
    rule(
        ranges["by_window_label"].startswith("stretched") == adopted
        and (
            not adopted or ranges["by_window_label"] == stretch_report.BY_WINDOW_LABEL
        ),
        "the months' label does not agree with the decision",
    )

    def check(name, short, label95, basis, horizon=None, closed=False) -> None:
        b = _basis_of(basis)
        if closed:
            rule(
                basis is None and short.startswith("closed"),
                f"{name}: a closed range has no basis",
            )
            return
        if b is None:
            rule(
                not short.startswith("Stretched")
                and not label95.startswith("Stretched"),
                f"{name}: labeled stretched but nothing stands behind it",
            )
            rule(
                label95 == SIMULATED_95,
                f"{name}: an unstretched 95% range is labeled simulated",
            )
            learned = by_h[horizon]["factors_learned"] if horizon else all_learned
            rule(
                not (adopted and learned),
                f"{name}: the stretch was adopted and its factors learned, but the range has no basis",
            )
            return
        rule(
            adopted,
            f"{name}: a range has a stretch basis but the stretch was not adopted",
        )
        row = by_h[b.factor_horizon_months]
        rule(
            (b.held, b.scored) == (row["inside_stretched"], row["scored_folds"]),
            f"{name}: the basis counts are not the {b.factor_horizon_months}-month evidence's",
        )
        rule(
            row["factors_learned"],
            f"{name}: stretched with factors that were not learned",
        )
        rule(
            basis["extrapolated"] == (b.extrapolated_because is not None),
            f"{name}: extrapolated exactly when a reason is given",
        )
        # the window decides the horizon whose factors it uses and whether its shape was tested
        h2, beyond = horizon_for(as_of, b.window_end)
        tested = b.window_start == as_of and b.window_end == add_months(as_of, h2)
        want = (
            "longer_than_six_months"
            if beyond
            else None
            if tested
            else "not_the_tested_shape"
        )
        rule(
            b.factor_horizon_months == h2 and b.extrapolated_because == want,
            f"{name}: not the tested horizon its window belongs to, or the wrong account of its shape",
        )
        if horizon is not None:
            rule(
                b.factor_horizon_months == horizon,
                f"{name}: not the horizon of its months",
            )
        side_row = by_h[b.factor_horizon_months]
        rule(
            b.stretched_side
            == stretch_report.side_of(
                _Factors(side_row["lower_factor"], side_row["upper_factor"])
            ),
            f"{name}: the side it says was stretched is not what the factors say",
        )
        rule(
            short == stretch_report.label_short(b),
            f"{name}: the short label is not what its basis says",
        )
        rule(
            label95 == stretch_report.label95(b),
            f"{name}: the 95% label is not what its basis says",
        )

    windows = r["forecasts"]["horizon_windows"]
    for h, v in ranges["horizons"].items():
        months = windows[h]
        horizon = None
        if months:
            y, mo = map(int, months[-1].split("-"))
            horizon = horizon_for(as_of, month_end(date(y, mo, 1)))[0]
        check(
            f"the {h} range",
            v["label_short"],
            v["label95"],
            v["basis"],
            horizon,
            not months,
        )
        if v["basis"] is not None:
            rule(
                v["label_full"] == stretch_report.label_full(_basis_of(v["basis"])),
                f"the {h} range's full label is not what its basis says",
            )
            rule(
                v["label_full"] in v["status"],
                f"the {h} range's status does not carry its full label",
            )
        else:
            if months:
                rule(
                    v["label_full"] in v["status"]
                    and (adopted or v["label_full"] == v["status"]),
                    f"the {h} range's full label is not its status",
                )
            if not adopted and months:
                rule(
                    v["label_short"] == v["status"].split(":")[0],
                    f"the {h} range's label is not its back-test label",
                )
    for q in r["gap"]["quarters"]:
        if "label_short" not in q:
            continue
        b = _basis_of(q["range_basis"])
        check(
            q["quarter"],
            q["label_short"],
            stretch_report.label95(b) if b else SIMULATED_95,
            q["range_basis"],
            None,
            q["status"] == "closed",
        )
        if not adopted and q["status"] != "closed":
            rule(
                q["label_short"] == "simulated",
                f"{q['quarter']}: an unstretched range is labeled simulated",
            )
    year = r["gap"]["fiscal_year"]
    if "label_short" in year:
        check(
            "the fiscal year",
            year["label_short"],
            year["label95"],
            year["range_basis"],
            None,
            not windows["rest of fiscal year"],
        )
    acc = c["acceptance"]
    if acc is None:
        return
    flagged = sorted(
        {
            *(
                h
                for h, v in ranges["horizons"].items()
                if v["basis"] and v["basis"]["floored_at_zero_80"]
            ),
            *(
                q["quarter"]
                for q in r["gap"]["quarters"]
                if q.get("range_basis") and q["range_basis"]["floored_at_zero_80"]
            ),
        }
    )
    rule(
        sorted(acc["floored_at_zero"]) == flagged,
        "the ranges said to be floored at zero are not the ones whose basis says so",
    )
    six = by_h[6]
    rule(
        acc["two_sided_coverage"] == (c["pooled"] or {}).get("coverage_stretched")
        and (acc["six_month_eligible_folds"], acc["six_month_scored_folds"])
        == (six["eligible_folds"], six["scored_folds"]),
        "what the rule accepted does not agree with the evidence",
    )
    learned = [h for h in by_h.values() if h["factors_learned"]]
    lower = any(
        h["lower_factor"] is not None and Decimal(h["lower_factor"]) > 1
        for h in learned
    )
    upper = any(
        h["upper_factor"] is not None and Decimal(h["upper_factor"]) > 1
        for h in learned
    )
    want = {(True, True): "both", (True, False): "lower", (False, True): "upper"}.get(
        (lower, upper), "neither"
    )
    rule(
        acc["stretched_side"] == want
        and acc["one_sided"] == (want in ("lower", "upper")),
        "the stretched side is not what the factors say",
    )
    rule(
        acc["sentence"]
        == stretch_report.acceptance_text(
            acc["stretched_side"],
            acc["two_sided_coverage"],
            acc["six_month_eligible_folds"],
            acc["six_month_scored_folds"],
            acc["floored_at_zero"],
        ),
        "the sentence on what the rule accepted is not what its fields say",
    )


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

    _better_than_baselines_rules(r, rule)
    _stretch_rules(r, rule)

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
