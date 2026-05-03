"""Scenario orchestration helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from gtm_model.tieout.runtime.snapshot import load_trajectory_roster_snapshot

logger = logging.getLogger(__name__)


@dataclass
class TieoutScenarioComputer:
    """Compute plan and trajectory scenarios while preserving tieout contracts."""

    quarter_dates: dict[str, tuple]
    quarters: list[str]
    get_config_dir: Callable[[], Path]
    get_assumptions: Callable[[], dict]
    try_cdw_freshness: Callable[[], dict]
    get_cdw: Callable[[], Any]
    try_funnel_from_cdw: Callable[[str], Optional[dict]]
    get_td_quarter: Callable[[str], dict]
    derive_weekly_targets: Callable[[str, dict], tuple[dict, bool]]
    config_driven_bottoms_up: Callable[..., dict]
    cdw_bottoms_up: Callable[..., dict]
    assign_confidence_tier: Callable[[str], str]
    compute_monthly_capacity: Callable[[Optional[dict]], list[Any]]
    assemble_scenario: Callable[..., Any]
    get_runtime_funnel_rates: Callable[[], dict[str, float]]
    describe_runtime_funnel_rates: Callable[[], dict[str, dict]]
    get_observed_ae_productivity: Callable[..., dict]
    get_observed_ae_ramp_curve: Callable[..., dict]
    get_trailing_mql_weekly_signal: Callable[..., tuple[Optional[list[float]], str]]
    build_config_sales_led_stream_fallbacks: Callable[[], dict[str, list[float]]]
    compute_plan_scenario: Callable[..., Any]
    try_roster: Callable[[Optional[dict]], Optional[list[dict]]]
    get_self_serve_velocity: Callable[[], dict]
    get_monthly_mql_actuals: Callable[..., tuple] = lambda as_of, months=12, fy_start=None: ([None] * months, None)

    def compute_plan(
        self,
        ae_overrides: Optional[dict] = None,
        conversion_overrides: Optional[dict] = None,
        scenario_name: str = "Archived Plan",
        scenario_desc: str = "",
        overflow_mode: str = "push",
        runtime_snapshot: Any | None = None,
    ) -> Any:
        """Compute the archived plan scenario."""
        use_warehouse = self._should_use_warehouse()
        quarter_payloads: list[dict] = []

        for quarter in self.quarters:
            td = self.get_td_quarter(quarter)
            start, end = self.quarter_dates[quarter]
            td, is_derived = self.derive_weekly_targets(quarter, td)

            funnel_result = None
            quarter_started = start <= date.today()
            if use_warehouse and conversion_overrides is None and quarter_started:
                funnel_result = self.try_funnel_from_cdw(quarter)

            if funnel_result is not None:
                bu = self.cdw_bottoms_up(
                    quarter=quarter,
                    td=td,
                    funnel_result=funnel_result,
                    overflow_mode=overflow_mode,
                    ae_overrides=ae_overrides,
                    runtime_snapshot=runtime_snapshot,
                )
            else:
                bu = self.config_driven_bottoms_up(
                    quarter=quarter,
                    td=td,
                    overflow_mode=overflow_mode,
                    conversion_overrides=self._resolve_cdw_conversion_overrides(
                        quarter=quarter,
                        use_warehouse=use_warehouse,
                        conversion_overrides=conversion_overrides,
                    ),
                    ae_overrides=ae_overrides,
                    runtime_snapshot=runtime_snapshot,
                )

            quarter_payloads.append(self._quarter_payload(
                quarter=quarter,
                start=start,
                end=end,
                td=td,
                bu=bu,
                is_derived=is_derived,
            ))

        return self.assemble_scenario(
            name=scenario_name,
            description=scenario_desc,
            quarter_payloads=quarter_payloads,
            monthly_capacity=self.compute_monthly_capacity(
                ae_overrides,
                runtime_snapshot=runtime_snapshot,
            ),
            overflow_mode=overflow_mode,
            overrides=self._build_overrides(
                ae_overrides=ae_overrides,
                conversion_overrides=conversion_overrides,
                overflow_mode=overflow_mode,
            ),
            runtime_snapshot=runtime_snapshot,
        )

    def compute_trajectory(
        self,
        overflow_mode: str = "push",
        quarterly_overrides: Optional[dict] = None,
        scenario_name: str = "Trajectory",
        scenario_desc: str = "Capacity-driven: AE roster × observed productivity + MQL trend",
        runtime_snapshot: Any | None = None,
    ) -> Any:
        """Compute the trajectory scenario.

        Args:
            overflow_mode: "push" or "lost" for capacity ceiling.
            quarterly_overrides: Per-quarter overrides, e.g.::

                {
                    "Q2FY26": {"s0_to_s1": 0.68, "ae_month_targets": [18, 20, 24]},
                    "Q3FY26": {"s1_to_s2": 0.37, "ae_month_targets": [25, 26, 27]},
                }

                Supported keys per quarter: s0_to_s1, s1_to_s2, mql_to_s0,
                avg_deal_size, ae_month_targets (preferred), add_aes
                (legacy cumulative), mql_change_pct.
                Q1FY26 overrides are ignored (locked to observed actuals).
            scenario_name: Name for the output scenario.
            scenario_desc: Description for the output scenario.
        """
        from gtm_model.trajectory import build_trajectory_pipeline_creation

        as_of = runtime_snapshot.as_of if runtime_snapshot is not None else date.today()
        trajectory_ae_overrides = self._build_trajectory_ae_overrides(quarterly_overrides)

        if runtime_snapshot is not None and trajectory_ae_overrides is None:
            roster = runtime_snapshot.trajectory_roster
            roster_meta = runtime_snapshot.trajectory_roster_meta
            ae_productivity = runtime_snapshot.observed_ae_productivity
            observed_ramp = runtime_snapshot.observed_ae_ramp_curve
            trailing_mql_weekly, mql_signal_source = runtime_snapshot.trailing_mql_weekly_signal
            runtime_rates = runtime_snapshot.runtime_funnel_rates
        else:
            roster, roster_meta = self._load_roster(ae_overrides=trajectory_ae_overrides)
            ae_productivity = self.get_observed_ae_productivity(roster, as_of)
            observed_ramp = self.get_observed_ae_ramp_curve(roster, as_of)
            trailing_mql_weekly, mql_signal_source = self.get_trailing_mql_weekly_signal(as_of)
            runtime_rates = self.get_runtime_funnel_rates()
        observed_ae_productivity = ae_productivity["productivity"]
        trailing_ae_sourced_s0s = ae_productivity["s0_count"]
        trailing_ramped_ae_months = ae_productivity["ramped_ae_months"]
        ae_productivity_source = ae_productivity["source"]
        if (observed_ae_productivity is None or observed_ae_productivity <= 0.0) and not trailing_mql_weekly:
            logger.info(
                "Trajectory fallback: using plan pipeline (reason: no observed AE productivity or MQL signal)"
            )
            return self.compute_plan_scenario(
                scenario_name="Trajectory (plan fallback)",
                overflow_mode=overflow_mode,
                runtime_snapshot=runtime_snapshot,
            )

        funnel_cfg = self.get_assumptions().get("funnel", {})
        attrition_cfg = self.get_assumptions().get("attrition", {})
        annual_attrition = float(attrition_cfg.get("ae_monthly", 0.012)) * 12
        avg_deal_size = float(funnel_cfg.get("avg_acv", 300_000))

        # Fetch monthly MQL actuals for splicing into the EWMA projection
        fy_start = self.quarter_dates[self.quarters[0]][0]
        if runtime_snapshot is not None:
            monthly_mql_actuals = getattr(runtime_snapshot, "monthly_mql_actuals", None)
            partial_month_index = getattr(runtime_snapshot, "mql_partial_month_index", None)
        else:
            monthly_mql_actuals, partial_month_index = self.get_monthly_mql_actuals(
                as_of=as_of,
                fy_start=fy_start,
            )

        trajectory = build_trajectory_pipeline_creation(
            roster=roster,
            as_of=as_of,
            months=12,
            observed_ae_productivity=observed_ae_productivity,
            trailing_ae_sourced_s0s=trailing_ae_sourced_s0s,
            trailing_ramped_ae_months=trailing_ramped_ae_months,
            trailing_mql_weekly=trailing_mql_weekly,
            annual_attrition_rate=annual_attrition,
            avg_deal_size=avg_deal_size,
            mql_to_s0=runtime_rates["mql_to_s0"],
            s0_to_s1=runtime_rates["s0_to_s1"],
            s1_to_s2=runtime_rates["s1_to_s2"],
            ramp_curves_by_segment=observed_ramp.get("curve_by_segment"),
            ramp_curve_source=observed_ramp.get("source", "config"),
            ramp_curve_reason=observed_ramp.get("reason", ""),
            ramp_curve_sample_sizes=observed_ramp.get("sample_sizes"),
            include_planned=False,          # confirmed hires only
            extrapolate_hiring=False,       # no velocity extrapolation
            monthly_mql_actuals=monthly_mql_actuals,
            mql_partial_month_index=partial_month_index,
        )

        ae_stream_source = "observed"
        if observed_ae_productivity is None or observed_ae_productivity <= 0.0:
            config_streams = self.build_config_sales_led_stream_fallbacks()
            trajectory.monthly_ae_s2_creation = list(config_streams.get("ae_selfgen", [0.0] * 12))
            trajectory.provenance.fallback_used = True
            trajectory.provenance.fallback_reason = "config_ae_selfgen_fallback"
            ae_stream_source = "config_fallback"

        # Legacy cumulative add_aes overrides still mutate the trajectory
        # vectors directly. Month-grain ae_month_targets now flow through the
        # adjusted roster path above so trajectory and capacity share one seat
        # model.
        if quarterly_overrides and trajectory_ae_overrides is None:
            self._apply_ae_hire_overrides_to_trajectory(
                trajectory=trajectory,
                quarterly_overrides=quarterly_overrides,
                as_of=as_of,
                observed_ae_productivity=observed_ae_productivity or 0.0,
                runtime_rates=runtime_rates,
                avg_deal_size=avg_deal_size,
            )

        trajectory.monthly_s2_creation = [
            ae_val + mql_val
            for ae_val, mql_val in zip(
                trajectory.monthly_ae_s2_creation,
                trajectory.monthly_mql_s2_creation,
            )
        ]

        # PLG bottoms-up from self-serve opportunity velocity
        plg_quarterly_override, plg_source = self._compute_plg_from_self_serve(
            self_serve_velocity=runtime_snapshot.self_serve_velocity if runtime_snapshot is not None else None,
        )

        quarter_payloads = self._build_trajectory_quarter_payloads(
            trajectory=trajectory,
            runtime_rates=runtime_rates,
            avg_deal_size=avg_deal_size,
            overflow_mode=overflow_mode,
            as_of=as_of,
            plg_quarterly_override=plg_quarterly_override,
            observed_plg_source=plg_source,
            quarterly_overrides=quarterly_overrides,
            runtime_snapshot=runtime_snapshot,
        )

        # Build ae_overrides for the capacity ceiling when quarterly add_aes
        # overrides are present.  The peak cumulative AE addition is used so
        # the capacity ceiling in later quarters isn't the binding constraint
        # on the increased pipeline.
        capacity_ae_overrides = trajectory_ae_overrides
        if quarterly_overrides and capacity_ae_overrides is None:
            cumulative = 0
            for q in self.quarters:
                cumulative += int((quarterly_overrides.get(q, {}) or {}).get("add_aes", 0))
            if cumulative > 0:
                capacity_ae_overrides = {"add_aes": cumulative}

        return self.assemble_scenario(
            name=scenario_name,
            description=scenario_desc,
            quarter_payloads=quarter_payloads,
            monthly_capacity=self.compute_monthly_capacity(
                capacity_ae_overrides,
                runtime_snapshot=runtime_snapshot,
            ),
            overflow_mode=overflow_mode,
            provenance_updates={
                **trajectory.provenance.to_dict(exclude={
                    "ramp_curve_source", "ramp_curve_reason",
                    "ramp_curve_by_segment", "ramp_curve_sample_sizes",
                    "fallback_reason",
                }),
                # Inline-computed fields (not on dataclass)
                "pipeline_source": "trajectory",
                "roster_source": roster_meta.get("source", "roster.yaml"),
                "ae_productivity_source": ae_productivity_source,
                "ae_stream_source": ae_stream_source,
                "mql_signal_source": mql_signal_source,
                "plg_source": plg_source,
                "quarterly_overrides": quarterly_overrides,
                "ae_override_contract": (
                    "month_targets" if trajectory_ae_overrides and "month_targets" in trajectory_ae_overrides else None
                ),
                # Renamed projections of dataclass fields
                "ae_ramp_curve_source": trajectory.provenance.ramp_curve_source,
                "ae_ramp_curve_reason": trajectory.provenance.ramp_curve_reason,
                "ae_ramp_curve": trajectory.provenance.ramp_curve_by_segment,
                "ae_ramp_curve_sample_sizes": trajectory.provenance.ramp_curve_sample_sizes,
                "trajectory_fallback_reason": trajectory.provenance.fallback_reason,
            },
            runtime_snapshot=runtime_snapshot,
        )

    def _should_use_warehouse(self) -> bool:
        """Decide whether the plan scenario should use warehouse-backed actuals."""
        freshness = self.try_cdw_freshness()
        use_warehouse = bool(freshness)
        if freshness:
            try:
                from gtm_model.data_health import assess_freshness

                assessment = assess_freshness(freshness)
                use_warehouse = assessment.get("use_warehouse", True)
            except Exception:
                use_warehouse = True
        return use_warehouse

    def _resolve_cdw_conversion_overrides(
        self,
        quarter: str,
        use_warehouse: bool,
        conversion_overrides: Optional[dict],
    ) -> Optional[dict]:
        """Fetch warehouse-backed conversion overrides for config-mode future quarters."""
        if not use_warehouse or conversion_overrides is not None:
            return conversion_overrides

        resolved = conversion_overrides
        try:
            cdw = self.get_cdw()
            if not cdw:
                return resolved

            per_deal = cdw.get_per_deal_funnel_rates()
            if per_deal:
                resolved = {}
                for key in ("s0_to_s1", "s1_to_s2"):
                    entry = per_deal.get(key)
                    if entry and entry.get("rate") is not None:
                        resolved[key] = entry["rate"]

            if resolved is not None:
                mart_rates = cdw.get_quarter_velocity_rates(quarter=quarter)
                mql_entry = (mart_rates or {}).get("mql_to_s0", {})
                if mql_entry and mql_entry.get("rate") is not None:
                    resolved["mql_to_s0"] = mql_entry["rate"]
        except Exception:
            pass

        return resolved

    def _compute_plg_from_self_serve(self, self_serve_velocity: Optional[dict] = None) -> tuple[dict[str, float], str]:
        """Try to compute PLG quarterly forecasts from self-serve opp velocity.

        Returns:
            (quarterly_override_dict, source_label)
            quarterly_override_dict maps quarter names (e.g. "Q1FY26") to
            projected PLG ARR for that quarter.  Empty dict means fallback
            to config targets.
        """
        ss_velocity = self_serve_velocity if self_serve_velocity is not None else self.get_self_serve_velocity()
        ss_weekly = ss_velocity.get("weekly_creation", [])

        if not ss_weekly or len(ss_weekly) < 4:
            return {}, "no_observed_data"

        from gtm_model.trajectory import compute_ewma_projection

        weekly_arr_values = [w.get("arr", 0) for w in ss_weekly]
        projected_monthly, _ = compute_ewma_projection(
            weekly_values=weekly_arr_values,
            months=12,
            alpha=0.3,
            growth_cap=0.15,
            trend_horizon=0,  # Architectural decision: conservative flat-carry, consistent with MQL
        )

        # Apply observed win rate as a haircut on projected creation ARR
        win_rate = ss_velocity.get("win_rate", 1.0)
        projected_monthly = [v * win_rate for v in projected_monthly]

        # Distribute monthly projections to quarters
        fy_start = self.quarter_dates[self.quarters[0]][0]  # First quarter start
        plg_quarterly: dict[str, float] = {}
        for q_name in self.quarters:
            q_start, q_end = self.quarter_dates[q_name]
            q_total = 0.0
            for month_idx in range(12):
                raw_month = fy_start.month + month_idx - 1
                month_date = date(
                    fy_start.year + raw_month // 12,
                    raw_month % 12 + 1,
                    1,
                )
                if q_start <= month_date <= q_end:
                    if month_idx < len(projected_monthly):
                        q_total += projected_monthly[month_idx]
            plg_quarterly[q_name] = q_total

        source_name = str(ss_velocity.get("source", "") or "").strip().lower()
        if source_name.startswith("warehouse"):
            plg_source = "warehouse_observed"
        elif source_name.startswith("crm"):
            plg_source = "crm_observed"
        else:
            plg_source = "observed"

        return plg_quarterly, plg_source

    def _build_trajectory_ae_overrides(self, quarterly_overrides: Optional[dict]) -> Optional[dict]:
        """Normalize quarter payloads into month-grain AE seat targets.

        The preferred backend contract is explicit month-level AE seat targets,
        matching the Scenario Planner. Legacy add_aes overrides remain supported
        separately and are handled downstream for backward compatibility.
        """
        if not quarterly_overrides:
            return None

        month_targets: dict[str, int] = {}
        for quarter in self.quarters:
            if quarter == "Q1FY26":
                continue
            q_overrides = quarterly_overrides.get(quarter, {}) or {}
            raw_targets = q_overrides.get("ae_month_targets")
            if raw_targets is None:
                raw_targets = q_overrides.get("aeMonthTargets")
            if not isinstance(raw_targets, (list, tuple)) or not raw_targets:
                continue

            quarter_start = self.quarter_dates[quarter][0]
            for month_offset, raw_target in enumerate(list(raw_targets)[:3]):
                target = int(raw_target or 0)
                if target <= 0:
                    continue
                month_index = quarter_start.month - 1 + month_offset
                month = date(
                    quarter_start.year + month_index // 12,
                    month_index % 12 + 1,
                    1,
                )
                month_targets[month.isoformat()] = target

        if month_targets:
            return {"month_targets": month_targets}
        return None

    def _apply_ae_hire_overrides_to_trajectory(
        self,
        trajectory: Any,
        quarterly_overrides: dict,
        as_of: date,
        observed_ae_productivity: float,
        runtime_rates: dict[str, float],
        avg_deal_size: float,
    ) -> None:
        """Mutate trajectory monthly vectors to add cumulative phantom AE production.

        add_aes overrides are CUMULATIVE: adding 2 in Q2 means Q3 and Q4
        also have those 2 extra AEs.  Each phantom AE starts at month 1
        ramp on the first day of the override quarter.

        Modifies trajectory.monthly_ae_s2_creation in place.
        """
        s0_to_s1 = runtime_rates["s0_to_s1"]
        s1_to_s2 = runtime_rates["s1_to_s2"]
        productivity = observed_ae_productivity or 0.0
        if productivity <= 0.0:
            return  # No observed productivity — phantom AEs would produce $0

        # Build cumulative phantom AE count per month (0-indexed from as_of month).
        # A phantom AE added in Q2 (May) produces from month 3 onward (May is
        # month index 2 if as_of is March, etc.).
        current_month = date(as_of.year, as_of.month, 1)
        phantom_aes_cumulative = [0] * 12
        cumulative = 0
        for quarter in self.quarters:
            if quarter == "Q1FY26":
                continue  # Q1 locked to actuals
            q_overrides = quarterly_overrides.get(quarter, {})
            q_add = int(q_overrides.get("add_aes", 0))
            if q_add <= 0:
                continue
            cumulative += q_add
            q_start = self.quarter_dates[quarter][0]
            # Map quarter start to trajectory month index
            start_idx = (
                (q_start.year - current_month.year) * 12
                + (q_start.month - current_month.month)
            )
            for m in range(max(0, start_idx), 12):
                phantom_aes_cumulative[m] += q_add

        # Add phantom production with ramp curve applied.
        # Each phantom AE cohort ramps from their hire quarter start, using
        # the same ramp curve as real hires (config or observed).
        from gtm_model.roster import _get_ramp_factor

        # Track per-cohort start months so we can apply ramp correctly
        cohort_starts: list[tuple[int, int]] = []  # (start_month_idx, ae_count)
        for quarter in self.quarters:
            if quarter == "Q1FY26":
                continue
            q_add = int((quarterly_overrides.get(quarter, {}) or {}).get("add_aes", 0))
            if q_add <= 0:
                continue
            q_start = self.quarter_dates[quarter][0]
            start_idx = (
                (q_start.year - current_month.year) * 12
                + (q_start.month - current_month.month)
            )
            cohort_starts.append((max(0, start_idx), q_add))

        for m in range(12):
            extra_s2_dollars = 0.0
            for cohort_start, cohort_count in cohort_starts:
                if m < cohort_start:
                    continue  # Cohort hasn't started yet
                months_since_hire = m - cohort_start
                ramp = _get_ramp_factor("enterprise", months_since_hire)
                extra_s0s = productivity * cohort_count * ramp
                extra_s2_dollars += extra_s0s * s0_to_s1 * s1_to_s2 * avg_deal_size
            if extra_s2_dollars > 0:
                trajectory.monthly_ae_s2_creation[m] += extra_s2_dollars

    def _build_trajectory_quarter_payloads(
        self,
        trajectory: Any,
        runtime_rates: dict[str, float],
        avg_deal_size: float,
        overflow_mode: str,
        as_of: date,
        plg_quarterly_override: Optional[dict[str, float]] = None,
        observed_plg_source: str = "observed",
        quarterly_overrides: Optional[dict] = None,
        runtime_snapshot: Any | None = None,
    ) -> list[dict]:
        """Translate a 12-month trajectory vector back into quarter payloads.

        When *quarterly_overrides* is provided, per-quarter conversion rates,
        deal sizes, and MQL scaling are applied before computing the bottoms-up
        payload for each quarter.  Q1FY26 overrides are ignored (locked to
        observed actuals).
        """
        quarter_payloads: list[dict] = []
        base_s0_to_s1 = runtime_rates["s0_to_s1"]
        base_s1_to_s2 = runtime_rates["s1_to_s2"]
        base_mql_to_s0 = runtime_rates["mql_to_s0"]

        # Get rate provenance for conversion_rates display 
        rate_descriptors = (
            runtime_snapshot.runtime_funnel_rate_descriptions
            if runtime_snapshot is not None
            else self.describe_runtime_funnel_rates()
        )

        for index, quarter in enumerate(self.quarters):
            td = self.get_td_quarter(quarter)
            td, is_derived = self.derive_weekly_targets(quarter, td)

            # Resolve effective rates for this quarter, applying overrides
            # for Q2-Q4 when present.
            q_overrides: dict = {}
            if quarterly_overrides and quarter != "Q1FY26":
                q_overrides = quarterly_overrides.get(quarter, {})

            eff_s0_to_s1 = float(q_overrides.get("s0_to_s1", base_s0_to_s1))
            eff_s1_to_s2 = float(q_overrides.get("s1_to_s2", base_s1_to_s2))
            eff_mql_to_s0 = float(q_overrides.get("mql_to_s0", base_mql_to_s0))
            eff_deal_size = float(q_overrides.get("avg_deal_size", avg_deal_size))
            eff_s2_dollar_factor = eff_deal_size * eff_s0_to_s1 * eff_s1_to_s2

            # Apply MQL volume scaling if requested for this quarter.
            # mql_change_pct of 0.15 means +15% MQL volume.
            mql_change_pct = float(q_overrides.get("mql_change_pct", 0.0))
            effective_trajectory = trajectory
            if mql_change_pct != 0.0:
                effective_trajectory = self._scale_trajectory_mql_for_quarter(
                    trajectory=trajectory,
                    quarter=quarter,
                    mql_change_pct=mql_change_pct,
                    as_of=as_of,
                )

            projection_override = self._build_trajectory_projection_override(
                trajectory=effective_trajectory,
                quarter_start=self.quarter_dates[quarter][0],
                td=td,
                mql_to_s0=eff_mql_to_s0,
                s0_to_s1=eff_s0_to_s1,
                s1_to_s2=eff_s1_to_s2,
                s2_dollar_factor=eff_s2_dollar_factor,
                as_of=as_of,
            )

            # When per-quarter rate/deal-size overrides change the funnel
            # factors, scale the dollar creation vectors so the downstream
            # bottoms-up math uses the adjusted pipeline amounts.
            if q_overrides:
                base_ae_factor = avg_deal_size * base_s0_to_s1 * base_s1_to_s2
                eff_ae_factor = eff_deal_size * eff_s0_to_s1 * eff_s1_to_s2
                base_mql_factor = base_mql_to_s0 * base_ae_factor
                eff_mql_factor = eff_mql_to_s0 * eff_ae_factor

                ae_scale = eff_ae_factor / base_ae_factor if base_ae_factor else 1.0
                mql_scale = eff_mql_factor / base_mql_factor if base_mql_factor else 1.0

                if abs(ae_scale - 1.0) > 1e-9:
                    ae_stream = projection_override.get("ae_selfgen", {})
                    ae_stream["monthly_creation"] = [
                        v * ae_scale for v in ae_stream.get("monthly_creation", [])
                    ]
                if abs(mql_scale - 1.0) > 1e-9:
                    mql_stream = projection_override.get("marketing_sdr", {})
                    mql_stream["monthly_creation"] = [
                        v * mql_scale for v in mql_stream.get("monthly_creation", [])
                    ]

                # Recompute total_monthly_creation from the adjusted streams
                ae_creation = projection_override.get("ae_selfgen", {}).get("monthly_creation", [0, 0, 0])
                mql_creation = projection_override.get("marketing_sdr", {}).get("monthly_creation", [0, 0, 0])
                projection_override["total_monthly_creation"] = [
                    a + m for a, m in zip(ae_creation, mql_creation)
                ]

            # Determine PLG override for this quarter.
            # Trajectory principle: never silently inject plan targets as if observed.
            # If no self-serve data exists, PLG = $0 with a warning, not the plan target.
            if plg_quarterly_override and quarter in plg_quarterly_override:
                plg_override = plg_quarterly_override[quarter]
                plg_source = observed_plg_source
            else:
                plg_override = 0.0  # No observed data → $0, not plan target
                plg_source = "no_observed_data"

            bu = self.config_driven_bottoms_up(
                quarter=quarter,
                td=td,
                overflow_mode=overflow_mode,
                monthly_creation_override=projection_override,
                plg_override=plg_override,
                runtime_snapshot=runtime_snapshot,
            )
            bu["plg_source"] = plg_source

            # Overlay weighted blend provenance into conversion_rates .
            # The config_driven_bottoms_up sets plan-derived rates; if the
            # runtime resolver used Salesforce blended cohort data, reflect
            # that here so the UI shows the correct source.
            bu_cr = bu.get("conversion_rates", {})
            for cr_key in ("s0_to_s1", "s1_to_s2"):
                desc = rate_descriptors.get(cr_key, {})
                if desc.get("source") == "blended_cohort":
                    bu_cr.setdefault(cr_key, {})["blended"] = {
                        "rate": desc["value"],
                        "n": desc.get("n", 0),
                        "source": "blended_cohort",
                        "methodology": desc.get("methodology", "weighted_blend_mature_cohort"),
                        "qualifying_months": desc.get("qualifying_months", 0),
                    }
            bu["conversion_rates"] = bu_cr

            start, end = self.quarter_dates[quarter]
            quarter_payloads.append(self._quarter_payload(
                quarter=quarter,
                start=start,
                end=end,
                td=td,
                bu=bu,
                is_derived=is_derived,
            ))

        return quarter_payloads

    def _scale_trajectory_mql_for_quarter(
        self,
        trajectory: Any,
        quarter: str,
        mql_change_pct: float,
        as_of: date,
    ) -> Any:
        """Return a shallow copy of trajectory with MQL volumes scaled for one quarter.

        Does NOT mutate the original trajectory — creates a copy with adjusted
        monthly_mql_volume and monthly_mql_s2_creation for the affected months.
        monthly_s2_creation is NOT recomputed here (it is rebuilt from the
        projection override in _build_trajectory_projection_override).
        """
        import copy as copy_mod

        scaled = copy_mod.copy(trajectory)
        scaled.monthly_mql_volume = list(trajectory.monthly_mql_volume)
        scaled.monthly_mql_s2_creation = list(trajectory.monthly_mql_s2_creation)
        scaled.monthly_s2_creation = list(trajectory.monthly_s2_creation)
        scaled.monthly_ae_s2_creation = list(trajectory.monthly_ae_s2_creation)

        current_month = date(as_of.year, as_of.month, 1)
        q_start = self.quarter_dates[quarter][0]
        scale_factor = 1.0 + mql_change_pct

        for month_offset in range(3):
            target_month_index = q_start.month - 1 + month_offset
            target_month = date(
                q_start.year + target_month_index // 12,
                target_month_index % 12 + 1,
                1,
            )
            idx = (
                (target_month.year - current_month.year) * 12
                + (target_month.month - current_month.month)
            )
            if 0 <= idx < len(scaled.monthly_mql_volume):
                scaled.monthly_mql_volume[idx] *= scale_factor
            if 0 <= idx < len(scaled.monthly_mql_s2_creation):
                scaled.monthly_mql_s2_creation[idx] *= scale_factor

        return scaled

    def _build_trajectory_projection_override(
        self,
        trajectory: Any,
        quarter_start: date,
        td: dict,
        mql_to_s0: float,
        s0_to_s1: float,
        s1_to_s2: float,
        s2_dollar_factor: float,
        as_of: date,
    ) -> dict:
        """Build the synthetic config-style projection payload for one trajectory quarter."""
        q_creation = self._slice_fiscal_quarter_months(
            trajectory.monthly_s2_creation,
            as_of=as_of,
            quarter_start=quarter_start,
        )
        q_ae_creation = self._slice_fiscal_quarter_months(
            trajectory.monthly_ae_s2_creation,
            as_of=as_of,
            quarter_start=quarter_start,
        )
        q_mql_creation = self._slice_fiscal_quarter_months(
            trajectory.monthly_mql_s2_creation,
            as_of=as_of,
            quarter_start=quarter_start,
        )
        q_mql_volume = self._slice_fiscal_quarter_months(
            trajectory.monthly_mql_volume,
            as_of=as_of,
            quarter_start=quarter_start,
        )

        q_mql_s0 = [value * mql_to_s0 for value in q_mql_volume]
        q_mql_s1 = [value * s0_to_s1 for value in q_mql_s0]
        q_mql_s2 = [value * s1_to_s2 for value in q_mql_s1]

        if s2_dollar_factor > 0:
            q_ae_s0 = [value / s2_dollar_factor for value in q_ae_creation]
        else:
            q_ae_s0 = [0.0, 0.0, 0.0]
        q_ae_s1 = [value * s0_to_s1 for value in q_ae_s0]
        q_ae_s2 = [value * s1_to_s2 for value in q_ae_s1]

        weeks_in_quarter = float(td.get("weeks_in_quarter", 13) or 13)
        return {
            "marketing_sdr": {
                "stream_key": "marketing_sdr",
                "display_name": "Marketing / SDR",
                "input_label": "MQLs",
                "weekly_input": sum(q_mql_volume) / weeks_in_quarter,
                "weekly_s0_count": sum(q_mql_s0) / weeks_in_quarter,
                "weekly_s1_count": sum(q_mql_s1) / weeks_in_quarter,
                "weekly_s2_count": sum(q_mql_s2) / weeks_in_quarter,
                "monthly_input": q_mql_volume,
                "monthly_s0_count": q_mql_s0,
                "monthly_s1_count": q_mql_s1,
                "monthly_s2_count": q_mql_s2,
                "monthly_creation": q_mql_creation,
            },
            "ae_selfgen": {
                "stream_key": "ae_selfgen",
                "display_name": "AE Self-Gen",
                "input_label": "S0s",
                "weekly_input": sum(q_ae_s0) / weeks_in_quarter,
                "weekly_s0_count": sum(q_ae_s0) / weeks_in_quarter,
                "weekly_s1_count": sum(q_ae_s1) / weeks_in_quarter,
                "weekly_s2_count": sum(q_ae_s2) / weeks_in_quarter,
                "monthly_input": q_ae_s0,
                "monthly_s0_count": q_ae_s0,
                "monthly_s1_count": q_ae_s1,
                "monthly_s2_count": q_ae_s2,
                "monthly_creation": q_ae_creation,
            },
            "plg": {
                "stream_key": "plg",
                "display_name": "PLG",
                "input_label": "Signups",
                "weekly_input": 0.0,
                "weekly_s0_count": 0.0,
                "weekly_s1_count": 0.0,
                "weekly_s2_count": 0.0,
                "monthly_input": [0.0, 0.0, 0.0],
                "monthly_s0_count": [0.0, 0.0, 0.0],
                "monthly_s1_count": [0.0, 0.0, 0.0],
                "monthly_s2_count": [0.0, 0.0, 0.0],
                "monthly_creation": [0.0, 0.0, 0.0],
            },
            "total_monthly_creation": q_creation,
            "total_weekly_s0_count": (sum(q_mql_s0) + sum(q_ae_s0)) / weeks_in_quarter,
            "total_weekly_s1_count": (sum(q_mql_s1) + sum(q_ae_s1)) / weeks_in_quarter,
            "total_weekly_s2_count": (sum(q_mql_s2) + sum(q_ae_s2)) / weeks_in_quarter,
            "_trajectory_override": True,
        }

    def _load_roster(self, ae_overrides: Optional[dict] = None) -> tuple[dict, dict]:
        """Load roster data for trajectory, preferring the live merged roster path."""
        return load_trajectory_roster_snapshot(
            live_roster=self.try_roster(ae_overrides),
            config_dir=self.get_config_dir(),
        )

    def _quarter_payload(
        self,
        quarter: str,
        start: date,
        end: date,
        td: dict,
        bu: dict,
        is_derived: bool,
    ) -> dict:
        """Build one quarter payload for downstream scenario assembly."""
        return {
            "quarter": quarter,
            "start": start,
            "end": end,
            "td": td,
            "bu": bu,
            "confidence_tier": self.assign_confidence_tier(quarter),
            "is_derived": is_derived,
        }

    @staticmethod
    def _slice_three_months(values: list[float], start_idx: int) -> list[float]:
        """Return a 3-month slice padded with zeros."""
        window = list(values[start_idx:start_idx + 3])
        while len(window) < 3:
            window.append(0.0)
        return window

    @staticmethod
    def _slice_fiscal_quarter_months(
        values: list[float],
        as_of: date,
        quarter_start: date,
    ) -> list[float]:
        """Map trajectory months to a fiscal quarter by calendar month.

        The trajectory vector starts at the current calendar month, while the
        fiscal-year rollforward is anchored to fixed FY months. We therefore
        align by month label, not raw position, so Q4 maps to Nov-Dec-Jan
        rather than the 10th-12th elements of a March-start vector.
        """
        current_month = date(as_of.year, as_of.month, 1)
        quarter_month = date(quarter_start.year, quarter_start.month, 1)
        window: list[float] = []

        for month_offset in range(3):
            target_month_index = quarter_month.month - 1 + month_offset
            target_month = date(
                quarter_month.year + target_month_index // 12,
                target_month_index % 12 + 1,
                1,
            )
            idx = (
                (target_month.year - current_month.year) * 12
                + (target_month.month - current_month.month)
            )
            if 0 <= idx < len(values):
                window.append(float(values[idx] or 0.0))
            else:
                window.append(0.0)

        return window

    @staticmethod
    def _build_overrides(
        ae_overrides: Optional[dict],
        conversion_overrides: Optional[dict],
        overflow_mode: str,
    ) -> dict:
        """Capture applied scenario overrides for downstream reporting."""
        overrides: dict = {}
        if ae_overrides:
            overrides["ae"] = ae_overrides
        if conversion_overrides:
            overrides["conversion"] = conversion_overrides
        if overflow_mode != "push":
            overrides["overflow_mode"] = overflow_mode
        return overrides
