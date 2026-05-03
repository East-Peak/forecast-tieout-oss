"""
Planning Tie-Out Engine — warehouse-powered full-funnel model.

A three-source pipeline model flowing through a cohort decay curve with a
capacity ceiling:

    warehouse actuals -> funnel_engine -> cohort_model -> roster -> comparison

Trajectory is the default forecast path; QuarterTieout, ScenarioResult, and
TieoutResult are the public data structures.

Gracefully falls back to config-driven computation when the warehouse is
unavailable.

Usage:
    from gtm_model.tieout import PlanningTieout, TieoutResult

    tieout = PlanningTieout()
    result = tieout.compute_full()
    print(result.primary_scenario.name)

    # Flex the archived plan scenario
    flexed = tieout.flex(add_aes=5, s2_conversion=0.22)
    print(flexed.summary())
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from gtm_model.tieout.infra.bootstrap import bootstrap_tieout_owner
from gtm_model.tieout.views.recommendations import format_money
from gtm_model.tieout.types import MonthlyCapacityRow, QuarterTieout, ScenarioResult, TieoutResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class PlanningTieout:
    """
    Planning Tie-Out Engine v2.

    warehouse-powered full-funnel model:
        warehouse actuals -> funnel_engine -> cohort_model -> roster -> comparison

    Falls back to config-driven computation when warehouse is unavailable.
    """

    QUARTER_DATES = {
        "Q1FY26": (date(2026, 2, 1), date(2026, 4, 30)),
        "Q2FY26": (date(2026, 5, 1), date(2026, 7, 31)),
        "Q3FY26": (date(2026, 8, 1), date(2026, 10, 31)),
        "Q4FY26": (date(2026, 11, 1), date(2027, 1, 31)),
    }

    QUARTERS = ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        plan_case_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ):
        bootstrap_tieout_owner(
            owner=self,
            config_dir=config_dir,
            plan_case_id=plan_case_id,
            profile_id=profile_id,
            logger=logger,
        )

    def _get_sf(self):
        """Lazy-init Salesforce connector on first access.

        ARCHITECTURE.md: When the active profile declares a data_access
        block (CSV / custom backend), we DO NOT touch Salesforce — that
        would silently mix the legacy connector's data into a profile
        that's supposed to be backend-only. Returns None instead.
        """
        if self._profile_uses_data_access_block():
            return None
        return self.connector_gateway.get_sf_connector()

    def _profile_uses_data_access_block(self) -> bool:
        """True when profile.yaml declares ARCHITECTURE.md data_access block.

        Once a profile opts into the new pluggable data_access seam, the
        legacy warehouse + SF gateway must NOT silently augment its snapshots
        with data from those source systems. This method gates that.
        """
        profile = getattr(self, "profile", None)
        if profile is None:
            return False
        return bool(getattr(profile, "data_access", None))

    def _get_profile_backend(self):
        """Lazy-resolve the ProfileBackend from the active OrgProfile.

        Returns None when the profile uses legacy `connector` + `data_dir`
        fields and hasn't migrated to ARCHITECTURE.md's `data_access` block. In
        that case the engine falls back to the existing warehouse/SF gateway.
        Cached on first access.
        """
        if not hasattr(self, "_profile_backend_cache"):
            self._profile_backend_cache = None
            self._profile_backend_resolved = False
        if self._profile_backend_resolved:
            return self._profile_backend_cache
        try:
            profile = getattr(self, "profile", None)
            if profile is not None and hasattr(profile, "build_backend"):
                self._profile_backend_cache = profile.build_backend()
        except Exception as exc:
            logger.warning("ProfileBackend resolution failed: %s", exc)
            self._profile_backend_cache = None
        self._profile_backend_resolved = True
        return self._profile_backend_cache

    def _get_self_serve_velocity(self) -> dict:
        """Get trailing self-serve opportunity velocity with warehouse-first fallback."""
        return self.runtime.get_self_serve_velocity(lookback_days=180)

    def _get_cdw(self):
        """Lazy-init warehouse connector on first access.

        Uses a quick ``which snow`` check to avoid the slow subprocess
        detection inside CDWConnector when the CLI is absent.

        ARCHITECTURE.md: When the active profile declares a data_access
        block (CSV / custom backend), warehouse is intentionally skipped to
        prevent silent data-mixing. Returns None.
        """
        if self._profile_uses_data_access_block():
            return None
        return self.connector_gateway.get_cdw_connector()

    def _load_yaml(self, filename: str) -> dict:
        return self.plan_config.load_yaml(filename)

    def _deep_merge_dicts(self, base: dict, overlay: dict) -> dict:
        """Recursively merge a config overlay into the base dictionary."""
        return self.plan_config.deep_merge_dicts(base, overlay)

    def _default_plan_case_id(self) -> str:
        return self.plan_config.default_plan_case_id(self.targets_raw)

    def _resolve_targets(self, plan_case_id: Optional[str]) -> dict:
        """Resolve the active top-down plan case from targets.yaml."""
        resolved_targets, resolved_plan_case_id = self.plan_config.resolve_targets(
            self.targets_raw,
            plan_case_id,
        )
        self.plan_case_id = resolved_plan_case_id
        return resolved_targets

    def available_plan_cases(self) -> list[dict]:
        """Return selectable top-down plan cases with the default case first."""
        return self.plan_config.available_plan_cases(self.targets_raw)

    # ------------------------------------------------------------------
    # warehouse helpers (with graceful fallback)
    # ------------------------------------------------------------------

    def _get_open_inventory_snapshot(self, as_of: Optional[date] = None):
        """Return the current open opportunity inventory, preferring warehouse over Salesforce."""
        return self.data_access.get_open_inventory_snapshot(as_of=as_of)

    def _generate_staggered_start_dates(self, count: int) -> list[str]:
        """Generate staggered start dates for phantom AEs.

        Uses the planned hiring timeline from roster.yaml as the template.
        If more phantom AEs are needed than planned slots available,
        distributes the extras evenly across remaining FY months.

        Returns a list of ISO date strings, one per phantom AE.
        """
        return self.data_access.generate_staggered_start_dates(count)

    def _compute_trailing_ramped_ae_months(
        self,
        roster: dict,
        as_of: date,
        months: int = 6,
    ) -> float:
        """Approximate trailing ramp-weighted AE-months over a rolling window."""
        return self.runtime.compute_trailing_ramped_ae_months(
            roster=roster,
            as_of=as_of,
            months=months,
        )

    def _get_observed_ae_productivity(
        self,
        roster: dict,
        as_of: date,
        lookback_days: int = 180,
    ) -> dict:
        """Get trailing AE-sourced S0 productivity with warehouse-first fallback."""
        return self.runtime.get_observed_ae_productivity(
            roster=roster,
            as_of=as_of,
            lookback_days=lookback_days,
            compute_ramped_months=lambda roster_arg, as_of_arg, months_arg: self._compute_trailing_ramped_ae_months(
                roster=roster_arg,
                as_of=as_of_arg,
                months=months_arg,
            ),
        )

    def _get_observed_ae_ramp_curve(
        self,
        roster: dict,
        as_of: date,
        lookback_days: int = 365,
    ) -> dict:
        """Estimate AE time-to-productivity from observed warehouse cohort data."""
        return self.runtime.get_observed_ae_ramp_curve(
            roster=roster,
            as_of=as_of,
            lookback_days=lookback_days,
        )

    def _get_trailing_mql_weekly_signal(
        self,
        as_of: date,
        lookback_days: int = 180,
    ) -> tuple[Optional[list[float]], str]:
        """Get trailing weekly MQL volume with warehouse-first fallback."""
        return self.runtime.get_trailing_mql_weekly_signal(
            as_of=as_of,
            lookback_days=lookback_days,
        )

    def _get_monthly_mql_actuals(
        self,
        as_of: date,
        months: int = 12,
        fy_start: date | None = None,
    ) -> tuple[list, int | None]:
        """Fetch monthly MQL actuals aligned to the projection window."""
        return self.runtime.get_monthly_mql_actuals(
            as_of=as_of,
            months=months,
            fy_start=fy_start,
        )

    def _build_config_sales_led_stream_fallbacks(self) -> dict[str, list[float]]:
        """Build 12-month config-mode sales-led stream fallbacks by source."""
        return self.support.build_config_sales_led_stream_fallbacks()

    def _get_beginning_arr_snapshot(self) -> tuple[float, dict]:
        """Resolve FY beginning ARR using active won-opportunity window logic."""
        return self.data_access.get_beginning_arr_snapshot()

    def _get_closed_won_finance_summary(
        self, as_of: Optional[date] = None
    ) -> tuple[dict, dict]:
        """Return closed-won finance totals for Amount vs ARR vs NACV display."""
        return self.data_access.get_closed_won_finance_summary(as_of=as_of)

    def _default_target_provenance(self, quarter: str, wt: dict) -> dict:
        """Return a default provenance payload for a configured weekly target set."""
        return self.targets_resolver.default_target_provenance(quarter, wt)

    def _annotate_target_coherence(self, td: dict, provenance: dict) -> dict:
        """Attach reviewer-facing target-coherence diagnostics to weekly-target provenance."""
        return self.targets_resolver.annotate_target_coherence(td, provenance)

    def _normalize_s1_pipeline_by_source(self, wt: dict) -> dict:
        """Normalize configured by-source S1 pipeline values to quarterly dollars."""
        return self.targets_resolver.normalize_s1_pipeline_by_source(wt)

    # ------------------------------------------------------------------
    # Top-down extraction
    # ------------------------------------------------------------------

    def _get_td_quarter(self, quarter: str) -> dict:
        """Extract top-down targets for a quarter."""
        return self.targets_resolver.get_td_quarter(quarter)

    def _get_source_mix_shares(self, quarter: str) -> dict:
        """Return normalized source shares for marketing, SDR, and AE motions."""
        return self.targets_resolver.get_source_mix_shares(quarter)

    def _allocate_integer_mix(self, total_count: int, allocations: list[tuple[str, float]]) -> dict:
        """Convert fractional source allocations into integer counts that sum exactly."""
        return self.targets_resolver.allocate_integer_mix(total_count, allocations)

    def _resolve_s0_source_mix(self, quarter: str, td: dict) -> dict:
        """Return explicit S0 source splits, deriving them from source mix when absent."""
        return self.targets_resolver.resolve_s0_source_mix(quarter, td)

    def _estimate_ae_selfgen_s0_weekly(self, td: dict) -> int:
        """Estimate direct AE-created S0 volume for the config funnel model."""
        return self.targets_resolver.estimate_ae_selfgen_s0_weekly(td)

    def _get_config_conversion_rates(self, quarter: str, td: dict) -> dict:
        """Resolve plan conversion rates for config-mode modeling.

        Priority chain (highest wins):
            1. Per-quarter ``conversion`` dict from targets.yaml
            2. Prior-quarter ``conversion`` dict (lookback)
            3. Rate registry / config-backed runtime defaults

        Note: The runtime fallback is resolved through the rate registry so
        tieout and trajectory math share one canonical source of truth.
        """
        return self.targets_resolver.get_config_conversion_rates(quarter, td)

    # ------------------------------------------------------------------
    # Q3/Q4 weekly target derivation
    # ------------------------------------------------------------------

    def _latest_explicit_weekly_target_quarter(self, quarter: str) -> Optional[str]:
        """Return the latest earlier quarter with explicit weekly targets."""
        return self.targets_resolver.latest_explicit_weekly_target_quarter(quarter)

    def _derive_weekly_targets_from_pipeline_driver_tree(self, quarter: str, td: dict) -> Optional[dict]:
        """Derive future-quarter weekly targets from pipeline coverage and stage drivers."""
        return self.targets_resolver.derive_weekly_targets_from_pipeline_driver_tree(quarter, td)

    def _derive_weekly_targets(self, quarter: str, td: dict) -> tuple[dict, bool]:
        """
        If weekly targets are missing for later quarters, derive them from
        pipeline coverage, source mix, and recent stage relationships.

        Falls back to the older bookings-scaled derivation only if the richer
        driver tree cannot be built from the available config.

        Returns (updated td dict, is_derived).
        """
        return self.targets_resolver.derive_weekly_targets(quarter, td)

    # ------------------------------------------------------------------
    # Decay curve
    # ------------------------------------------------------------------

    def _get_registered_funnel_rate(self, key: str, default: float) -> float:
        """Resolve a funnel rate via the registry, falling back to config defaults."""
        return self.runtime.get_registered_funnel_rate(key, default)

    def _get_runtime_funnel_rates(self) -> dict[str, float]:
        """Return the canonical runtime funnel rates for tieout math."""
        return self.runtime.get_runtime_funnel_rates()

    def _describe_runtime_funnel_rates(self) -> dict[str, dict]:
        """Return runtime funnel rates with provenance metadata."""
        return self.runtime.describe_runtime_funnel_rates()

    def _get_decay_curve(self) -> list[float]:
        """Load decay curve from assumptions.yaml."""
        return self.runtime.get_decay_curve()

    def _get_rolling_s2_to_won_rate(self) -> dict:
        """Try SF trailing observed S2→Won rate, fall back to static config.

        Returns dict with keys: rate, source, sample, lookback_days.
        Cached on instance for the computation cycle.

        NOTE: quarter-bounded warehouse aggregates (s2_to_won measured as
        "deals entering S2 and closing won within the same quarter") are
        intentionally not used here — that metric undercounts deals that
        crossed quarter boundaries. Early-funnel sequential transition
        rates (mql_to_s0, s0_to_s1, s1_to_s2) ARE safe to use from such
        aggregates and are consumed elsewhere for pipeline-creation
        modeling.
        """
        return self.runtime.get_rolling_s2_to_won_rate()

    def _get_s2_to_won_rate(self) -> float:
        """Return the composite S2-to-Won conversion rate.

        Prefers rolling observed Salesforce rate when sample >= 20,
        otherwise falls back to the explicit/config composite rate.
        """
        return self.runtime.get_s2_to_won_rate()

    def _get_stage_win_rates(self) -> dict[str, float]:
        """Return stage-to-Won probabilities for open opportunity runoff."""
        return self.runtime.get_stage_win_rates(
            resolve_s2_to_won=lambda: self._get_s2_to_won_rate(),
        )

    def _rebalance_projection_pipeline_values(self, projection: dict, td: dict) -> dict:
        """Anchor config-mode pipeline dollars to implied S2 target (converted from S1 targets)."""
        return self.targets_resolver.rebalance_projection_pipeline_values(projection, td)

    def _get_observed_stage_velocity(self) -> dict:
        """Try warehouse/SF observed stage velocity, fall back to config assumptions.

        Returns dict: stage_days, source, sample_sizes.
        Uses observed data when any stage has >= 10 transitions.

        Prefers per-deal warehouse data (lifetime stage durations from raw
        opportunity rows) over quarter-bounded conversion aggregates —
        the latter undercount cross-quarter transitions.
        """
        return self.runtime.get_observed_stage_velocity()

    def _get_stage_velocity_from_cdw(self, min_sample: int) -> Optional[dict]:
        """Query the warehouse's per-deal stage-velocity mart.

        Expects pre-computed days-in-stage columns from row-level stage
        dates (per-deal lifetime metrics, safe for forecasting), not
        quarter-bounded conversion aggregates.
        """
        return self.runtime.get_stage_velocity_from_cdw(min_sample)

    def _get_stage_velocity_days(self) -> dict[str, float]:
        """Return stage-by-stage timing for inventory runoff."""
        return self.runtime.get_stage_velocity_days()

    def _get_observed_arr_movements(self) -> dict:
        """Fetch trailing-12-month ARR movements from SF when available.

        Returns dict: expansion_arr, churned_arr, contraction_arr,
        observed_annual_churn_rate, observed_annual_expansion_rate, source.
        """
        return self.runtime.get_observed_arr_movements()

    def _get_actual_decay_from_cdw(self) -> list[float]:
        """Build actual decay distribution from warehouse closed-won timing data."""
        return self.runtime.get_actual_decay_from_cdw(
            config_curve=self._get_decay_curve(),
        )

    def _get_observed_decay_curve(self) -> dict:
        """Return close-timing decay curve, preferring warehouse data when
        sample is sufficient.

        Returns dict with keys: curve (list[float]), source, sample.

        Warehouse timing should come from per-deal S2-to-Close intervals
        (row-level data), not quarter-bounded aggregates. Small samples
        produce noisy distributions, so we require >= 30 deals before
        using warehouse data over the config curve.
        """
        return self.runtime.get_observed_decay_curve(
            config_curve=self._get_decay_curve(),
        )

    def _summarize_source_breakdown(
        self,
        projections: dict,
        *,
        mode: str,
        actual_streams: Optional[dict] = None,
    ) -> dict:
        """Normalize per-stream projection detail for downstream UI/export use."""
        return self.support.summarize_source_breakdown(
            projections,
            mode=mode,
            actual_streams=actual_streams,
        )

    def _build_monthly_source_detail(self, quarter_payloads: list[dict]) -> list[dict]:
        """Expand per-quarter stream projections into one FY-wide monthly detail table."""
        return self.support.build_monthly_source_detail(quarter_payloads)

    def _project_expansion_workstream(
        self,
        quarter_payloads: list[dict],
        monthly_projection: dict,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Run the standalone expansion engine and return quarter-level detail."""
        return self.support.project_expansion_workstream(
            quarter_payloads,
            monthly_projection,
            runtime_snapshot=runtime_snapshot,
        )

    # ------------------------------------------------------------------
    # Config-driven fallback computation (no warehouse)
    # ------------------------------------------------------------------

    def _config_driven_bottoms_up(
        self,
        quarter: str,
        td: dict,
        overflow_mode: str = "push",
        conversion_overrides: Optional[dict] = None,
        ae_overrides: Optional[dict] = None,
        monthly_creation_override: Optional[list] = None,
        plg_override: Optional[float] = None,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Archived-plan computation using only config data (no warehouse)."""
        return self.archived_plan_model.config_driven(
            quarter=quarter,
            td=td,
            overflow_mode=overflow_mode,
            conversion_overrides=conversion_overrides,
            ae_overrides=ae_overrides,
            monthly_creation_override=monthly_creation_override,
            plg_override=plg_override,
            runtime_snapshot=runtime_snapshot,
        )

    # ------------------------------------------------------------------
    # warehouse-powered archived-plan computation
    # ------------------------------------------------------------------

    def _cdw_bottoms_up(
        self,
        quarter: str,
        td: dict,
        funnel_result: dict,
        overflow_mode: str = "push",
        ae_overrides: Optional[dict] = None,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Archived-plan computation from warehouse funnel data."""
        return self.archived_plan_model.cdw(
            quarter=quarter,
            td=td,
            funnel_result=funnel_result,
            overflow_mode=overflow_mode,
            ae_overrides=ae_overrides,
            runtime_snapshot=runtime_snapshot,
        )

    # ------------------------------------------------------------------
    # Confidence tier assignment
    # ------------------------------------------------------------------

    def _assign_confidence_tier(self, quarter: str) -> str:
        """
        Assign a confidence tier based on proximity to current date.

        committed — current or past quarter
        building  — next quarter
        planned   — 2+ quarters out
        """
        return self.support.assign_confidence_tier(quarter)

    # ------------------------------------------------------------------
    # Monthly capacity timeline (backward compat)
    # ------------------------------------------------------------------

    def _compute_monthly_capacity(
        self,
        ae_overrides: Optional[dict] = None,
        runtime_snapshot: Any | None = None,
    ) -> list[MonthlyCapacityRow]:
        """Compute month-by-month capacity across FY26 using roster module."""
        return self.projection.compute_monthly_capacity(
            ae_overrides=ae_overrides,
            runtime_snapshot=runtime_snapshot,
        )

    def _project_full_year_bookings(
        self,
        quarter_payloads: list[dict],
        monthly_capacity: list[MonthlyCapacityRow],
        overflow_mode: str,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Project one FY-wide roll-forward so quarter outputs share tails correctly."""
        return self.projection.project_full_year_bookings(
            quarter_payloads=quarter_payloads,
            monthly_capacity=monthly_capacity,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def _run_health_checks(self, runtime_snapshot: Any | None = None) -> dict:
        """Run all health checks. Returns {} if warehouse is unavailable."""
        return self.health_checker.run(runtime_snapshot=runtime_snapshot)

    # ------------------------------------------------------------------
    # Main computation
    # ------------------------------------------------------------------

    def compute_archived_plan(
        self,
        ae_overrides: Optional[dict] = None,
        conversion_overrides: Optional[dict] = None,
        scenario_name: str = "Archived Plan",
        scenario_desc: str = "",
        overflow_mode: str = "push",
        runtime_snapshot: Any | None = None,
    ) -> ScenarioResult:
        """
        Compute the archived plan scenario for all quarters.

        Flow:
            warehouse actuals -> funnel_engine -> cohort_model -> roster -> comparison

        This is the legacy config-driven archived-plan path retained for
        backward compatibility, flex scenarios, and gap-closing analysis.
        The trajectory scenario is the default forecast path.

        Args:
            ae_overrides: Override AE counts (e.g., {"total_aes": 30})
            conversion_overrides: Override conversion rates
            scenario_name: Name for this scenario
            scenario_desc: Description of what changed
            overflow_mode: "push" or "lost" for capacity ceiling

        Returns:
            ScenarioResult with quarterly comparisons
        """
        return self.scenarios.compute_plan(
            ae_overrides=ae_overrides,
            conversion_overrides=conversion_overrides,
            scenario_name=scenario_name,
            scenario_desc=scenario_desc,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )

    def compute(
        self,
        ae_overrides: Optional[dict] = None,
        conversion_overrides: Optional[dict] = None,
        scenario_name: str = "Archived Plan",
        scenario_desc: str = "",
        overflow_mode: str = "push",
        runtime_snapshot: Any | None = None,
    ) -> ScenarioResult:
        """Backward-compatible wrapper for the archived plan scenario."""
        return self.compute_archived_plan(
            ae_overrides=ae_overrides,
            conversion_overrides=conversion_overrides,
            scenario_name=scenario_name,
            scenario_desc=scenario_desc,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )

    def compute_trajectory(
        self,
        overflow_mode: str = "push",
        quarterly_overrides: Optional[dict] = None,
        scenario_name: str = "Trajectory",
        scenario_desc: str = "Capacity-driven: AE roster × observed productivity + MQL trend",
        runtime_snapshot: Any | None = None,
    ) -> ScenarioResult:
        """Compute the trajectory scenario: capacity-driven pipeline creation.

        Instead of config-driven S1 pipeline targets, derives pipeline creation
        from actual AE roster, observed productivity, trailing MQL volume, and
        trend extrapolation. This answers "where are we headed?" vs the plan
        scenario's "where does plan say we should be?"

        Architectural decision: docs/decisions/001-two-scenario-architecture.md
        Architectural decision: docs/decisions/003-ae-productivity-drives-pipeline.md

        Args:
            overflow_mode: "push" or "lost" for capacity ceiling.
            quarterly_overrides: Per-quarter overrides for trajectory flex.
            scenario_name: Name for the output scenario.
            scenario_desc: Description for the output scenario.

        Returns:
            ScenarioResult with trajectory-derived pipeline creation.
        """
        return self.scenarios.compute_trajectory(
            overflow_mode=overflow_mode,
            quarterly_overrides=quarterly_overrides,
            scenario_name=scenario_name,
            scenario_desc=scenario_desc,
            runtime_snapshot=runtime_snapshot,
        )

    def compute_full(
        self,
        overflow_mode: str = "push",
        runtime_snapshot: Any | None = None,
    ) -> TieoutResult:
        """Compute trajectory plus archived-plan compatibility payload."""
        return self.public_api.compute_full(
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
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
    ) -> ScenarioResult:
        """
        Flex the model with overrides and return a new scenario.

        Args:
            name: Scenario name
            description: What changed
            add_aes: Additional AEs to add to each quarter
            total_aes: Override total AE count (overrides add_aes)
            s2_conversion: Override S2->Won rate
            mql_to_s0: Override MQL->S0 rate
            s0_to_s1: Override S0->S1 rate
            s1_to_s2: Override S1->S2 rate
            attainment_rate: Override attainment rate
            overflow_mode: "push" or "lost" for capacity ceiling
            quarterly_overrides: Per-quarter overrides for trajectory flex.
                Format::

                    {
                        "Q2FY26": {"s0_to_s1": 0.68, "ae_month_targets": [18, 20, 24]},
                        "Q3FY26": {"s1_to_s2": 0.37, "ae_month_targets": [25, 26, 27]},
                    }

                Supported keys per quarter: s0_to_s1, s1_to_s2, mql_to_s0,
                avg_deal_size, ae_month_targets (preferred), add_aes
                (legacy cumulative), mql_change_pct.
                Q1FY26 overrides are ignored (locked to observed actuals).
                When provided, flex runs against the trajectory scenario.
        """
        return self.public_api.flex(
            name=name,
            description=description,
            add_aes=add_aes,
            total_aes=total_aes,
            s2_conversion=s2_conversion,
            mql_to_s0=mql_to_s0,
            s0_to_s1=s0_to_s1,
            s1_to_s2=s1_to_s2,
            attainment_rate=attainment_rate,
            overflow_mode=overflow_mode,
            quarterly_overrides=quarterly_overrides,
        )


    def gap_closing_recommendations(
        self,
        base: Optional[ScenarioResult] = None,
        overflow_mode: str = "push",
    ) -> dict:
        """Analyze the FY gap and recommend prioritized closing actions.

        Instead of just computing sensitivity on conversion toggles (which
        are absorbed by pipeline rebalancing), this does a structural
        decomposition: what portion of the gap is hiring, what portion is
        pipeline volume, and what portion is conversion / win-rate.

        Returns dict with gap, constraints, levers, and narrative.
        """
        return self.recommendations.analyze(
            base=base,
            overflow_mode=overflow_mode,
        )
