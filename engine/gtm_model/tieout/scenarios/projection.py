"""Monthly capacity and FY rollforward helpers for Planning Tie-Out."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

from dateutil.relativedelta import relativedelta


@dataclass
class TieoutProjectionCalculator:
    """Build monthly capacity views and project FY pipeline rollforward."""

    quarter_dates: dict[str, tuple]
    quarters: list[str]
    get_targets: Callable[[], dict]
    get_assumptions: Callable[[], dict]
    try_roster: Callable[[Optional[dict]], Optional[list[dict]]]
    monthly_capacity_row_factory: Callable[..., Any]
    get_s2_to_won_rate: Callable[[], float]
    get_rolling_s2_to_won_rate: Callable[[], dict]
    get_observed_decay_curve: Callable[[], dict]
    get_open_inventory_snapshot: Callable[[Optional[date]], Any]
    get_stage_win_rates: Callable[[], dict]
    get_stage_velocity_days: Callable[[], dict]

    def compute_monthly_capacity(
        self,
        ae_overrides: Optional[dict] = None,
        runtime_snapshot: Any | None = None,
    ) -> list[Any]:
        """Compute month-by-month capacity across FY26 using roster data when available."""
        rows: list[Any] = []
        fy_start = date(2026, 2, 1)
        roster = runtime_snapshot.roster if runtime_snapshot is not None and ae_overrides is None else self.try_roster(ae_overrides)
        monthly_target_supported = self._supports_monthly_sales_led_targets()
        monthly_targets = self.get_targets().get("monthly_bookings", {}) if monthly_target_supported else {}

        if roster:
            from gtm_model.roster import project_capacity_timeline

            cap_timeline = project_capacity_timeline(
                roster=roster,
                start_month=fy_start,
                months=12,
            )

            for month_data in cap_timeline:
                month = month_data["month"]
                quarter = self._quarter_for_month(month) or "Q1FY26"
                headcount_targets = self.get_targets().get("headcount_targets", {}).get(quarter, {})
                month_key = month.strftime("%b-%y")
                target = monthly_targets.get(month_key, 0) if monthly_target_supported else None

                rows.append(self.monthly_capacity_row_factory(
                    month=month,
                    ae_total=month_data.get("total_count", 0),
                    ae_ramped=month_data.get("ramped_count", 0),
                    se_total=headcount_targets.get("sales_engineers", 0),
                    sdr_total=headcount_targets.get("sdrs", 0),
                    ae_capacity=month_data.get("total", 0),
                    ae_capacity_ramped=0,
                    ae_capacity_ramping=0,
                    blended_ramp_pct=(
                        month_data.get("ramped_count", 0) / max(month_data.get("total_count", 1), 1)
                    ),
                    monthly_target=target,
                ))
            return rows

        assumptions = self.get_assumptions()
        seg_prod = assumptions.get("segment_productivity", {})
        ent_quota = seg_prod.get("enterprise", {}).get("annual_quota", 1_400_000)
        attainment = assumptions.get("capacity", {}).get("attainment_rate", 0.80)

        for month_offset in range(12):
            month = fy_start + relativedelta(months=month_offset)
            quarter = self._quarter_for_month(month)
            if quarter is None:
                continue

            headcount_targets = self.get_targets().get("headcount_targets", {}).get(quarter, {})
            total_aes = headcount_targets.get("account_executives", 12)
            if ae_overrides:
                if "month_targets" in ae_overrides:
                    total_aes = self._resolve_month_target_total(
                        month=month,
                        ae_overrides=ae_overrides,
                        fallback_total=total_aes,
                    )
                elif "total_aes" in ae_overrides:
                    total_aes = ae_overrides["total_aes"]
                elif "add_aes" in ae_overrides:
                    total_aes += ae_overrides["add_aes"]

            capacity = total_aes * (ent_quota / 12) * attainment
            month_key = month.strftime("%b-%y")
            target = monthly_targets.get(month_key, 0) if monthly_target_supported else None

            rows.append(self.monthly_capacity_row_factory(
                month=month,
                ae_total=total_aes,
                ae_ramped=total_aes,
                se_total=headcount_targets.get("sales_engineers", 0),
                sdr_total=headcount_targets.get("sdrs", 0),
                ae_capacity=capacity,
                ae_capacity_ramped=capacity,
                ae_capacity_ramping=0,
                blended_ramp_pct=1.0,
                monthly_target=target,
            ))

        return rows

    def _supports_monthly_sales_led_targets(self) -> bool:
        """Return whether the active plan contract supports monthly sales-led targets."""
        plan_meta = self.get_targets().get("top_down_plan", {}) or {}
        plan_id = str(plan_meta.get("plan_id") or "")
        preset_id = str(plan_meta.get("preset_id") or "")
        status = str(plan_meta.get("status") or "")
        return not (status == "baseline_reference" or preset_id == "board_baseline")

    def project_full_year_bookings(
        self,
        quarter_payloads: list[dict],
        monthly_capacity: list[Any],
        overflow_mode: str,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Project one FY-wide roll-forward so quarter outputs share tails correctly."""
        from gtm_model.pipeline_rollforward import project_pipeline_rollforward

        if not monthly_capacity:
            return self._empty_projection()

        months = [row.month for row in monthly_capacity]
        capacities = [row.ae_capacity for row in monthly_capacity]
        pipeline_creation: list[float] = []
        future_generation_win_rates: list[float] = []
        future_generation_basis: list[str] = []
        if runtime_snapshot is not None:
            fallback_s2_to_won = runtime_snapshot.s2_to_won_rate
            rolling_info = runtime_snapshot.rolling_s2_to_won_rate
            decay_info = runtime_snapshot.observed_decay_curve
            inventory_snapshot = runtime_snapshot.open_inventory_snapshot
            stage_win_rates = runtime_snapshot.stage_win_rates
            stage_velocity_days = runtime_snapshot.stage_velocity_days
        else:
            fallback_s2_to_won = self.get_s2_to_won_rate()
            rolling_info = self.get_rolling_s2_to_won_rate()
            decay_info = self.get_observed_decay_curve()
            inventory_snapshot = self.get_open_inventory_snapshot(as_of=date.today())
            stage_win_rates = self.get_stage_win_rates()
            stage_velocity_days = self.get_stage_velocity_days()

        for payload in quarter_payloads:
            creation = list(payload["bu"].get("monthly_creation", []))
            if len(creation) < 3:
                creation = creation + [0.0] * (3 - len(creation))
            pipeline_creation.extend(creation[:3])

            source_breakdown = (payload.get("bu", {}) or {}).get("source_breakdown", {}) or {}
            pipeline_value_provenance = source_breakdown.get("pipeline_value_provenance", {}) or {}
            basis = str(pipeline_value_provenance.get("basis", "raw_s2_pipeline_created") or "raw_s2_pipeline_created")

            future_generation_win_rates.extend([fallback_s2_to_won] * 3)
            future_generation_basis.extend([basis] * 3)

        pipeline_creation = pipeline_creation[:len(months)]
        rollforward = project_pipeline_rollforward(
            inventory_snapshot=inventory_snapshot,
            monthly_pipeline_created=pipeline_creation,
            months=months,
            stage_win_rates=stage_win_rates,
            stage_velocity_days=stage_velocity_days,
            close_timing_curve=decay_info["curve"],
            s2_to_won_rate=fallback_s2_to_won,
            monthly_capacity=capacities,
            overflow_mode=overflow_mode,
            monthly_future_generation_win_rates=future_generation_win_rates[:len(months)],
            future_generation_basis=future_generation_basis[:len(months)],
        )
        expected = list(rollforward.total_expected_wins)[:len(months)]
        capped = list(rollforward.capacity_capped_wins)[:len(months)]
        overflow = list(rollforward.overflow_backlog)[:len(months)]

        quarter_sales_led: dict[str, float] = {}
        for index, quarter in enumerate(self.quarters):
            start_idx = index * 3
            quarter_sales_led[quarter] = sum(expected[start_idx:start_idx + 3])

        return {
            "months": months,
            "pipeline_creation": pipeline_creation,
            "expected": expected,
            "capped": capped,
            "overflow": overflow,
            "existing_wins": list(rollforward.existing_inventory_wins)[:len(months)],
            "existing_losses": list(rollforward.existing_inventory_losses)[:len(months)],
            "existing_remaining": list(rollforward.existing_inventory_remaining)[:len(months)],
            "future_wins": list(rollforward.future_generation_wins)[:len(months)],
            "total_expected": list(rollforward.total_expected_wins)[:len(months)],
            "provenance": {
                **dict(rollforward.provenance or {}),
                "s2_to_won_source": rolling_info["source"],
                "s2_to_won_sample": rolling_info.get("sample", 0),
                "s2_to_won_lookback_days": rolling_info.get("lookback_days", 0),
                "decay_curve_source": decay_info["source"],
                "decay_curve_sample": decay_info.get("sample", 0),
            },
            "quarter_sales_led": quarter_sales_led,
        }

    def _quarter_for_month(self, month: date) -> Optional[str]:
        """Resolve the owning quarter for a given month."""
        for quarter, (start, end) in self.quarter_dates.items():
            if start <= month <= end:
                return quarter
        return None

    @staticmethod
    def _resolve_month_target_total(
        month: date,
        ae_overrides: Optional[dict],
        fallback_total: int,
    ) -> int:
        """Resolve the most recent explicit month-target seat total.

        When the live roster path is unavailable, month-level AE targets should
        still drive the fallback capacity view instead of collapsing back to
        quarter-level headcount assumptions.
        """
        month_targets = (ae_overrides or {}).get("month_targets") or {}
        if not month_targets:
            return int(fallback_total)

        effective_total = int(fallback_total)
        for raw_month, raw_target in sorted(month_targets.items()):
            month_str = str(raw_month).strip()
            if len(month_str) == 7:
                month_str = f"{month_str}-01"
            target_month = date.fromisoformat(month_str[:10]).replace(day=1)
            if target_month <= month and int(raw_target or 0) > effective_total:
                effective_total = int(raw_target)
        return effective_total

    @staticmethod
    def _empty_projection() -> dict:
        """Return an empty FY rollforward payload."""
        return {
            "months": [],
            "pipeline_creation": [],
            "expected": [],
            "capped": [],
            "overflow": [],
            "existing_wins": [],
            "existing_losses": [],
            "existing_remaining": [],
            "future_wins": [],
            "total_expected": [],
            "provenance": {},
            "quarter_sales_led": {},
        }
