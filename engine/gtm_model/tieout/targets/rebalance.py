"""Config pipeline rebalance helpers for Planning Tie-Out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class TieoutPipelineRebalancer:
    """Anchor config-mode pipeline dollars to implied S2 targets."""

    get_registered_funnel_rate: Callable[[str, float], float]

    def rebalance_projection_pipeline_values(self, projection: dict, td: dict) -> dict:
        """Scale projected stream values to the configured quarter pipeline target."""
        s1_pipeline_total = float(td.get("s1_pipeline_total", 0.0) or 0.0)
        if s1_pipeline_total <= 0:
            return projection

        s1_to_s2_rate = self.get_registered_funnel_rate("s1_to_s2", 0.25)
        configured_total = s1_pipeline_total * s1_to_s2_rate
        raw_total_before_rebalance = float(sum(projection.get("total_monthly_creation", []) or []))
        stream_targets: dict[str, float] = {}
        by_source = td.get("s1_pipeline_by_source") or {}
        if by_source:
            marketing_total = float(by_source.get("marketing_sourced", by_source.get("marketing", 0.0)) or 0.0) * s1_to_s2_rate
            sdr_total = float(by_source.get("sdr_sourced", by_source.get("sdr", 0.0)) or 0.0) * s1_to_s2_rate
            ae_total = float(by_source.get("ae_sourced", by_source.get("ae", 0.0)) or 0.0) * s1_to_s2_rate
            stream_targets["marketing_sdr"] = marketing_total + sdr_total
            stream_targets["ae_selfgen"] = ae_total
            allocated_total = stream_targets["marketing_sdr"] + stream_targets["ae_selfgen"]
            remainder = max(configured_total - allocated_total, 0.0)
            if remainder > 0:
                stream_targets["marketing_sdr"] += remainder
        else:
            sales_led_raw = {
                "marketing_sdr": float(sum((projection.get("marketing_sdr", {}) or {}).get("monthly_creation", []) or [])),
                "ae_selfgen": float(sum((projection.get("ae_selfgen", {}) or {}).get("monthly_creation", []) or [])),
            }
            sales_led_total = sum(sales_led_raw.values())
            if sales_led_total > 0:
                stream_targets["marketing_sdr"] = configured_total * (sales_led_raw["marketing_sdr"] / sales_led_total)
                stream_targets["ae_selfgen"] = configured_total * (sales_led_raw["ae_selfgen"] / sales_led_total)
            else:
                stream_targets["marketing_sdr"] = configured_total * 0.65
                stream_targets["ae_selfgen"] = configured_total * 0.35
        stream_targets["plg"] = 0.0

        num_months = len(projection.get("total_monthly_creation", []) or [])
        if num_months <= 0:
            return projection

        configured_monthly = list(td.get("s1_pipeline_monthly", []) or [])
        overall_weights = self._weights(configured_monthly, num_months) if configured_monthly else None

        for stream_key in ("marketing_sdr", "ae_selfgen", "plg"):
            stream_data = projection.get(stream_key)
            if not stream_data:
                continue
            target_total = float(stream_targets.get(stream_key, 0.0) or 0.0)
            if target_total <= 0:
                stream_data["monthly_creation"] = [0.0] * num_months
                continue
            monthly_weights = overall_weights or self._weights(
                stream_data.get("monthly_s1_count", []) or stream_data.get("monthly_input", []),
                num_months,
            )
            stream_data["monthly_creation"] = [target_total * weight for weight in monthly_weights]

        projection["total_monthly_creation"] = [
            sum(
                float((projection.get(stream_key, {}) or {}).get("monthly_creation", [0.0] * num_months)[idx] or 0.0)
                for stream_key in ("marketing_sdr", "ae_selfgen", "plg")
            )
            for idx in range(num_months)
        ]
        projection["pipeline_value_provenance"] = {
            "basis": "s2_pipeline_created",
            "configured_total": configured_total,
            "raw_total_before_rebalance": raw_total_before_rebalance,
            "s1_pipeline_total": s1_pipeline_total,
            "s1_to_s2_rate_used": s1_to_s2_rate,
            "implied_s2_target": configured_total,
        }
        return projection

    @staticmethod
    def _weights(values: list[float], length: int) -> list[float]:
        """Normalize a monthly profile to weights across the target length."""
        aligned = list(values or [])[:length]
        if len(aligned) < length:
            aligned.extend([0.0] * (length - len(aligned)))
        total = sum(float(value or 0.0) for value in aligned)
        if total <= 0:
            return [1.0 / max(length, 1)] * length
        return [float(value or 0.0) / total for value in aligned]
