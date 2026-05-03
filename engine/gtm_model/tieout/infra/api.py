"""Public API orchestration helpers for Planning Tie-Out."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Optional

from gtm_model.tieout.types import TieoutResult


def _merge_source_breakdown_actuals(trajectory_breakdown: dict, archived_breakdown: dict) -> dict:
    """Copy live per-stream attribution onto the trajectory-mode stream summary."""
    merged = copy.deepcopy(trajectory_breakdown or {})
    merged_streams = merged.setdefault("streams", {})
    archived_streams = (archived_breakdown or {}).get("streams", {}) or {}

    for stream_key, stream_data in merged_streams.items():
        archived_stream = archived_streams.get(stream_key, {}) or {}
        stream_data["actual_pipeline"] = archived_stream.get("actual_pipeline")  # None if not present
        stream_data["actual_opp_count"] = archived_stream.get("actual_opp_count")  # None if not present

    return merged


def _merge_prefer_primary(primary: dict, fallback: dict) -> dict:
    """Deep-merge two nested dicts while preserving the primary payload."""
    merged = copy.deepcopy(primary or {})
    for key, fallback_value in (fallback or {}).items():
        if key not in merged or merged[key] in (None, {}):
            merged[key] = copy.deepcopy(fallback_value)
            continue
        primary_value = merged[key]
        if isinstance(primary_value, dict) and isinstance(fallback_value, dict):
            merged[key] = _merge_prefer_primary(primary_value, fallback_value)
    return merged


def _sync_trajectory_actuals_sidecar(trajectory: Any, archived_plan: Any) -> Any:
    """Keep quarter-level actuals consistent when trajectory becomes the primary scenario."""
    if trajectory is None or archived_plan is None:
        return trajectory

    archived_quarters = {
        getattr(quarter, "quarter", None): quarter
        for quarter in getattr(archived_plan, "quarters", [])
    }
    actual_fields = (
        "actual_bookings",
        "actual_pipeline",
        "actual_mqls",
        "actual_s0",
        "actual_s1",
        "actual_s2",
    )

    for trajectory_quarter in getattr(trajectory, "quarters", []):
        archived_quarter = archived_quarters.get(getattr(trajectory_quarter, "quarter", None))
        if archived_quarter is None:
            continue

        for field_name in actual_fields:
            setattr(
                trajectory_quarter,
                field_name,
                copy.deepcopy(getattr(archived_quarter, field_name, 0)),
            )

        trajectory_quarter.conversion_rates = _merge_prefer_primary(
            getattr(trajectory_quarter, "conversion_rates", {}) or {},
            getattr(archived_quarter, "conversion_rates", {}) or {},
        )
        trajectory_quarter.funnel_tieout = _merge_prefer_primary(
            getattr(trajectory_quarter, "funnel_tieout", {}) or {},
            getattr(archived_quarter, "funnel_tieout", {}) or {},
        )
        # Backfill zero actuals from archived plan's warehouse data
        archived_ft = getattr(archived_quarter, "funnel_tieout", {}) or {}
        traj_ft = trajectory_quarter.funnel_tieout or {}
        for stage_key in ("mqls_weekly", "s0_weekly", "s1_weekly", "s2_weekly"):
            traj_entry = traj_ft.get(stage_key, {})
            archived_entry = archived_ft.get(stage_key, {})
            archived_actual = archived_entry.get("actual", 0) or 0
            if not traj_entry.get("actual") and archived_actual:
                traj_entry["actual"] = archived_actual
                traj_entry["delta"] = archived_actual - traj_entry.get("plan", 0)
        trajectory_quarter.funnel_tieout = traj_ft
        trajectory_quarter.source_breakdown = _merge_source_breakdown_actuals(
            getattr(trajectory_quarter, "source_breakdown", {}) or {},
            getattr(archived_quarter, "source_breakdown", {}) or {},
        )

    return trajectory


@dataclass
class TieoutPublicApi:
    """Keep high-level public workflows out of the facade class."""

    compute_plan: Callable[..., Any]
    compute_trajectory: Callable[..., Any]
    run_health_checks: Callable[..., dict]
    get_beginning_arr_snapshot: Callable[[], tuple[float, dict]]
    get_closed_won_finance_summary: Callable[[], tuple[dict, dict]]
    get_assumptions: Callable[[], dict]
    get_targets: Callable[[], dict]
    get_decay_curve: Callable[[], list[float]]
    get_observed_arr_movements: Callable[[], dict]
    build_runtime_snapshot: Callable[..., Any]  # accepts optional as_of=date
    tieout_result_factory: Callable[..., TieoutResult]

    def compute_full(
        self,
        overflow_mode: str = "push",
        runtime_snapshot: Any | None = None,
    ) -> TieoutResult:
        """Compute the full tie-out payload with both public scenarios."""
        runtime_snapshot = runtime_snapshot or self.build_runtime_snapshot()
        base = self.compute_plan(
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )
        trajectory = self.compute_trajectory(
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )
        trajectory = _sync_trajectory_actuals_sidecar(trajectory, base)
        health_status = self.run_health_checks(runtime_snapshot=runtime_snapshot)
        targets = self.get_targets()

        return self.tieout_result_factory(
            base=base,
            trajectory=trajectory,
            top_down_beginning_arr=float(targets.get("beginning_arr", 0.0) or 0.0),
            beginning_arr=runtime_snapshot.beginning_arr,
            beginning_arr_provenance=runtime_snapshot.beginning_arr_provenance,
            bookings_summary=runtime_snapshot.bookings_summary,
            bookings_summary_provenance=runtime_snapshot.bookings_summary_provenance,
            assumptions_snapshot=self._build_assumptions_snapshot(runtime_snapshot=runtime_snapshot),
            top_down_plan=targets.get("top_down_plan", {}),
            health_status=health_status,
            arr_movements=runtime_snapshot.observed_arr_movements,
            as_of=runtime_snapshot.as_of,
        )

    def flex(
        self,
        name: str = "Flexed",
        description: str = "",
        add_aes: int = 0,
        total_aes: Optional[int] = None,
        s2_conversion: Optional[float] = None,
        mql_to_s0: Optional[float] = None,
        s0_to_s1: Optional[float] = None,
        s1_to_s2: Optional[float] = None,
        attainment_rate: Optional[float] = None,
        overflow_mode: str = "push",
        quarterly_overrides: Optional[dict] = None,
    ) -> Any:
        """Compute a flexed scenario with override normalization.

        When *quarterly_overrides* is provided the flex runs against the
        trajectory path (capacity-driven) instead of the archived plan.
        Per-quarter keys: s0_to_s1, s1_to_s2, mql_to_s0, avg_deal_size,
        ae_month_targets (preferred month-grain seat path), add_aes
        (legacy cumulative across quarters), mql_change_pct.
        Q1FY26 overrides are ignored (locked to observed actuals).

        Flat scalar overrides (add_aes, s0_to_s1, etc.) still work as
        before and route through the archived plan scenario.
        """
        if quarterly_overrides:
            return self.compute_trajectory(
                overflow_mode=overflow_mode,
                quarterly_overrides=quarterly_overrides,
                scenario_name=name,
                scenario_desc=description or "Trajectory with per-quarter overrides",
            )

        ae_overrides = self._build_ae_overrides(
            add_aes=add_aes,
            total_aes=total_aes,
        )
        conversion_overrides = self._build_conversion_overrides(
            s2_conversion=s2_conversion,
            mql_to_s0=mql_to_s0,
            s0_to_s1=s0_to_s1,
            s1_to_s2=s1_to_s2,
            attainment_rate=attainment_rate,
        )

        return self.compute_plan(
            ae_overrides=ae_overrides,
            conversion_overrides=conversion_overrides,
            scenario_name=name,
            scenario_desc=description,
            overflow_mode=overflow_mode,
        )

    def _build_assumptions_snapshot(self, runtime_snapshot: Any | None = None) -> dict:
        """Capture the compact assumptions block exposed in full results."""
        assumptions = self.get_assumptions()
        if runtime_snapshot is not None:
            close_rate_distribution = list((runtime_snapshot.observed_decay_curve or {}).get("curve", []) or [])
        else:
            close_rate_distribution = self.get_decay_curve()
        return {
            "stage_conversion": assumptions.get("forecast", {}).get("stage_conversion", {}),
            "funnel": assumptions.get("funnel", {}),
            "capacity": assumptions.get("capacity", {}),
            "close_rate_distribution": close_rate_distribution,
        }

    @staticmethod
    def _build_ae_overrides(
        add_aes: int = 0,
        total_aes: Optional[int] = None,
    ) -> Optional[dict]:
        """Normalize AE override inputs to the scenario contract."""
        if total_aes is not None:
            return {"total_aes": total_aes}
        if add_aes:
            return {"add_aes": add_aes}
        return None

    @staticmethod
    def _build_conversion_overrides(
        s2_conversion: Optional[float] = None,
        mql_to_s0: Optional[float] = None,
        s0_to_s1: Optional[float] = None,
        s1_to_s2: Optional[float] = None,
        attainment_rate: Optional[float] = None,
    ) -> Optional[dict]:
        """Normalize conversion override inputs to the scenario contract."""
        # Preserve legacy flex behavior: only stage-level funnel overrides are
        # currently wired through to the archived plan scenario.
        _ = (s2_conversion, attainment_rate)
        overrides = {}
        if mql_to_s0 is not None:
            overrides["mql_to_s0"] = mql_to_s0
        if s0_to_s1 is not None:
            overrides["s0_to_s1"] = s0_to_s1
        if s1_to_s2 is not None:
            overrides["s1_to_s2"] = s1_to_s2
        return overrides or None
