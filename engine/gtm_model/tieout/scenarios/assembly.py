"""Scenario assembly helpers for Planning Tie-Out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class TieoutScenarioAssembler:
    """Build `ScenarioResult` objects from prepared quarter payloads."""

    project_full_year_bookings: Callable[[list[dict], list[Any], str], dict]
    project_expansion_workstream: Callable[[list[dict], dict], dict]
    get_observed_arr_movements: Callable[[], dict]
    get_beginning_arr_snapshot: Callable[[], tuple[float, dict]]
    build_monthly_source_detail: Callable[[list[dict]], list[dict]]
    quarter_tieout_factory: Callable[..., Any]
    scenario_result_factory: Callable[..., Any]

    def _compute_plan_churn(self, td: dict) -> float:
        """Compute quarter churn, preferring any observed ARR movement source."""
        return self._compute_plan_churn_with_snapshot(td, runtime_snapshot=None)

    def _compute_plan_churn_with_snapshot(self, td: dict, runtime_snapshot: Any | None) -> float:
        """Compute quarter churn, optionally using a shared runtime snapshot."""
        if runtime_snapshot is not None:
            arr_movements = runtime_snapshot.observed_arr_movements
            beginning_arr = runtime_snapshot.beginning_arr
        else:
            arr_movements = self.get_observed_arr_movements()
            beginning_arr, _ = self.get_beginning_arr_snapshot()
        if (
            arr_movements.get("source") not in {"", "unavailable", None}
            and arr_movements.get("observed_annual_churn_rate", 0) > 0
        ):
            quarterly_churn_rate = arr_movements["observed_annual_churn_rate"] / 4.0
            return beginning_arr * quarterly_churn_rate if beginning_arr else 0.0

        td_gross = td["bookings"] + td["plg"] + td["expansion"]
        td_net = td["total_net_new"]
        return max(td_gross - td_net, 0.0) if td_net > 0 else 0.0

    def _build_quarters(
        self,
        quarter_payloads: list[dict],
        monthly_projection: dict,
        expansion_projection: dict,
        runtime_snapshot: Any | None = None,
    ) -> list[Any]:
        """Build per-quarter output records from shared monthly projections."""
        quarters = []
        for payload in quarter_payloads:
            quarter = payload["quarter"]
            td = payload["td"]
            bu = payload["bu"]
            sales_led = monthly_projection["quarter_sales_led"].get(quarter, bu["sales_led"])
            expansion_detail = expansion_projection.get(quarter, {})
            modeled_expansion = float(expansion_detail.get("total_expansion_arr", 0.0) or 0.0)
            plan_churn = self._compute_plan_churn_with_snapshot(td, runtime_snapshot=runtime_snapshot)
            total = sales_led + bu["plg"] + modeled_expansion - plan_churn

            quarters.append(self.quarter_tieout_factory(
                quarter=quarter,
                period_start=payload["start"],
                period_end=payload["end"],
                td_bookings=td["bookings"],
                td_plg=td["plg"],
                td_expansion=td["expansion"],
                td_total_net_new=td["total_net_new"],
                td_ending_arr=td["ending_arr"],
                td_pipeline_target=td["pipeline_target"],
                td_aes=td["aes"],
                td_ses=td["ses"],
                td_sdrs=td["sdrs"],
                td_total_gtm=td["total_gtm"],
                td_mqls_weekly=td["mqls_weekly"],
                td_s0_weekly=td["s0_weekly"],
                td_s1_weekly=td["s1_weekly"],
                td_s2_weekly=td["s2_weekly"],
                bu_sales_led_arr=sales_led,
                bu_plg_arr=bu["plg"],
                bu_expansion_arr=modeled_expansion,
                bu_churn=plan_churn,
                bu_total_arr=total,
                bu_ramped_aes=bu["ramped_aes"],
                bu_total_aes=bu["total_aes"],
                bu_blended_ramp=bu["blended_ramp"],
                bu_mqls_projected=bu["mqls_projected"],
                bu_s0_projected=bu["s0_projected"],
                bu_s1_projected=bu["s1_projected"],
                bu_s2_projected=bu["s2_projected"],
                actual_bookings=bu.get("actual_bookings", 0.0),
                actual_pipeline=bu.get("actual_pipeline", 0.0),
                actual_mqls=bu.get("actual_mqls", 0),
                actual_s0=bu.get("actual_s0", 0),
                actual_s1=bu.get("actual_s1", 0),
                actual_s2=bu.get("actual_s2", 0),
                conversion_rates=bu.get("conversion_rates", {}),
                funnel_tieout=bu.get("funnel_tieout", {}),
                source_breakdown=bu.get("source_breakdown", {}),
                expansion_breakdown=expansion_detail,
                target_provenance=td.get("target_provenance", {}),
                confidence_tier=payload["confidence_tier"],
                is_derived_targets=payload["is_derived"],
                plg_source=bu.get("plg_source", "config"),
            ))
        return quarters

    @staticmethod
    def _build_capacity_warnings(quarters: list[Any]) -> list[str]:
        """Emit warnings when the roster and plan-case headcount diverge."""
        warnings: list[str] = []
        for quarter in quarters:
            if quarter.td_aes > 0 and quarter.bu_total_aes > 0:
                divergence = quarter.td_aes - quarter.bu_total_aes
                if abs(divergence) >= 3:
                    warnings.append(
                        f"{quarter.quarter}: {quarter.bu_total_aes} AEs on roster vs "
                        f"{quarter.td_aes} in plan ({abs(divergence)} hires behind). "
                        f"Forecast uses actual roster, not plan targets."
                    )
        return warnings

    def assemble(
        self,
        name: str,
        description: str,
        quarter_payloads: list[dict],
        monthly_capacity: list[Any],
        overflow_mode: str,
        overrides: dict | None = None,
        provenance_updates: dict | None = None,
        runtime_snapshot: Any | None = None,
    ) -> Any:
        """Build a `ScenarioResult` from shared quarter payloads."""
        monthly_projection = self.project_full_year_bookings(
            quarter_payloads=quarter_payloads,
            monthly_capacity=monthly_capacity,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )
        if provenance_updates:
            monthly_projection.setdefault("provenance", {}).update(provenance_updates)

        expansion_projection = self.project_expansion_workstream(
            quarter_payloads,
            monthly_projection,
            runtime_snapshot=runtime_snapshot,
        )
        quarters = self._build_quarters(
            quarter_payloads=quarter_payloads,
            monthly_projection=monthly_projection,
            expansion_projection=expansion_projection,
            runtime_snapshot=runtime_snapshot,
        )

        return self.scenario_result_factory(
            name=name,
            description=description,
            quarters=quarters,
            monthly_capacity=monthly_capacity,
            monthly_months=monthly_projection["months"],
            monthly_pipeline_creation=monthly_projection["pipeline_creation"],
            monthly_bookings_expected=monthly_projection["expected"],
            monthly_bookings_capped=monthly_projection["capped"],
            monthly_overflow=monthly_projection["overflow"],
            monthly_existing_inventory_wins=monthly_projection.get("existing_wins", []),
            monthly_existing_inventory_losses=monthly_projection.get("existing_losses", []),
            monthly_existing_inventory_remaining=monthly_projection.get("existing_remaining", []),
            monthly_future_generation_wins=monthly_projection.get("future_wins", []),
            monthly_total_expected_wins=monthly_projection.get("total_expected", []),
            monthly_rollforward_provenance=monthly_projection.get("provenance", {}),
            monthly_source_detail=self.build_monthly_source_detail(quarter_payloads),
            overrides=overrides or {},
            capacity_warnings=self._build_capacity_warnings(quarters),
        )
