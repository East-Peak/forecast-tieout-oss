"""Helper construction wiring for Planning Tie-Out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from gtm_model.tieout.scenarios.assembly import TieoutScenarioAssembler
from gtm_model.tieout.infra.api import TieoutPublicApi
from gtm_model.tieout.scenarios.archived_plan import TieoutArchivedPlanCalculator
from gtm_model.tieout.infra.connectors import TieoutConnectorGateway
from gtm_model.tieout.infra.data_access import TieoutDataAccess
from gtm_model.tieout.infra.health import TieoutHealthChecker
from gtm_model.tieout.scenarios.projection import TieoutProjectionCalculator
from gtm_model.tieout.views.recommendations import TieoutRecommendationsAnalyzer
from gtm_model.tieout.runtime.resolver import TieoutRuntimeResolver
from gtm_model.tieout.scenarios.compute import TieoutScenarioComputer
from gtm_model.tieout.scenarios.support import TieoutSupportServices
from gtm_model.tieout.runtime.snapshot import TieoutRuntimeSnapshotBuilder
from gtm_model.tieout.targets.targets import TieoutTargetResolver
from gtm_model.tieout.types import MonthlyCapacityRow, QuarterTieout, ScenarioResult, TieoutResult


@dataclass
class TieoutComponents:
    """Typed helper bundle attached to a `PlanningTieout` instance."""

    connector_gateway: TieoutConnectorGateway
    runtime: TieoutRuntimeResolver
    scenario_assembler: TieoutScenarioAssembler
    targets_resolver: TieoutTargetResolver
    support: TieoutSupportServices
    data_access: TieoutDataAccess
    archived_plan_model: TieoutArchivedPlanCalculator
    projection: TieoutProjectionCalculator
    recommendations: TieoutRecommendationsAnalyzer
    scenarios: TieoutScenarioComputer
    public_api: TieoutPublicApi
    health_checker: TieoutHealthChecker
    snapshot_builder: TieoutRuntimeSnapshotBuilder


def build_tieout_components(
    owner: Any,
    quarter_tieout_factory: Callable[..., Any] = QuarterTieout,
    scenario_result_factory: Callable[..., Any] = ScenarioResult,
    monthly_capacity_row_factory: Callable[..., Any] = MonthlyCapacityRow,
) -> TieoutComponents:
    """Build the helper graph for a `PlanningTieout` instance."""
    connectors = TieoutConnectorGateway(owner=owner)

    runtime = TieoutRuntimeResolver(
        get_assumptions=lambda: owner.assumptions,
        get_rate_registry=lambda: owner.rate_registry,
        get_cdw=lambda: owner.cdw if owner.cdw is not None else owner._get_cdw(),
        get_sf=lambda: owner.sf if owner.sf is not None else owner._get_sf(),
        is_cdw_query_failed=lambda: owner._cdw_queries_failed,
        try_closed_won_timing=lambda: connectors.try_closed_won_timing(),
        get_closed_won_timing_source=lambda: owner._closed_won_timing_source,
        get_beginning_arr_snapshot=lambda: owner._get_beginning_arr_snapshot(),
        get_backend=lambda: getattr(owner, "_get_profile_backend", lambda: None)(),
    )

    scenario_assembler = TieoutScenarioAssembler(
        project_full_year_bookings=lambda quarter_payloads, monthly_capacity, overflow_mode, runtime_snapshot=None: owner._project_full_year_bookings(
            quarter_payloads=quarter_payloads,
            monthly_capacity=monthly_capacity,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        ),
        project_expansion_workstream=lambda quarter_payloads, monthly_projection, runtime_snapshot=None: owner._project_expansion_workstream(
            quarter_payloads,
            monthly_projection,
            runtime_snapshot=runtime_snapshot,
        ),
        get_observed_arr_movements=lambda: owner._get_observed_arr_movements(),
        get_beginning_arr_snapshot=lambda: owner._get_beginning_arr_snapshot(),
        build_monthly_source_detail=lambda quarter_payloads: owner._build_monthly_source_detail(quarter_payloads),
        quarter_tieout_factory=quarter_tieout_factory,
        scenario_result_factory=scenario_result_factory,
    )

    targets_resolver = TieoutTargetResolver(
        quarters=owner.QUARTERS,
        get_targets=lambda: owner.targets,
        get_assumptions=lambda: owner.assumptions,
        get_runtime_funnel_rates=lambda: owner._get_runtime_funnel_rates(),
        get_registered_funnel_rate=lambda key, default: owner._get_registered_funnel_rate(key, default),
    )

    support = TieoutSupportServices(
        quarter_dates=owner.QUARTER_DATES,
        quarters=owner.QUARTERS,
        get_assumptions=lambda: owner.assumptions,
        get_td_quarter=lambda quarter: owner._get_td_quarter(quarter),
        derive_weekly_targets=lambda quarter, td: owner._derive_weekly_targets(quarter, td),
        estimate_ae_selfgen_s0_weekly=lambda td: owner._estimate_ae_selfgen_s0_weekly(td),
        get_config_conversion_rates=lambda quarter, td: owner._get_config_conversion_rates(quarter, td),
        rebalance_projection_pipeline_values=lambda projection, td: owner._rebalance_projection_pipeline_values(projection, td),
        get_beginning_arr_snapshot=lambda: owner._get_beginning_arr_snapshot(),
    )

    data_access = TieoutDataAccess(
        get_config_dir=lambda: owner.config_dir,
        load_config_yaml=lambda filename: owner._load_yaml(filename),
        get_targets=lambda: owner.targets,
        get_quarter_dates=lambda: owner.QUARTER_DATES,
        get_cdw=lambda: owner.cdw if owner.cdw is not None else owner._get_cdw(),
        get_sf=lambda: owner.sf if owner.sf is not None else owner._get_sf(),
        is_cdw_query_failed=lambda: owner._cdw_queries_failed,
        get_beginning_arr_cache=lambda: owner._beginning_arr_cache,
        set_beginning_arr_cache=lambda value: setattr(owner, "_beginning_arr_cache", value),
        get_bookings_summary_cache=lambda: owner._bookings_summary_cache,
        set_bookings_summary_cache=lambda value: setattr(owner, "_bookings_summary_cache", value),
        get_roster_cache=lambda: owner._roster_cache,
        get_open_inventory_cache=lambda: owner._open_inventory_cache,
        # Architectural decision: ProfileBackend seam. Lazy-resolved via the owner so
        # backend construction can fail-soft without breaking other paths.
        get_backend=lambda: getattr(owner, "_get_profile_backend", lambda: None)(),
    )

    archived_plan_model = TieoutArchivedPlanCalculator(
        quarter_dates=owner.QUARTER_DATES,
        get_assumptions=lambda: owner.assumptions,
        get_targets=lambda: owner.targets,
        get_config_conversion_rates=lambda quarter, td: owner._get_config_conversion_rates(quarter, td),
        estimate_ae_selfgen_s0_weekly=lambda td: owner._estimate_ae_selfgen_s0_weekly(td),
        rebalance_projection_pipeline_values=lambda projection, td: owner._rebalance_projection_pipeline_values(projection, td),
        try_roster=lambda ae_overrides=None: data_access.try_roster(ae_overrides),
        get_observed_decay_curve=lambda: owner._get_observed_decay_curve(),
        get_s2_to_won_rate=lambda: owner._get_s2_to_won_rate(),
        summarize_source_breakdown=lambda projection, mode, actual_streams=None: owner._summarize_source_breakdown(
            projection,
            mode=mode,
            actual_streams=actual_streams,
        ),
        try_cdw_bookings=lambda quarter: connectors.try_cdw_bookings(quarter),
    )

    projection = TieoutProjectionCalculator(
        quarter_dates=owner.QUARTER_DATES,
        quarters=owner.QUARTERS,
        get_targets=lambda: owner.targets,
        get_assumptions=lambda: owner.assumptions,
        try_roster=lambda ae_overrides=None: data_access.try_roster(ae_overrides),
        monthly_capacity_row_factory=monthly_capacity_row_factory,
        get_s2_to_won_rate=lambda: owner._get_s2_to_won_rate(),
        get_rolling_s2_to_won_rate=lambda: owner._get_rolling_s2_to_won_rate(),
        get_observed_decay_curve=lambda: owner._get_observed_decay_curve(),
        get_open_inventory_snapshot=lambda as_of=None: owner._get_open_inventory_snapshot(as_of=as_of),
        get_stage_win_rates=lambda: owner._get_stage_win_rates(),
        get_stage_velocity_days=lambda: owner._get_stage_velocity_days(),
    )

    recommendations = TieoutRecommendationsAnalyzer(
        # Keep the compute() seam alive so late monkeypatches still work.
        compute_base=lambda overflow_mode="push": owner.compute(overflow_mode=overflow_mode),
        flex_scenario=lambda **kwargs: owner.flex(**kwargs),
        get_s2_to_won_rate=lambda: owner._get_s2_to_won_rate(),
        available_plan_cases=lambda: owner.available_plan_cases(),
        get_plan_case_id=lambda: owner.plan_case_id,
        default_plan_case_id=lambda: owner._default_plan_case_id(),
        tieout_factory=lambda plan_case_id: owner.__class__(
            config_dir=owner.config_dir,
            plan_case_id=plan_case_id,
        ),
    )

    scenarios = TieoutScenarioComputer(
        quarter_dates=owner.QUARTER_DATES,
        quarters=owner.QUARTERS,
        get_config_dir=lambda: owner.config_dir,
        get_assumptions=lambda: owner.assumptions,
        try_cdw_freshness=lambda: connectors.try_cdw_freshness(),
        get_cdw=lambda: owner._get_cdw(),
        try_funnel_from_cdw=lambda quarter: connectors.try_funnel_from_cdw(quarter),
        get_td_quarter=lambda quarter: owner._get_td_quarter(quarter),
        derive_weekly_targets=lambda quarter, td: owner._derive_weekly_targets(quarter, td),
        config_driven_bottoms_up=lambda **kwargs: owner._config_driven_bottoms_up(**kwargs),
        cdw_bottoms_up=lambda **kwargs: owner._cdw_bottoms_up(**kwargs),
        assign_confidence_tier=lambda quarter: owner._assign_confidence_tier(quarter),
        compute_monthly_capacity=lambda ae_overrides=None, runtime_snapshot=None: owner._compute_monthly_capacity(
            ae_overrides,
            runtime_snapshot=runtime_snapshot,
        ),
        assemble_scenario=lambda **kwargs: owner.scenario_assembler.assemble(**kwargs),
        get_runtime_funnel_rates=lambda: owner._get_runtime_funnel_rates(),
        describe_runtime_funnel_rates=lambda: owner._describe_runtime_funnel_rates(),
        get_observed_ae_productivity=lambda roster, as_of, lookback_days=180: owner._get_observed_ae_productivity(
            roster,
            as_of,
            lookback_days=lookback_days,
        ),
        get_observed_ae_ramp_curve=lambda roster, as_of, lookback_days=365: owner._get_observed_ae_ramp_curve(
            roster,
            as_of,
            lookback_days=lookback_days,
        ),
        get_trailing_mql_weekly_signal=lambda as_of, lookback_days=180: owner._get_trailing_mql_weekly_signal(
            as_of,
            lookback_days=lookback_days,
        ),
        get_monthly_mql_actuals=lambda as_of, months=12, fy_start=None: owner._get_monthly_mql_actuals(
            as_of, months=months, fy_start=fy_start,
        ),
        build_config_sales_led_stream_fallbacks=lambda: owner._build_config_sales_led_stream_fallbacks(),
        # Trajectory fallback still routes through compute() for the same seam.
        compute_plan_scenario=lambda **kwargs: owner.compute(**kwargs),
        try_roster=lambda ae_overrides=None: data_access.try_roster(ae_overrides),
        get_self_serve_velocity=lambda: owner._get_self_serve_velocity(),
    )

    snapshot_builder = TieoutRuntimeSnapshotBuilder(
        get_config_dir=lambda: owner.config_dir,
        load_config_yaml=lambda filename: owner._load_yaml(filename),
        get_beginning_arr_snapshot=lambda: owner._get_beginning_arr_snapshot(),
        get_closed_won_finance_summary=lambda as_of=None: owner._get_closed_won_finance_summary(as_of=as_of),
        get_observed_arr_movements=lambda: owner._get_observed_arr_movements(),
        get_observed_decay_curve=lambda: owner._get_observed_decay_curve(),
        get_s2_to_won_rate=lambda: owner._get_s2_to_won_rate(),
        get_rolling_s2_to_won_rate=lambda: owner._get_rolling_s2_to_won_rate(),
        get_open_inventory_snapshot=lambda as_of=None: owner._get_open_inventory_snapshot(as_of=as_of),
        get_stage_win_rates=lambda: owner._get_stage_win_rates(),
        get_stage_velocity_days=lambda: owner._get_stage_velocity_days(),
        get_runtime_funnel_rates=lambda: owner._get_runtime_funnel_rates(),
        describe_runtime_funnel_rates=lambda: owner._describe_runtime_funnel_rates(),
        try_roster=lambda ae_overrides=None: data_access.try_roster(ae_overrides),
        get_observed_ae_productivity=lambda roster, as_of, lookback_days=180: owner._get_observed_ae_productivity(
            roster,
            as_of,
            lookback_days=lookback_days,
        ),
        get_observed_ae_ramp_curve=lambda roster, as_of, lookback_days=365: owner._get_observed_ae_ramp_curve(
            roster,
            as_of,
            lookback_days=lookback_days,
        ),
        get_trailing_mql_weekly_signal=lambda as_of, lookback_days=180: owner._get_trailing_mql_weekly_signal(
            as_of,
            lookback_days=lookback_days,
        ),
        get_self_serve_velocity=lambda: owner._get_self_serve_velocity(),
        get_monthly_mql_actuals=lambda as_of, months=12, fy_start=None: owner._get_monthly_mql_actuals(
            as_of, months=months, fy_start=fy_start,
        ),
        get_monthly_actuals=lambda as_of, months=12, fy_start=None: owner.data_access.get_monthly_actuals(
            as_of, months=months, fy_start=fy_start,
        ),
    )

    public_api = TieoutPublicApi(
        # Public API wrappers intentionally call compute() so post-init monkeypatches
        # on the compatibility wrapper are still honored.
        compute_plan=lambda **kwargs: owner.compute(**kwargs),
        compute_trajectory=lambda **kwargs: owner.compute_trajectory(**kwargs),
        run_health_checks=lambda runtime_snapshot=None: owner._run_health_checks(runtime_snapshot=runtime_snapshot),
        get_beginning_arr_snapshot=lambda: owner._get_beginning_arr_snapshot(),
        get_closed_won_finance_summary=lambda as_of=None: owner._get_closed_won_finance_summary(as_of=as_of),
        get_assumptions=lambda: owner.assumptions,
        get_targets=lambda: owner.targets,
        get_decay_curve=lambda: owner._get_decay_curve(),
        get_observed_arr_movements=lambda: owner._get_observed_arr_movements(),
        build_runtime_snapshot=lambda as_of=None: snapshot_builder.build(
            as_of=as_of,
            fy_start=owner.QUARTER_DATES[owner.QUARTERS[0]][0],
        ),
        tieout_result_factory=lambda **kwargs: TieoutResult(**kwargs),
    )

    health_checker = TieoutHealthChecker(owner=owner)

    return TieoutComponents(
        connector_gateway=connectors,
        runtime=runtime,
        scenario_assembler=scenario_assembler,
        targets_resolver=targets_resolver,
        support=support,
        data_access=data_access,
        archived_plan_model=archived_plan_model,
        projection=projection,
        recommendations=recommendations,
        scenarios=scenarios,
        public_api=public_api,
        health_checker=health_checker,
        snapshot_builder=snapshot_builder,
    )
