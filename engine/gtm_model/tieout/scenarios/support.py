"""Support helpers for Planning Tie-Out scenario detail and expansion views."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from dateutil.relativedelta import relativedelta


@dataclass
class TieoutSupportServices:
    """Build scenario support payloads that are consumed by UI/export layers."""

    quarter_dates: dict[str, tuple]
    quarters: list[str]
    get_assumptions: Callable[[], dict]
    get_td_quarter: Callable[[str], dict]
    derive_weekly_targets: Callable[[str, dict], tuple[dict, bool]]
    estimate_ae_selfgen_s0_weekly: Callable[[dict], int]
    get_config_conversion_rates: Callable[[str, dict], dict]
    rebalance_projection_pipeline_values: Callable[[dict, dict], dict]
    get_beginning_arr_snapshot: Callable[[], tuple[float, dict]]

    def build_config_sales_led_stream_fallbacks(self) -> dict[str, list[float]]:
        """Build 12-month config-mode sales-led stream fallbacks by source."""
        from gtm_model.funnel_engine import compute_three_source_pipeline

        avg_deal_size = float(self.get_assumptions().get("funnel", {}).get("avg_acv", 300_000) or 300_000)
        streams = {
            "marketing_sdr": [],
            "ae_selfgen": [],
        }

        for quarter in self.quarters:
            td = self.get_td_quarter(quarter)
            td, _ = self.derive_weekly_targets(quarter, td)
            projection = compute_three_source_pipeline(
                marketing_sdr_mqls_weekly=td["mqls_weekly"] if td["mqls_weekly"] > 0 else 264,
                ae_selfgen_s0_weekly=self.estimate_ae_selfgen_s0_weekly(td),
                plg_signups_weekly=0,
                rates=self.get_config_conversion_rates(quarter, td),
                weeks=td.get("weeks_in_quarter", 13),
                avg_deal_size=avg_deal_size,
            )
            projection = self.rebalance_projection_pipeline_values(projection, td)
            for stream_key in streams:
                monthly_creation = list((projection.get(stream_key) or {}).get("monthly_creation", []) or [])
                while len(monthly_creation) < 3:
                    monthly_creation.append(0.0)
                streams[stream_key].extend(monthly_creation[:3])

        return {key: values[:12] for key, values in streams.items()}

    @staticmethod
    def summarize_source_breakdown(
        projections: dict,
        *,
        mode: str,
        actual_streams: Optional[dict] = None,
    ) -> dict:
        """Normalize per-stream projection detail for downstream UI/export use."""
        streams = {}
        actual_streams = actual_streams or {}
        actual_counts = actual_streams.get("counts", {}) or {}
        actual_pipeline = actual_streams.get("pipeline", {}) or {}

        for stream_key in ("marketing_sdr", "ae_selfgen", "plg"):
            projection = projections.get(stream_key, {})
            if not projection:
                continue
            streams[stream_key] = {
                "stream_key": stream_key,
                "display_name": projection.get("display_name", stream_key.replace("_", " ").title()),
                "input_label": projection.get("input_label", "Input"),
                "weekly_input": float(projection.get("weekly_input", 0.0) or 0.0),
                "weekly_s0_count": float(projection.get("weekly_s0_count", 0.0) or 0.0),
                "weekly_s1_count": float(projection.get("weekly_s1_count", 0.0) or 0.0),
                "weekly_s2_count": float(projection.get("weekly_s2_count", 0.0) or 0.0),
                "monthly_input": list(projection.get("monthly_input", []) or []),
                "monthly_s0_count": list(projection.get("monthly_s0_count", []) or []),
                "monthly_s1_count": list(projection.get("monthly_s1_count", []) or []),
                "monthly_s2_count": list(projection.get("monthly_s2_count", []) or []),
                "monthly_creation": list(projection.get("monthly_creation", []) or []),
                "quarter_pipeline_created": float(sum(projection.get("monthly_creation", []) or [])),
                "actual_opp_count": int(actual_counts.get(stream_key, 0) or 0),
                "actual_pipeline": float(actual_pipeline.get(stream_key, 0.0) or 0.0),
            }

        return {
            "mode": mode,
            "streams": streams,
            "pipeline_value_provenance": copy.deepcopy(
                projections.get("pipeline_value_provenance", {}) or {}
            ),
        }

    @staticmethod
    def build_monthly_source_detail(quarter_payloads: list[dict]) -> list[dict]:
        """Expand per-quarter stream projections into one FY-wide monthly detail table."""
        rows = []
        for payload in quarter_payloads:
            breakdown = (payload.get("bu") or {}).get("source_breakdown", {})
            streams = breakdown.get("streams", {}) or {}
            start = payload["start"]
            for stream_key, stream_data in streams.items():
                monthly_input = list(stream_data.get("monthly_input", []) or [])
                monthly_s0 = list(stream_data.get("monthly_s0_count", []) or [])
                monthly_s1 = list(stream_data.get("monthly_s1_count", []) or [])
                monthly_s2 = list(stream_data.get("monthly_s2_count", []) or [])
                monthly_creation = list(stream_data.get("monthly_creation", []) or [])
                num_months = max(
                    len(monthly_input),
                    len(monthly_s0),
                    len(monthly_s1),
                    len(monthly_s2),
                    len(monthly_creation),
                )
                for idx in range(num_months):
                    month = start + relativedelta(months=idx)
                    rows.append({
                        "month": month,
                        "month_label": month.strftime("%b %Y"),
                        "quarter": payload["quarter"],
                        "confidence_tier": payload["confidence_tier"],
                        "mode": breakdown.get("mode", "config"),
                        "source": stream_data.get("display_name", stream_key.replace("_", " ").title()),
                        "input_label": stream_data.get("input_label", "Input"),
                        "input_count": float(monthly_input[idx]) if idx < len(monthly_input) else 0.0,
                        "s0_count": float(monthly_s0[idx]) if idx < len(monthly_s0) else 0.0,
                        "s1_count": float(monthly_s1[idx]) if idx < len(monthly_s1) else 0.0,
                        "s2_count": float(monthly_s2[idx]) if idx < len(monthly_s2) else 0.0,
                        "pipeline_created": float(monthly_creation[idx]) if idx < len(monthly_creation) else 0.0,
                    })
        return rows

    def project_expansion_workstream(
        self,
        quarter_payloads: list[dict],
        monthly_projection: dict,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Run the standalone expansion engine and return quarter-level detail."""
        from gtm_model.expansion_engine import ExpansionAssumptions, project_expansion

        sales_led_new_arr = [
            float(monthly_projection.get("quarter_sales_led", {}).get(quarter, 0.0) or 0.0)
            for quarter in self.quarters
        ]
        plg_new_arr = [
            float((payload.get("bu") or {}).get("plg", 0.0) or 0.0)
            for payload in quarter_payloads
        ]
        assumptions = ExpansionAssumptions.from_config(self.get_assumptions())
        if runtime_snapshot is not None:
            beginning_arr = runtime_snapshot.beginning_arr
        else:
            beginning_arr, _ = self.get_beginning_arr_snapshot()
        forecast = project_expansion(
            beginning_arr=beginning_arr,
            quarter_labels=self.quarters,
            sales_led_new_arr=sales_led_new_arr,
            plg_new_arr=plg_new_arr,
            assumptions=assumptions,
        )
        return {quarter: detail.to_dict() for quarter, detail in forecast.by_quarter().items()}

    def assign_confidence_tier(self, quarter: str) -> str:
        """Assign a confidence tier to a quarter based on distance from today."""
        today = date.today()
        start, end = self.quarter_dates[quarter]

        current_q = None
        for current_quarter, (q_start, q_end) in self.quarter_dates.items():
            if q_start <= today <= q_end:
                current_q = current_quarter
                break

        if current_q is None:
            if today < date(2026, 2, 1):
                current_q = "Q1FY26"
            else:
                current_q = "Q4FY26"

        current_idx = self.quarters.index(current_q)
        this_idx = self.quarters.index(quarter)
        offset = this_idx - current_idx

        if offset <= 0:
            return "committed"
        if offset == 1:
            return "building"
        return "planned"
