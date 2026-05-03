/**
 * TargetSetter — TypeScript domain + view-model types.
 *
 * Domain types mirror the engine's snapshot.target_setter block and the
 * JSON schema at schema/snapshot.schema.json#/$defs/TargetSetterBlock.
 *
 * View-model types (ScenarioOption, RoleSummaryCard, TotalFooter) live here
 * rather than in the components that render them to break cyclic imports:
 * pageHelpers.ts imports from here, not from component files.
 */

// ---------------------------------------------------------------------------
// Domain aliases — runtime strings, no literal unions.
// ---------------------------------------------------------------------------

export type QuarterKey = string;
export type SegmentKey = string;
export type ScenarioId = string;

// ---------------------------------------------------------------------------
// Scenario
// ---------------------------------------------------------------------------

export interface Scenario {
  id: ScenarioId;
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
  segment_share: Record<SegmentKey, number>;
  acv: Record<SegmentKey, number>;
}

// ---------------------------------------------------------------------------
// QuarterTargets — per-quarter solve output
// ---------------------------------------------------------------------------

export interface QuarterTargets {
  quarter: QuarterKey;
  starting_pipe: number;
  bookings_target: number;
  created_pipe: number;
  infeasible: boolean;
  /** starting_pipe × win_rate_starting — bookings from carried-over pipe */
  won_from_starting: number;
  /** created_pipe × win_rate_created — bookings from new pipe created this quarter */
  won_from_created: number;
  /** Total created_pipe × (1 - ae_self_gen_pct) — marketing-sourced pipe dollars */
  marketing_pipe: number;
  marketing_s2_total: number;
  marketing_s2_by_segment: Record<SegmentKey, number>;
  total_s2_by_segment: Record<SegmentKey, number>;
  mqls: number;
  /** Marketing-sourced S0 meetings — derived from MQLs × mql_to_s0 */
  s0: number;
  /** Marketing-sourced S1 meetings — derived from marketing S0 × s0_to_s1 */
  s1: number;
  // --- Two-tributary extensions (same-rate assumption for Outbound path) ---
  /** Total S0 meetings needed (Marketing-sourced + Outbound-sourced) */
  total_s0: number;
  /** Total S1 meetings needed */
  total_s1: number;
  /** Total S2 SQOs needed (Marketing + Outbound). Equals sum of total_s2_by_segment. */
  total_s2: number;
  /** Outbound-sourced S0 — what SDRs + direct AE outreach must generate */
  outbound_s0: number;
  /** Outbound-sourced S1 */
  outbound_s1: number;
  /** Outbound-sourced S2 SQOs (= total_s2 − marketing_s2_total) */
  outbound_s2: number;
  ending_pipe: number;
}

// ---------------------------------------------------------------------------
// SolveResult — full output from the waterfall solver
// ---------------------------------------------------------------------------

export interface SolveResult {
  scope: QuarterKey[];
  active_quarter: QuarterKey | null;
  active_ytd_bookings: number;
  active_remaining_gap: number;
  quarters: QuarterTargets[];
  warnings: string[];
}

// ---------------------------------------------------------------------------
// CapacityInput / GapQuarter — capacity and gap analysis
// ---------------------------------------------------------------------------

export interface CapacityInput {
  quarter: QuarterKey;
  mql_capacity: number;
}

export interface GapQuarter {
  quarter: QuarterKey;
  mqls_needed: number;
  mql_capacity: number;
  mql_gap: number;
  implied_bookings: number;
  bookings_target: number;
  bookings_gap: number;
}

// ---------------------------------------------------------------------------
// MonthlyRow / WeeklyRow — cadenced planning grids
// ---------------------------------------------------------------------------

export interface MonthlyRow {
  quarter: QuarterKey;
  months: [string, string, string];
  values: [number, number, number];
  quarterly_total: number;
  manually_edited: boolean[];
}

export interface WeeklyRow {
  quarter: QuarterKey;
  weeks: string[];
  values: number[];
  quarterly_total: number;
  manually_edited: boolean[];
}

// ---------------------------------------------------------------------------
// View-model types
// Copied verbatim from source components (literal-union ids → ScenarioId/string).
// ---------------------------------------------------------------------------

/**
 * Source: components/targetSetter/ScenarioSelector.tsx
 * Drives the scenario pill strip.
 */
export interface ScenarioOption {
  id: ScenarioId;
  label: string;
  /** Main provenance line, e.g. "SFDC · trailing 90d · n=929". */
  primaryLine: string;
  /** Secondary provenance line, e.g. "refreshed Apr 18, 2026". */
  secondaryLine: string;
}

/**
 * Source: components/targetSetter/RoleSummaryStrip.tsx
 * One card per role (Marketing / SDR / AE) in the summary strip.
 */
export interface RoleSummaryCard {
  role: string;
  metricLabel: string;
  totalValue: number;
  integer: boolean;
  perQuarter: { quarter: string; value: number }[];
  /** Relative delta (e.g. 1.4 = +140%) or null when baseline unavailable. */
  qoqDelta: number | null;
  /** Optional secondary metric rendered beneath the primary — useful for showing
   *  a derived or downstream number without adding a whole separate card. */
  secondary?: {
    label: string;
    totalValue: number;
    integer: boolean;
    perQuarter: { quarter: string; value: number }[];
  };
}

/**
 * Source: components/targetSetter/RoleSummaryStrip.tsx
 * Combined total footer shown below the role strip.
 */
export interface TotalFooter {
  label: string;
  totalValue: number;
  integer: boolean;
  perQuarter: { quarter: string; value: number }[];
  /** Optional sub-components, shown inline — e.g. "Marketing 1,234 + Outbound 567". */
  components?: { label: string; value: number }[];
}
