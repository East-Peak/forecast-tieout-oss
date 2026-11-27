"""How each named scenario compares with the as-signed baseline: the figures behind
``comparison.json``. Every figure is the core's (the plan section's own with-plan numbers);
the one difference taken here, the change in the fiscal-year gap, is taken in decimals.
The generator only serialises this; the browser shows it and subtracts nothing."""

from __future__ import annotations

from decimal import Decimal

from .plan import REST_OF_FY

BASELINE = "as-signed"


def comparison_rows(reports: dict[str, dict], labels: dict[str, str]) -> list[dict]:
    rows = []
    signed = reports.get(BASELINE)
    signed_rest = (
        signed["gap"]["fiscal_year"].get("forecast_rest_of_year") if signed else None
    )
    for scenario, r in reports.items():
        year = r["gap"]["fiscal_year"]
        plan = r.get("plan")
        row = {
            "scenario": scenario,
            "label": labels.get(scenario, scenario),
            "expected_fiscal_year": year["expected"],
            "fiscal_year_gap": year["gap"],
            "bookings_change": None,
            "fiscal_year_gap_change": None,
            "cash_cost_in_twelve_months": None,
        }
        if plan is not None and "unavailable" not in plan:
            if signed_rest is not None and plan["baseline"][REST_OF_FY] != signed_rest:
                raise ValueError(
                    f"{scenario}: the plan's baseline {plan['baseline'][REST_OF_FY]} is not the "
                    f"as-signed forecast {signed_rest}"
                )
            fy = plan["gap"]["fiscal_year"]
            row["expected_fiscal_year"] = plan["expected_fiscal_year"]
            row["fiscal_year_gap"] = fy["gap_with_plan"]
            row["fiscal_year_gap_change"] = (
                f"{Decimal(fy['gap_with_plan']) - Decimal(fy['baseline_gap']):.2f}"
            )
            row["bookings_change"] = dict(plan["difference"])
            row["cash_cost_in_twelve_months"] = plan["cash_cost_in_twelve_months"]
        elif plan is not None:
            row["expected_fiscal_year"] = row["fiscal_year_gap"] = None
        rows.append(row)
    return rows
