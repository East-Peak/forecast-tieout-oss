/**
 * Forecast Snapshot — TypeScript contract types.
 *
 * These types mirror schema/snapshot.schema.json and define the shape of the
 * JSON payload exchanged between the Python engine and the React frontend.
 */

// ---------------------------------------------------------------------------
// TargetSetter — scenario shape as emitted by the engine.
// Used in snapshot.target_setter.observed_scenario and .scenarios[].
// All rate fields are REQUIRED; the engine and schema guarantee their presence.
// ---------------------------------------------------------------------------

/** @contract Engine snapshot target-setter scenario payload. */
export interface SnapshotScenario {
  id: string;
  label: string;
  description?: { primary: string; secondary: string };
  win_rate_starting: number;
  win_rate_created: number;
  push_rate: number;
  loss_rate: number;
  ae_self_gen_pct: number;
  mql_to_s0: number;
  s0_to_s1: number;
  s1_to_s2: number;
  segment_share: Record<string, number>;
  acv: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export interface Snapshot {
  /** Semver tracking the shape of this contract (not engine behavior). */
  schema_version: string;
  /** Version of the Python engine that produced this snapshot. */
  engine_version: string;
  /** Configuration profile used to generate this snapshot. */
  profile_id: string;
  /** Flags indicating which data sources were available at generation time. */
  capabilities: {
    has_stage_history: boolean;
    has_contacts: boolean;
    has_companies: boolean;
  };
  /** ISO 8601 timestamp of snapshot generation. */
  generated_at: string;
  /** Git commit SHA of the engine at generation time. */
  git_sha: string;
  /** ISO 8601 date representing the effective date of the snapshot data. */
  as_of: string;

  actuals: Actuals;
  pipeline: Pipeline;
  rates: Rates;
  roster: Roster;
  model_output: ModelOutput;
  scenario_building_blocks: ScenarioBuildingBlocks;
  assumptions: { [key: string]: unknown };
  health_status: { [key: string]: unknown };
  beginning_arr: number;
  beginning_arr_provenance?: { [key: string]: unknown };
  bookings_summary_provenance?: { [key: string]: unknown };
  top_down_plan: { [key: string]: unknown };
  provenance?: { [key: string]: unknown };

  /**
   * TargetSetter block — optional, present only when the engine is configured
   * with a target_setter section (profiles that declare bookings targets).
   * observed_scenario mirrors the engine's calibrated rates for the active
   * period; scenarios is the full palette the UI offers for what-if selection.
   */
  target_setter?: {
    observed_scenario?: SnapshotScenario;
    scenarios?: SnapshotScenario[];
  };
}

// ---------------------------------------------------------------------------
// Actuals
// ---------------------------------------------------------------------------

export interface Actuals {
  bookings_by_month: { month: string; total: number }[];
  losses_by_month?: { month: string; total: number }[];
  pipeline_created_by_month?: { month: string; total: number }[];
  pipeline_entered_s2_by_month?: { month: string; total: number }[];
  mql_by_month: { month_index: number; value: number }[];
  provenance?: { [key: string]: unknown };
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

/** @contract Engine snapshot pipeline payload. */
export interface Pipeline {
  deals: Deal[];
  inventory_by_stage: { stage: string; count: number; total_value: number }[];
  provenance: { [key: string]: unknown };
}

export interface Deal {
  opp_id: string;
  stage: string;
  amount: number;
  arr: number;
  metric_value: number;
  close_date: string | null;
  created_date: string | null;
  source_stream: string;
  owner_name: string;
  opp_type: string;
  forecast_category: string;
}

// ---------------------------------------------------------------------------
// Rates
// ---------------------------------------------------------------------------

/** @contract Engine snapshot rate payload. */
export interface Rates {
  stage_conversion: Record<string, number>;
  stage_velocity_days: Record<string, number>;
  overall_win_rate: number;
  funnel_rates: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Roster
// ---------------------------------------------------------------------------

/** @contract Engine snapshot roster payload. */
export interface Roster {
  current_aes: Array<{ [key: string]: unknown }>;
  trajectory_roster: { [role: string]: Array<{ [key: string]: unknown }> };
  trajectory_roster_meta: { [key: string]: unknown };
  effective_capacity: CapacityRow[];
  observed_productivity: { [key: string]: unknown };
  observed_ramp_curve: { [key: string]: unknown };
}

export interface CapacityRow {
  month: string;
  label?: string;
  ae_total: number;
  ae_ramped: number;
  ae_ramping: number;
  se_total: number;
  sdr_total: number;
  ae_capacity: number;
  ae_capacity_ramped: number;
  ae_capacity_ramping: number;
  blended_ramp_pct: number;
  monthly_target: number;
}

// ---------------------------------------------------------------------------
// Model Output (pre-computed view models)
// ---------------------------------------------------------------------------

/** @contract Engine snapshot precomputed page view-model payload. */
export interface ModelOutput {
  bookings_bridge: BookingsBridgeData;
  capacity_headcount: CapacityHeadcountData;
  funnel_health: FunnelHealthData;
  pipeline_inventory: PipelineInventoryData;
}

export interface BookingsBridgeData {
  months: string[];
  existing_wins: number[];
  future_wins: number[];
  total_expected: number[];
  capped: number[];
  overflow: number[];
  plan_existing_wins: number[];
  plan_future_wins: number[];
  plan_total: number[];
  trajectory_quarters: QuarterData[];
  plan_quarters: QuarterData[];
  provenance: { [key: string]: unknown };
  source_detail: Array<{ [key: string]: unknown }>;
  capacity_warnings: string[];
}

/** @contract Shared engine snapshot quarter summary row. */
export interface QuarterData {
  quarter: string;
  period_start: string;
  period_end: string;
  td_bookings: number;
  bu_sales_led_arr: number;
  actual_bookings: number;
  [key: string]: unknown;
}

interface FunnelHealthTopDown {
  bookings?: number;
  plg?: number;
  expansion?: number;
  total_net_new?: number;
  ending_arr?: number;
  pipeline_target?: number;
  aes?: number;
  total_gtm?: number;
}

interface FunnelHealthBottomsUp {
  sales_led_arr?: number;
  plg_arr?: number;
  expansion_arr?: number;
  total_arr?: number;
  ramped_aes?: number;
  total_aes?: number;
}

interface FunnelHealthActuals {
  bookings?: number;
  pipeline?: number;
  mqls_weekly?: number;
  s0_weekly?: number;
  s1_weekly?: number;
  s2_weekly?: number;
}

interface FunnelHealthGap {
  bookings?: number;
  bookings_pct?: number;
  total?: number;
  total_pct?: number;
  status?: string;
}

interface FunnelHealthReforecast {
  quarter_state?: string;
  elapsed_fraction?: number;
  actual_bookings?: number;
  plan_to_date_bookings?: number;
  pace_gap?: number;
  pace_gap_pct?: number;
  remaining_plan_bookings?: number;
  remaining_bu_bookings?: number;
  reforecast_bookings?: number;
  reforecast_gap?: number;
  reforecast_gap_pct?: number;
  has_actuals?: boolean;
}

interface FunnelHealthTieoutMetric {
  plan?: number;
  actual?: number;
  delta?: number;
}

interface FunnelHealthTieout {
  [stageKey: string]: FunnelHealthTieoutMetric | undefined;
  mqls_weekly?: FunnelHealthTieoutMetric;
  s0_weekly?: FunnelHealthTieoutMetric;
  s1_weekly?: FunnelHealthTieoutMetric;
  s2_weekly?: FunnelHealthTieoutMetric;
}

export interface FunnelHealthConversionRate {
  rate?: number;
  n?: number;
  source?: string;
}

export interface FunnelHealthConversionRateByStream {
  [streamKey: string]: FunnelHealthConversionRate | undefined;
  blended?: FunnelHealthConversionRate;
  marketing_sdr?: FunnelHealthConversionRate;
  ae_selfgen?: FunnelHealthConversionRate;
  plg?: FunnelHealthConversionRate;
}

interface FunnelHealthConversionRates {
  [transitionKey: string]: FunnelHealthConversionRateByStream | undefined;
}

export interface FunnelHealthSourceStream {
  stream_key: string;
  display_name?: string;
  input_label?: string;
  weekly_input?: number;
  weekly_s0_count?: number;
  weekly_s1_count?: number;
  weekly_s2_count?: number;
  monthly_input?: number[];
  monthly_s0_count?: number[];
  monthly_s1_count?: number[];
  monthly_s2_count?: number[];
  monthly_creation?: number[];
  quarter_pipeline_created?: number;
  actual_opp_count?: number;
  actual_pipeline?: number;
}

interface FunnelHealthSourceBreakdown {
  mode?: string;
  streams?: {
    [streamKey: string]: FunnelHealthSourceStream | undefined;
  };
  pipeline_value_provenance?: unknown;
}

export interface FunnelHealthExpansionBreakdown {
  quarter?: string;
  opening_arr?: number;
  sales_led_base_arr?: number;
  plg_base_arr?: number;
  renewable_sales_led_arr?: number;
  sales_led_usage_eligible_arr?: number;
  plg_usage_eligible_arr?: number;
  committed_consumption_arr?: number;
  program_maturity_factor?: number;
  renewal_expansion_arr?: number;
  usage_expansion_arr?: number;
  plg_expansion_arr?: number;
  consumption_true_forward_arr?: number;
  total_expansion_arr?: number;
}

interface FunnelHealthRateDescription {
  value?: number;
  source?: string;
  n?: number | null;
  methodology?: string;
}

interface FunnelHealthRollingS2ToWon {
  rate?: number;
  source?: string;
  sample?: number;
  method?: string;
  lookback_days?: number;
}

export interface FunnelHealthQuarter extends QuarterData {
  top_down?: FunnelHealthTopDown;
  bottoms_up?: FunnelHealthBottomsUp;
  actuals?: FunnelHealthActuals;
  gap?: FunnelHealthGap;
  conversion_rates?: FunnelHealthConversionRates;
  funnel_tieout?: FunnelHealthTieout;
  source_breakdown?: FunnelHealthSourceBreakdown;
  expansion_breakdown?: FunnelHealthExpansionBreakdown;
  reforecast?: FunnelHealthReforecast;
  confidence_tier?: string;
  is_derived_targets?: boolean;
  bu_plg_arr?: number;
  bu_expansion_arr?: number;
}

export interface CapacityHeadcountData {
  trajectory_capacity: CapacityRow[];
  plan_capacity: CapacityRow[];
  trajectory_quarters: QuarterData[];
  plan_quarters: QuarterData[];
}

/**
 * Provenance record for a single computed rate.
 * Copied verbatim from source types/snapshot.ts (optional fields preserved).
 */
export interface RateProvenance {
  value: number;
  source: string;
  n: number | null;
  methodology: string;
  lookback_days?: number;
  calibrated_at?: string;
  date_range?: { start: string; end: string };
}

/** @contract Engine snapshot waterfall-rate provenance alias. */
export type WaterfallRateDescription = RateProvenance;

/** Four waterfall rates emitted by the engine's calibration step. */
export interface WaterfallRates {
  win_rate_starting: number;
  win_rate_created: number;
  push_rate: number;
  loss_rate: number;
}

export interface FunnelHealthData {
  trajectory_quarters: FunnelHealthQuarter[];
  plan_quarters: FunnelHealthQuarter[];
  funnel_rates: { [rateName: string]: number };
  funnel_rate_descriptions: {
    [rateName: string]: FunnelHealthRateDescription | undefined;
  };
  mql_actuals: unknown[];
  rolling_s2_to_won: FunnelHealthRollingS2ToWon | null;
  /** Optional: present on engine v2+ snapshots. */
  waterfall_rates?: WaterfallRates;
  waterfall_rate_descriptions?: Record<keyof WaterfallRates, WaterfallRateDescription>;
}

export interface PipelineInventoryData {
  months: string[];
  existing_wins: number[];
  existing_losses: number[];
  existing_remaining: number[];
  future_wins: number[];
  pipeline_creation: number[];
  provenance: { [key: string]: unknown };
}

// ---------------------------------------------------------------------------
// Scenario Building Blocks
// ---------------------------------------------------------------------------

/** @contract Engine snapshot scenario-planner payload. */
export interface ScenarioBuildingBlocks {
  months: string[];
  monthly_is_actual: boolean[];
  monthly_inventory_wins: number[];
  monthly_inventory_losses: number[];
  monthly_inventory_remaining: number[];
  monthly_ae_creation: number[];
  monthly_mql_creation: number[];
  monthly_future_wins: number[];
  monthly_ae_count: number[];
  monthly_ae_capacity: number[];
  monthly_ae_ramped: number[];
  monthly_blended_ramp: number[];
  monthly_total_expected: number[];
  monthly_capped: number[];
  observed_values: ObservedValues;
  decay_curve: number[];
  stage_win_rates: Record<string, number>;
  funnel_rates: Record<string, number>;
  /**
   * Parallel array to `months`: the fiscal-quarter label each month belongs to,
   * or null for months outside the active fiscal year (e.g. prior-year actuals).
   * The engine emits this so the frontend never needs to know the fiscal calendar.
   * Optional during the migration; will become required once the scenario engine
   * stops hardcoding its own month-to-quarter mapping.
   */
  quarter_by_month?: (string | null)[];
  /**
   * Ordered list of quarter labels that the user can edit in the scenario UI
   * (typically: every quarter that hasn't fully booked actuals yet).
   * Engine-derived from `monthly_is_actual` + `quarter_by_month`. Optional
   * during the migration; required once scenario.ts consumes it.
   */
  overridable_quarters?: string[];
}

export interface ObservedValues {
  win_rate: number;
  avg_deal_size: number;
  avg_cycle_days: number;
  ramp_months: number;
  productivity_per_ae_per_month: number;
}
