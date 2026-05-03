"""Standalone expansion workstream for Planning Tie-Out.

This module models existing-customer ARR growth separately from the
new-logo funnel. It follows a few pragmatic forecasting principles:

- Track expansion as its own revenue movement, separate from churn and
  contraction.
- Forecast off existing-customer cohorts, not just a flat percentage of ARR.
- Separate renewal-driven uplift from ongoing usage-driven growth.
- Reserve explicit hooks for consumption pricing mechanics such as
  pre-commits and true-forward adjustments.

The current implementation is still assumption-driven, but it provides a
structured engine that can later ingest live renewal dates, product usage,
and pricing rules without rewriting the tieout model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _quarter_lag(months: int) -> int:
    """Convert a month lag into whole fiscal-quarter buckets."""
    if months <= 0:
        return 0
    return max(int(math.ceil(months / 3)), 0)


@dataclass
class ExpansionAssumptions:
    """Assumptions for the standalone expansion engine."""

    contract_term_months: int = 12
    legacy_plg_share: float = 0.05
    program_maturity_by_quarter: dict[str, float] = field(default_factory=dict)

    sales_led_renewal_uplift_rate: float = 0.09
    sales_led_quarterly_usage_expansion_rate: float = 0.015
    sales_led_usage_lag_months: int = 3

    plg_quarterly_customer_expansion_rate: float = 0.05
    plg_usage_lag_months: int = 6
    plg_avg_acv: float = 30_000
    plg_avg_expansion_arr: float = 75_000

    consumption_precommit_share_of_sales_led_base: float = 0.0
    consumption_quarterly_overage_growth_rate: float = 0.0
    consumption_true_forward_capture_rate: float = 0.0
    consumption_fungibility_factor: float = 1.0

    @property
    def contract_term_quarters(self) -> int:
        return max(int(self.contract_term_months / 3), 1)

    @property
    def legacy_sales_led_share(self) -> float:
        return max(0.0, 1.0 - self.legacy_plg_share)

    @classmethod
    def from_config(cls, assumptions: dict) -> "ExpansionAssumptions":
        """Build assumptions from assumptions.yaml-style config."""
        retention = assumptions.get("retention", {}) or {}
        self_serve = assumptions.get("self_serve", {}) or {}
        engine = assumptions.get("expansion_engine", {}) or {}
        sales_cfg = engine.get("sales_led", {}) or {}
        plg_cfg = engine.get("plg", {}) or {}
        consumption_cfg = engine.get("consumption", {}) or {}

        sales_annual_rate = float(sales_cfg.get("annual_expansion_rate", retention.get("expansion_rate", 0.15)) or 0.0)
        sales_renewal_share = float(sales_cfg.get("renewal_share", 0.60) or 0.0)
        sales_usage_share = float(sales_cfg.get("usage_share", max(0.0, 1.0 - sales_renewal_share)) or 0.0)

        plg_annual_rate = float(plg_cfg.get("annual_expansion_rate", self_serve.get("expansion_rate", 0.20)) or 0.0)

        return cls(
            contract_term_months=int(engine.get("contract_term_months", 12) or 12),
            legacy_plg_share=float(engine.get("legacy_plg_share", 0.05) or 0.0),
            program_maturity_by_quarter=dict(engine.get("program_maturity_by_quarter", {}) or {}),
            sales_led_renewal_uplift_rate=float(
                sales_cfg.get("renewal_uplift_rate", sales_annual_rate * sales_renewal_share) or 0.0
            ),
            sales_led_quarterly_usage_expansion_rate=float(
                sales_cfg.get("quarterly_usage_expansion_rate", sales_annual_rate * sales_usage_share / 4.0) or 0.0
            ),
            sales_led_usage_lag_months=int(sales_cfg.get("usage_lag_months", 3) or 0),
            plg_quarterly_customer_expansion_rate=float(
                plg_cfg.get("quarterly_customer_expansion_rate", plg_annual_rate / 4.0) or 0.0
            ),
            plg_usage_lag_months=int(plg_cfg.get("usage_lag_months", self_serve.get("time_to_expand_months", 6)) or 0),
            plg_avg_acv=float(self_serve.get("avg_acv", 30_000) or 30_000),
            plg_avg_expansion_arr=float(self_serve.get("avg_expansion_acv", 75_000) or 75_000),
            consumption_precommit_share_of_sales_led_base=float(
                consumption_cfg.get("precommit_share_of_sales_led_base", 0.0) or 0.0
            ),
            consumption_quarterly_overage_growth_rate=float(
                consumption_cfg.get("quarterly_overage_growth_rate", 0.0) or 0.0
            ),
            consumption_true_forward_capture_rate=float(
                consumption_cfg.get("true_forward_capture_rate", 0.0) or 0.0
            ),
            consumption_fungibility_factor=float(
                consumption_cfg.get("fungibility_factor", 1.0) or 1.0
            ),
        )


@dataclass
class ExpansionCohort:
    """A revenue cohort that can later generate expansion."""

    motion: str
    arr: float
    start_quarter_index: int
    usage_lag_quarters: int
    renewal_term_quarters: int
    name: str = ""

    def age_in_quarters(self, quarter_index: int) -> int:
        return quarter_index - self.start_quarter_index

    def is_usage_eligible(self, quarter_index: int) -> bool:
        return self.age_in_quarters(quarter_index) >= self.usage_lag_quarters

    def is_renewal_eligible(self, quarter_index: int) -> bool:
        return self.age_in_quarters(quarter_index) >= self.renewal_term_quarters


@dataclass
class ExpansionQuarterForecast:
    """Quarter-level output for the expansion workstream."""

    quarter: str
    opening_arr: float
    sales_led_base_arr: float
    plg_base_arr: float
    renewable_sales_led_arr: float
    sales_led_usage_eligible_arr: float
    plg_usage_eligible_arr: float
    committed_consumption_arr: float
    program_maturity_factor: float
    renewal_expansion_arr: float
    usage_expansion_arr: float
    plg_expansion_arr: float
    consumption_true_forward_arr: float
    total_expansion_arr: float

    def to_dict(self) -> dict:
        return {
            "quarter": self.quarter,
            "opening_arr": self.opening_arr,
            "sales_led_base_arr": self.sales_led_base_arr,
            "plg_base_arr": self.plg_base_arr,
            "renewable_sales_led_arr": self.renewable_sales_led_arr,
            "sales_led_usage_eligible_arr": self.sales_led_usage_eligible_arr,
            "plg_usage_eligible_arr": self.plg_usage_eligible_arr,
            "committed_consumption_arr": self.committed_consumption_arr,
            "program_maturity_factor": self.program_maturity_factor,
            "renewal_expansion_arr": self.renewal_expansion_arr,
            "usage_expansion_arr": self.usage_expansion_arr,
            "plg_expansion_arr": self.plg_expansion_arr,
            "consumption_true_forward_arr": self.consumption_true_forward_arr,
            "total_expansion_arr": self.total_expansion_arr,
        }


@dataclass
class ExpansionForecast:
    """Standalone expansion forecast across the modeled horizon."""

    quarters: list[ExpansionQuarterForecast] = field(default_factory=list)

    def by_quarter(self) -> dict[str, ExpansionQuarterForecast]:
        return {quarter.quarter: quarter for quarter in self.quarters}


def project_expansion(
    *,
    beginning_arr: float,
    quarter_labels: list[str],
    sales_led_new_arr: list[float],
    plg_new_arr: list[float],
    assumptions: ExpansionAssumptions,
) -> ExpansionForecast:
    """Forecast quarter-level expansion ARR from existing-customer cohorts."""
    renewal_term_quarters = assumptions.contract_term_quarters
    sales_led_usage_lag_quarters = _quarter_lag(assumptions.sales_led_usage_lag_months)
    plg_usage_lag_quarters = _quarter_lag(assumptions.plg_usage_lag_months)
    legacy_start_index = -max(renewal_term_quarters, sales_led_usage_lag_quarters, plg_usage_lag_quarters, 1)

    cohorts: list[ExpansionCohort] = []
    if beginning_arr > 0:
        legacy_sales_led_arr = beginning_arr * assumptions.legacy_sales_led_share
        legacy_plg_arr = beginning_arr * assumptions.legacy_plg_share
        if legacy_sales_led_arr > 0:
            cohorts.append(ExpansionCohort(
                motion="sales_led",
                arr=legacy_sales_led_arr,
                start_quarter_index=legacy_start_index,
                usage_lag_quarters=sales_led_usage_lag_quarters,
                renewal_term_quarters=renewal_term_quarters,
                name="legacy_sales_led_base",
            ))
        if legacy_plg_arr > 0:
            cohorts.append(ExpansionCohort(
                motion="plg",
                arr=legacy_plg_arr,
                start_quarter_index=legacy_start_index,
                usage_lag_quarters=plg_usage_lag_quarters,
                renewal_term_quarters=renewal_term_quarters,
                name="legacy_plg_base",
            ))

    forecasts: list[ExpansionQuarterForecast] = []

    for quarter_index, quarter_label in enumerate(quarter_labels):
        opening_arr = sum(cohort.arr for cohort in cohorts)
        sales_led_base_arr = sum(cohort.arr for cohort in cohorts if cohort.motion == "sales_led")
        plg_base_arr = sum(cohort.arr for cohort in cohorts if cohort.motion == "plg")

        renewable_sales_led_arr = (
            sum(cohort.arr for cohort in cohorts if cohort.motion == "sales_led" and cohort.is_renewal_eligible(quarter_index))
            / renewal_term_quarters
        )
        sales_led_usage_eligible_arr = sum(
            cohort.arr for cohort in cohorts
            if cohort.motion == "sales_led" and cohort.is_usage_eligible(quarter_index)
        )
        plg_usage_eligible_arr = sum(
            cohort.arr for cohort in cohorts
            if cohort.motion == "plg" and cohort.is_usage_eligible(quarter_index)
        )
        committed_consumption_arr = (
            sales_led_usage_eligible_arr * assumptions.consumption_precommit_share_of_sales_led_base
        )
        program_maturity_factor = float(
            assumptions.program_maturity_by_quarter.get(quarter_label, 1.0) or 0.0
        )

        renewal_expansion_arr = (
            renewable_sales_led_arr * assumptions.sales_led_renewal_uplift_rate * program_maturity_factor
        )
        usage_expansion_arr = (
            sales_led_usage_eligible_arr
            * assumptions.sales_led_quarterly_usage_expansion_rate
            * program_maturity_factor
        )
        plg_expanding_customers = (
            (plg_usage_eligible_arr / assumptions.plg_avg_acv)
            * assumptions.plg_quarterly_customer_expansion_rate
            * program_maturity_factor
            if assumptions.plg_avg_acv > 0
            else 0.0
        )
        plg_expansion_arr = plg_expanding_customers * assumptions.plg_avg_expansion_arr
        consumption_true_forward_arr = (
            committed_consumption_arr
            * assumptions.consumption_quarterly_overage_growth_rate
            * assumptions.consumption_true_forward_capture_rate
            * assumptions.consumption_fungibility_factor
            * program_maturity_factor
        )

        total_expansion_arr = max(
            renewal_expansion_arr + usage_expansion_arr + plg_expansion_arr + consumption_true_forward_arr,
            0.0,
        )

        forecasts.append(ExpansionQuarterForecast(
            quarter=quarter_label,
            opening_arr=opening_arr,
            sales_led_base_arr=sales_led_base_arr,
            plg_base_arr=plg_base_arr,
            renewable_sales_led_arr=renewable_sales_led_arr,
            sales_led_usage_eligible_arr=sales_led_usage_eligible_arr,
            plg_usage_eligible_arr=plg_usage_eligible_arr,
            committed_consumption_arr=committed_consumption_arr,
            program_maturity_factor=program_maturity_factor,
            renewal_expansion_arr=renewal_expansion_arr,
            usage_expansion_arr=usage_expansion_arr,
            plg_expansion_arr=plg_expansion_arr,
            consumption_true_forward_arr=consumption_true_forward_arr,
            total_expansion_arr=total_expansion_arr,
        ))

        sales_led_arr_added = sales_led_new_arr[quarter_index] if quarter_index < len(sales_led_new_arr) else 0.0
        plg_arr_added = plg_new_arr[quarter_index] if quarter_index < len(plg_new_arr) else 0.0
        if sales_led_arr_added > 0:
            cohorts.append(ExpansionCohort(
                motion="sales_led",
                arr=sales_led_arr_added,
                start_quarter_index=quarter_index,
                usage_lag_quarters=sales_led_usage_lag_quarters,
                renewal_term_quarters=renewal_term_quarters,
                name=f"{quarter_label}_sales_led",
            ))
        if plg_arr_added > 0:
            cohorts.append(ExpansionCohort(
                motion="plg",
                arr=plg_arr_added,
                start_quarter_index=quarter_index,
                usage_lag_quarters=plg_usage_lag_quarters,
                renewal_term_quarters=renewal_term_quarters,
                name=f"{quarter_label}_plg",
            ))
        # Re-invest expansion ARR as new base for future-quarter expansion.
        # This is intentional compounding — expansion creates base that itself
        # expands.  The program_maturity_by_quarter curve dampens early
        # quarters so the snowball is modest until the motion matures.
        # Cap expansion reinvestment at 50% of the quarter's opening base
        # to prevent unrealistic late-year blowups.
        max_reinvestment = opening_arr * 0.50
        if total_expansion_arr > 0:
            reinvest_total = min(total_expansion_arr, max_reinvestment)
            reinvest_ratio = reinvest_total / total_expansion_arr if total_expansion_arr > 0 else 0.0
            sales_led_like_expansion = (renewal_expansion_arr + usage_expansion_arr + consumption_true_forward_arr) * reinvest_ratio
            if sales_led_like_expansion > 0:
                cohorts.append(ExpansionCohort(
                    motion="sales_led",
                    arr=sales_led_like_expansion,
                    start_quarter_index=quarter_index,
                    usage_lag_quarters=sales_led_usage_lag_quarters,
                    renewal_term_quarters=renewal_term_quarters,
                    name=f"{quarter_label}_sales_led_expansion",
                ))
            capped_plg_expansion = plg_expansion_arr * reinvest_ratio
            if capped_plg_expansion > 0:
                cohorts.append(ExpansionCohort(
                    motion="plg",
                    arr=capped_plg_expansion,
                    start_quarter_index=quarter_index,
                    usage_lag_quarters=plg_usage_lag_quarters,
                    renewal_term_quarters=renewal_term_quarters,
                    name=f"{quarter_label}_plg_expansion",
                ))

    return ExpansionForecast(quarters=forecasts)
