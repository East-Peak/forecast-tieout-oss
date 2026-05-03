export interface PlanManifestEntry {
  id?: string;
  path: string;
}

export interface RawPlanHiringEntry {
  month: string;
  count: number;
  role: string;
  segment?: string;
}

export interface RawSliderDefaults {
  win_rate?: number;
  avg_deal_size?: number;
  ramp_months?: number;
  avg_productivity?: number;
  avg_cycle_days?: number;
}

export type PlanArrGrain = "monthly" | "quarterly" | "annual";
export type PlanSeatGrain = "monthly" | "quarterly" | "annual";
export type PlanTreatmentClass = "operator_comparable" | "executive_reference";
export type PlanModeledStatus = "scenario_modeled" | "held_assumption";

export type PlanPacingFieldId =
  | "mqls_weekly"
  | "s0_weekly"
  | "s1_weekly"
  | "s2_weekly"
  | "mql_to_s0"
  | "s0_to_s1"
  | "s1_to_s2";

export interface RawPlanPreset {
  schema_version?: number;
  id?: string;
  name: string;
  version: string;
  created_date: string;
  quarterly_targets?: Record<string, number>;
  monthly_targets?: Record<string, number>;
  monthly_ae_targets?: Record<string, number>;
  hiring_schedule?: RawPlanHiringEntry[];
  quarter_end_ae_targets?: Record<string, number>;
  quarterly_mql_pace?: Record<string, number>;
  quarterly_conversion_targets?: {
    mql_to_s0?: Record<string, number>;
    s0_to_s1?: Record<string, number>;
    s1_to_s2?: Record<string, number>;
  };
  slider_defaults?: RawSliderDefaults;
  default_comparison_view_id?: string;
  default_executive_context_view_id?: string;
  components?: Record<string, unknown>;
  views?: Record<string, unknown>;
  pacing?: Record<string, unknown>;
  forward_context?: Record<string, unknown>;
}

export interface SliderDefaults {
  winRate: number | null;
  avgDealSize: number | null;
  rampMonths: number | null;
  avgProductivity: number | null;
  avgCycleDays: number | null;
}

export interface PlanTargetBookkeeping {
  quarterlyBookings: Record<string, number>;
  explicitMonthlyBookings: Record<string, number>;
  explicitMonthlyAeTargets: Record<string, number>;
  quarterEndAeTargets: Record<string, number>;
  quarterlyMqlPace: Record<string, number>;
  quarterlyConversionRates: {
    mqlToS0: Record<string, number>;
    s0ToS1: Record<string, number>;
    s1ToS2: Record<string, number>;
  };
}

export interface NormalizedValueFamily {
  canonicalGrain: PlanArrGrain;
  monthly: Record<string, number>;
  quarterly: Record<string, number>;
  annual: number | null;
}

export interface NormalizedSeatValueFamily {
  canonicalGrain: PlanSeatGrain;
  monthly: Record<string, number>;
  quarterly: Record<string, number>;
  annual: number | null;
}

export interface PlanComponent {
  id: string;
  label: string;
  category: string;
  modeledStatus: PlanModeledStatus;
  approvalStatus: string;
  basis: string;
  asOf: string;
  arrTargets: NormalizedValueFamily;
  seatTargets: NormalizedSeatValueFamily | null;
}

export interface PlanView {
  id: string;
  label: string;
  treatmentClass: PlanTreatmentClass;
  supportedGrains: PlanArrGrain[];
  componentIds: string[];
  seatTargetOwnerComponentId: string | null;
  derived: boolean;
  contextKind: string | null;
  totals: {
    monthly: Record<string, number>;
    quarterly: Record<string, number>;
    annual: number | null;
  };
}

export interface PlanPacingProvenance {
  source: string;
  derivation: string;
  approvalStatus: string;
  freshnessAsOf: string | null;
  freshnessStatus: string | null;
  label: string | null;
  notes: string[];
}

export interface PlanPacingField {
  value: number;
  provenance: PlanPacingProvenance;
}

export interface PlanPacingQuarterPackage {
  packageProvenance: PlanPacingProvenance;
  fields: Partial<Record<PlanPacingFieldId, PlanPacingField>>;
}

export interface PlanForwardContext {
  mode: "note_only";
  promotionStrategy: "requires_new_plan_version";
  effectiveAfter: string | null;
  referenceSeries: Record<string, Record<string, number>>;
  notes: string[];
}

export interface PlanPreset {
  id: string;
  slug: string;
  schemaVersion: 1 | 2;
  name: string;
  version: string;
  createdDate: string;
  source: {
    manifestId: string | null;
    path: string | null;
    provenance: "plan_file";
  };
  components: Record<string, PlanComponent>;
  views: Record<string, PlanView>;
  comparisonScopeId: string | null;
  comparisonScopeLabel: string | null;
  comparison: {
    viewId: string | null;
    label: string | null;
    operatorComparable: boolean;
    supportedGrains: PlanArrGrain[];
    seatTargetOwnerComponentId: string | null;
  };
  executiveContext: {
    viewId: string | null;
    label: string | null;
    supportedGrains: PlanArrGrain[];
    annualTarget: number | null;
    quarterlyTargets: Record<string, number>;
    available: boolean;
  };
  targets: PlanTargetBookkeeping;
  pacing: Record<string, PlanPacingQuarterPackage>;
  hiring: {
    entries: RawPlanHiringEntry[];
    hasExplicitMonthlySeatPath: boolean;
  };
  assumptions: SliderDefaults;
  availability: {
    comparableOnOperatorPages: boolean;
    explicitMonthlyBookings: boolean;
    explicitMonthlyAeTargets: boolean;
    quarterEndAeTargets: boolean;
    quarterlyMqlPace: boolean;
    quarterlyConversionRates: boolean;
    hiringSchedule: boolean;
    monthlyComparable: boolean;
    quarterlyComparable: boolean;
    annualComparable: boolean;
    executiveContext: boolean;
  };
  forwardContext: PlanForwardContext | null;
  fyTarget: number | null;
}

export type PlanMonthlyReferenceBasis =
  | "none"
  | "explicit_monthly_plan"
  | "derived_even_quarter_split"
  | "mixed"
  | "unsupported_monthly"
  | "suppressed_non_comparable";

export interface PlanMonthlyReferenceRow {
  month: string;
  quarter: string | null;
  value: number;
  basis: Exclude<
    PlanMonthlyReferenceBasis,
    "none" | "mixed" | "unsupported_monthly" | "suppressed_non_comparable"
  >;
}

export interface PlanMonthlyReference {
  label: string;
  note: string | null;
  basis: PlanMonthlyReferenceBasis;
  values: number[];
  rows: PlanMonthlyReferenceRow[];
}

export interface PlanTimingSemanticsItem {
  label: string;
  detail: string;
  tone: "slate" | "blue" | "emerald" | "amber";
}

export interface PlanTimingSemantics {
  selectedPlanName: string;
  comparisonScopeLabel: string | null;
  comparisonScopeId: string | null;
  overview: string;
  items: PlanTimingSemanticsItem[];
}

export interface ResolvedPlanPacingProvenance extends PlanPacingProvenance {
  stale: boolean;
  evaluationAsOf: string;
  presentationState: "approved" | "provisional" | "fallback" | "unknown";
}

export interface ResolvedPlanPacingField {
  value: number | null;
  provenance: ResolvedPlanPacingProvenance | null;
  source: "plan" | "fallback" | "none";
}

export class PlanValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PlanValidationError";
  }
}
