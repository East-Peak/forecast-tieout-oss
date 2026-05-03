"""
GTM Model Library

A model of the go-to-market motion for a B2B SaaS company.
Covers acquisition funnel, opportunity stages, rep capacity, ARR waterfall,
and attribution analysis.

Usage:
    from gtm_model import funnel, capacity, waterfall, attribution

    # Calculate required pipeline to hit target
    requirements = funnel.reverse_funnel(bookings_target=6_000_000)

    # Calculate team capacity for a quarter
    cap = capacity.calculate_quarterly("Q1FY26")

    # Compute ARR waterfall
    wf = waterfall.calculate("Q1FY26")
"""

from .stages import OpportunityStage, StageMetrics, LeadStage
from .funnel import FunnelAssumptions, FunnelRequirements, reverse_funnel, forward_funnel
from .capacity import RepCapacity, TeamCapacity, Segment, RampCurve, calculate_quarterly_capacity
from .waterfall import ARRWaterfall, RetentionAssumptions, calculate_waterfall, project_arr_timeline
from .scenarios import Scenario, run_scenario, compare_scenarios, what_if_close_rate_improves, create_standard_scenarios
from .timing import (
    TimelineRequirement,
    TimelineStatus,
    MonthlyRequirement,
    calculate_pipeline_creation_schedule,
    calculate_mql_schedule,
    build_timeline_requirement,
    assess_timeline_status,
)
from .velocity import (
    SalesCycleVelocity,
    StageVelocity,
    LeadVelocity,
    VelocityComparison,
    calculate_sales_cycle_velocity,
    calculate_stage_velocity_from_history,
    get_assumed_stage_velocity,
    calculate_lead_velocity,
    compare_velocity,
)
from .economics import (
    UnitEconomics,
    TeamCost,
    calculate_cac,
    calculate_ltv,
    calculate_payback,
    calculate_unit_economics,
    scenario_economics,
    compare_economics,
    # v3 additions
    RoleCosts,
    OrgCost,
    calculate_org_cost,
    calculate_org_cost_from_team,
    calculate_sm_efficiency,
)
from .team_structure import (
    GTMRole,
    SegmentRatios,
    CoverageRatios,
    DerivedTeam,
    derive_team,
    derive_team_from_segments,
    calculate_incremental_support,
    team_from_headcount,
    validate_coverage,
)
from .hiring import (
    MonthlyHire,
    HiringPace,
    AttritionRates,
    HiringPlan,
    reverse_hiring_timeline,
    reverse_hiring_timeline_detailed,
    generate_hiring_plan,
    project_headcount_timeline,
    calculate_capacity_with_ramp,
)
from .org_planner import (
    OrgPlan,
    OrgPlanner,
    quick_derive_team,
    quick_org_cost,
)
from .segments import (
    SegmentProductivity,
    SelfServeStream,
    AttritionModel,
    calculate_segment_capacity,
    calculate_combined_arr_target,
)
from .capacity import (
    # v3 additions
    MonthlyCapacity,
    calculate_monthly_capacity,
    calculate_monthly_timeline,
    calculate_required_aes_for_arr,
    calculate_team_arr_capacity,
    format_monthly_timeline,
)
# v3.1: ARR Waterfall / NDR
from .arr_waterfall import (
    ARRMovementType,
    ARRMovement,
    ARRWaterfallPeriod,
    CohortRetention,
    NDRProjection,
    calculate_ndr,
    calculate_grr,
    calculate_expansion_rate,
    annualize_retention,
    build_arr_waterfall,
    build_arr_waterfall_from_sf,
    project_arr_with_ndr,
)
# v3.1: Pipeline Coverage
from .pipeline_coverage import (
    PipelineSegment,
    CoverageMultiples,
    PipelineSourceMix,
    PipelineAging,
    PipelineBucket,
    SegmentCoverage,
    CoverageReport,
    PipelineQualityScore,
    calculate_segment_coverage,
    calculate_coverage_report,
    calculate_required_pipeline,
    calculate_achievable_bookings,
    calculate_pipeline_quality,
    calculate_weighted_pipeline,
    project_pipeline_needs,
)
# v3.1: Variable Comp / Accelerators
from .economics import (
    CompStructure,
    AcceleratorTier,
    AcceleratorPlan,
    VariableCompCalculation,
    calculate_variable_comp,
    calculate_team_variable_comp,
    project_comp_scenarios,
    calculate_quota_to_ote_health,
)
# v3.2: Prediction & Forecasting
from .forecast import (
    ChannelStatus,
    PipelineForecast,
    ChannelRequirement,
    ChannelBreakdown,
    RollingForecast,
    calculate_pipeline_forecast,
    calculate_channel_requirements,
    calculate_rolling_forecast,
    get_age_multiplier,
    load_forecast_config,
    format_currency,
    DEFAULT_STAGE_CONVERSION,
    AGE_MULTIPLIERS,
)

# v3.2: Monte Carlo Simulation
from .monte_carlo import (
    Deal,
    SimulationRun,
    MonteCarloResult,
    VarianceAttribution,
    run_monte_carlo_forecast,
    calculate_variance_attribution,
    deals_from_sf_pipeline,
    run_scenario,
    compare_scenarios,
    DEFAULT_TRANSITION_MATRIX,
    DEFAULT_STAGE_WIN_RATES,
    DEFAULT_BETA_PRIORS,
)

__version__ = "0.3.2"  # v3.2 with Prediction & Forecasting + Monte Carlo

__all__ = [
    # Stages
    "OpportunityStage",
    "StageMetrics",
    "LeadStage",
    # Funnel
    "FunnelAssumptions",
    "FunnelRequirements",
    "reverse_funnel",
    "forward_funnel",
    # Capacity
    "RepCapacity",
    "TeamCapacity",
    "Segment",
    "RampCurve",
    "calculate_quarterly_capacity",
    # Waterfall
    "ARRWaterfall",
    "RetentionAssumptions",
    "calculate_waterfall",
    "project_arr_timeline",
    # Scenarios
    "Scenario",
    "run_scenario",
    "compare_scenarios",
    "what_if_close_rate_improves",
    "create_standard_scenarios",
    # Timing
    "TimelineRequirement",
    "TimelineStatus",
    "MonthlyRequirement",
    "calculate_pipeline_creation_schedule",
    "calculate_mql_schedule",
    "build_timeline_requirement",
    "assess_timeline_status",
    # Velocity (v2)
    "SalesCycleVelocity",
    "StageVelocity",
    "LeadVelocity",
    "VelocityComparison",
    "calculate_sales_cycle_velocity",
    "calculate_stage_velocity_from_history",
    "get_assumed_stage_velocity",
    "calculate_lead_velocity",
    "compare_velocity",
    # Economics (v2)
    "UnitEconomics",
    "TeamCost",
    "calculate_cac",
    "calculate_ltv",
    "calculate_payback",
    "calculate_unit_economics",
    "scenario_economics",
    "compare_economics",
    # Economics (v3)
    "RoleCosts",
    "OrgCost",
    "calculate_org_cost",
    "calculate_org_cost_from_team",
    "calculate_sm_efficiency",
    # Team Structure (v3)
    "GTMRole",
    "SegmentRatios",
    "CoverageRatios",
    "DerivedTeam",
    "derive_team",
    "derive_team_from_segments",
    "calculate_incremental_support",
    "team_from_headcount",
    "validate_coverage",
    # Hiring (v3)
    "MonthlyHire",
    "HiringPace",
    "AttritionRates",
    "HiringPlan",
    "reverse_hiring_timeline",
    "reverse_hiring_timeline_detailed",
    "generate_hiring_plan",
    "project_headcount_timeline",
    "calculate_capacity_with_ramp",
    # Org Planner (v3)
    "OrgPlan",
    "OrgPlanner",
    "quick_derive_team",
    "quick_org_cost",
    # Capacity (v3)
    "MonthlyCapacity",
    "calculate_monthly_capacity",
    "calculate_monthly_timeline",
    "calculate_required_aes_for_arr",
    "calculate_team_arr_capacity",
    "format_monthly_timeline",
    # Segments (v3)
    "SegmentProductivity",
    "SelfServeStream",
    "AttritionModel",
    "calculate_segment_capacity",
    "calculate_combined_arr_target",
    # ARR Waterfall / NDR (v3.1)
    "ARRMovementType",
    "ARRMovement",
    "ARRWaterfallPeriod",
    "CohortRetention",
    "NDRProjection",
    "calculate_ndr",
    "calculate_grr",
    "calculate_expansion_rate",
    "annualize_retention",
    "build_arr_waterfall",
    "build_arr_waterfall_from_sf",
    "project_arr_with_ndr",
    # Pipeline Coverage (v3.1)
    "PipelineSegment",
    "CoverageMultiples",
    "PipelineSourceMix",
    "PipelineAging",
    "PipelineBucket",
    "SegmentCoverage",
    "CoverageReport",
    "PipelineQualityScore",
    "calculate_segment_coverage",
    "calculate_coverage_report",
    "calculate_required_pipeline",
    "calculate_achievable_bookings",
    "calculate_pipeline_quality",
    "calculate_weighted_pipeline",
    "project_pipeline_needs",
    # Variable Comp / Accelerators (v3.1)
    "CompStructure",
    "AcceleratorTier",
    "AcceleratorPlan",
    "VariableCompCalculation",
    "calculate_variable_comp",
    "calculate_team_variable_comp",
    "project_comp_scenarios",
    "calculate_quota_to_ote_health",
    # Prediction & Forecasting (v3.2)
    "ChannelStatus",
    "PipelineForecast",
    "ChannelRequirement",
    "ChannelBreakdown",
    "RollingForecast",
    "calculate_pipeline_forecast",
    "calculate_channel_requirements",
    "calculate_rolling_forecast",
    "get_age_multiplier",
    "load_forecast_config",
    "format_currency",
    "DEFAULT_STAGE_CONVERSION",
    "AGE_MULTIPLIERS",
    # Monte Carlo Simulation (v3.2)
    "Deal",
    "SimulationRun",
    "MonteCarloResult",
    "VarianceAttribution",
    "run_monte_carlo_forecast",
    "calculate_variance_attribution",
    "deals_from_sf_pipeline",
    "run_scenario",
    "compare_scenarios",
    "DEFAULT_TRANSITION_MATRIX",
    "DEFAULT_STAGE_WIN_RATES",
    "DEFAULT_BETA_PRIORS",
]
