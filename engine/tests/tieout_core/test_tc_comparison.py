"""Goal 3A review: every comparison figure is computed in the core, not in the generator."""

from decimal import Decimal

import pytest

from engine.tieout_core.comparison import BASELINE, comparison_rows

REST, TWELVE = "rest of fiscal year", "next twelve months"


def report(expected, gap, forecast_rest=None, plan=None):
    return {
        "gap": {
            "fiscal_year": {
                "expected": expected,
                "gap": gap,
                "forecast_rest_of_year": forecast_rest,
            }
        },
        **({"plan": plan} if plan else {}),
    }


def plan(baseline_rest="4000.00", with_rest="4600.00", cost="800.00"):
    return {
        "baseline": {REST: baseline_rest, TWELVE: "9000.00"},
        "with_plan": {REST: with_rest, TWELVE: "9900.00"},
        "difference": {REST: "600.00", TWELVE: "900.00"},
        "expected_fiscal_year": "5600.00",
        "gap": {"fiscal_year": {"baseline_gap": "3000.00", "gap_with_plan": "1500.00"}},
        "cash_cost_in_twelve_months": cost,
    }


def test_each_plan_row_reads_the_cores_with_plan_figures():
    reports = {
        BASELINE: report("5000.00", "3000.00", "4000.00"),
        "demo-plan": report("5000.00", "3000.00", "4000.00", plan()),
    }
    by = {r["scenario"]: r for r in comparison_rows(reports, {})}
    assert by[BASELINE]["expected_fiscal_year"] == "5000.00"
    assert by[BASELINE]["fiscal_year_gap_change"] is None
    row = by["demo-plan"]
    assert (
        row["expected_fiscal_year"] == "5600.00"
    )  # the core's plan.expected_fiscal_year
    assert row["fiscal_year_gap"] == "1500.00"
    assert row["bookings_change"] == {REST: "600.00", TWELVE: "900.00"}
    assert row["cash_cost_in_twelve_months"] == "800.00"
    assert row["fiscal_year_gap_change"] == "-1500.00"
    assert Decimal(row["fiscal_year_gap_change"]) == Decimal("1500.00") - Decimal(
        "3000.00"
    )


def test_a_plan_whose_baseline_is_not_the_signed_forecast_is_refused():
    reports = {
        BASELINE: report("5000.00", "3000.00", "4000.00"),
        "demo-plan": report(
            "5000.00", "3000.00", "4000.00", plan(baseline_rest="4100.00")
        ),
    }
    with pytest.raises(ValueError, match="baseline"):
        comparison_rows(reports, {})


def test_an_unavailable_forecast_compares_as_null_not_zero():
    (row,) = comparison_rows({BASELINE: report(None, None)}, {})
    assert row["expected_fiscal_year"] is None and row["fiscal_year_gap"] is None


def test_a_plan_the_core_could_not_value_compares_as_unavailable():
    reports = {
        BASELINE: report(None, None),
        "demo-plan": report(None, None, plan={"unavailable": "x"}),
    }
    rows = comparison_rows(reports, {})
    assert (
        rows[1]["bookings_change"] is None and rows[1]["expected_fiscal_year"] is None
    )
