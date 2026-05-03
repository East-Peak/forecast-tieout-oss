/**
 * Forecast Snapshot — TypeScript contract types.
 *
 * These types mirror schema/snapshot.schema.json and define the shape of the
 * JSON payload exchanged between the Python engine and the React frontend.
 */

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
  assumptions: Record<string, unknown>;
  health_status: Record<string, unknown>;
  beginning_arr: number;
  beginning_arr_provenance?: Record<string, unknown>;
  bookings_summary_provenance?: Record<string, unknown>;
  top_down_plan: Record<string, unknown>;
  provenance?: Record<string, unknown>;
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
  provenance?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export interface Pipeline {
  deals: Deal[];
  inventory_by_stage: { stage: string; count: number; total_value: number }[];
  provenance: Record<string, unknown>;
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

export interface Rates {
  stage_conversion: Record<string, number>;
  stage_velocity_days: Record<string, number>;
  overall_win_rate: number;
  funnel_rates: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Roster
// ---------------------------------------------------------------------------

export interface Roster {
  current_aes: Record<string, unknown>[];
  trajectory_roster: Record<string, Record<string, unknown>[]>;
  trajectory_roster_meta: Record<string, unknown>;
  effective_capacity: CapacityRow[];
  observed_productivity: Record<string, unknown>;
  observed_ramp_curve: Record<string, unknown>;
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
  provenance: Record<string, unknown>;
  source_detail: Record<string, unknown>[];
  capacity_warnings: string[];
}

export interface QuarterData {
  quarter: string;
  period_start: string;
  period_end: string;
  td_bookings: number;
  bu_sales_led_arr: number;
  actual_bookings: number;
  [key: string]: unknown;
}

export interface CapacityHeadcountData {
  trajectory_capacity: CapacityRow[];
  plan_capacity: CapacityRow[];
  trajectory_quarters: QuarterData[];
  plan_quarters: QuarterData[];
}

export interface FunnelHealthData {
  trajectory_quarters: QuarterData[];
  plan_quarters: QuarterData[];
  funnel_rates: Record<string, number>;
  funnel_rate_descriptions: Record<string, unknown>;
  mql_actuals: unknown[];
  rolling_s2_to_won: Record<string, unknown>;
}

export interface PipelineInventoryData {
  months: string[];
  existing_wins: number[];
  existing_losses: number[];
  existing_remaining: number[];
  future_wins: number[];
  pipeline_creation: number[];
  provenance: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Scenario Building Blocks
// ---------------------------------------------------------------------------

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
