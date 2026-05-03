import {
  cloneScenarioOverrides,
} from "../engine/scenario";
import type {
  ScenarioOverrides,
  ScenarioQuarterKey,
  ScenarioQuarterOverride,
} from "../engine/scenario";
import type {
  PlanPreset,
  ResolvedPlanPacingProvenance,
} from "./plans";
import {
  getPlanSeatQuarterTarget,
  resolvePlanPacingField,
} from "./plans";
import { formatMoney } from "./format";
export { formatMoney };

/** Quarter label for display. Sourced from snapshot.scenario_building_blocks at runtime. */
export type DisplayQuarter = string;

export type ScalarOverrideFieldKey = Exclude<
  keyof ScenarioQuarterOverride,
  "addAes" | "aeMonthTargets" | "mqlChangePct"
>;

export interface OverrideFieldConfig {
  key: ScalarOverrideFieldKey;
  label: string;
  inputKind: "count" | "percent" | "currency";
  step: number;
  min?: number;
  max?: number;
  help: string;
  format: (value: number) => string;
}

export interface QuarterPlanReference {
  comparable: boolean;
  quarterlySupported: boolean;
  quarterEndAeTarget: number | null;
  mqlWeekly: number | null;
  mqlToS0: number | null;
  s0ToS1: number | null;
  s1ToS2: number | null;
  avgDealSize: number | null;
  provenance: {
    mqlWeekly: ResolvedPlanPacingProvenance | null;
    mqlToS0: ResolvedPlanPacingProvenance | null;
    s0ToS1: ResolvedPlanPacingProvenance | null;
    s1ToS2: ResolvedPlanPacingProvenance | null;
  };
  note: string | null;
}

export interface ScenarioQuarterSummaryRow {
  quarter: DisplayQuarter;
  monthRange: string;
  status: "Locked" | "Override" | "Baseline";
  planTarget: number | null;
  baselineCapped: number;
  scenarioCapped: number;
  scenarioExpected: number;
  gapToPlan: number | null;
}

export const OVERRIDE_FIELDS: OverrideFieldConfig[] = [
  {
    key: "mqlToS0",
    label: "MQL to S0",
    inputKind: "percent",
    step: 0.005,
    min: 0,
    max: 1,
    help: "Baseline marketing-to-S0 conversion for this quarter. Edit it to test an override.",
    format: formatPercent,
  },
  {
    key: "s0ToS1",
    label: "S0 to S1",
    inputKind: "percent",
    step: 0.005,
    min: 0,
    max: 1,
    help: "Baseline S0-to-S1 progression for this quarter. Edit it to test an override.",
    format: formatPercent,
  },
  {
    key: "s1ToS2",
    label: "S1 to S2",
    inputKind: "percent",
    step: 0.005,
    min: 0,
    max: 1,
    help: "Baseline S1-to-S2 progression for this quarter. Edit it to test an override.",
    format: formatPercent,
  },
  {
    key: "avgDealSize",
    label: "Average Deal Size",
    inputKind: "currency",
    step: 5_000,
    min: 50_000,
    max: 1_000_000,
    help: "Baseline ARR per closed-won deal for this quarter. Edit it to test an override.",
    format: formatMoney,
  },
];

export function cumulative(values: number[]): number[] {
  const result: number[] = [];
  let running = 0;
  values.forEach((value) => {
    running += value;
    result.push(running);
  });
  return result;
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatPercentInput(value: number): string {
  return (value * 100).toFixed(1);
}

export function formatCountInput(value: number): string {
  return Math.round(value).toString();
}

export function formatCurrencyInput(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(Math.round(value));
}

export function formatSignedMoney(value: number): string {
  if (value > 0) return `+${formatMoney(value)}`;
  if (value < 0) return `-${formatMoney(Math.abs(value))}`;
  return formatMoney(0);
}

export function formatSavedDelta(value: number): string | undefined {
  if (Math.abs(value) < 0.5) return undefined;
  if (value > 0) return `+${formatMoney(value)} vs saved`;
  return `-${formatMoney(Math.abs(value))} vs saved`;
}

export function formatWeeklyVolume(value: number): string {
  return `${new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(Math.round(value))}/wk`;
}

export function formatWeeklyInput(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(Math.round(value));
}

/**
 * Sum the values for months that belong to the given quarter, using the
 * snapshot-emitted parallel array `quarter_by_month`. Both inputs are parallel
 * to `values` (and to `snapshot.scenario_building_blocks.months`).
 */
export function sumQuarter(
  quarterByMonth: readonly (string | null)[],
  quarter: DisplayQuarter,
  values: number[],
): number {
  return quarterByMonth.reduce<number>((total, q, index) => {
    if (q !== quarter) return total;
    return total + (values[index] ?? 0);
  }, 0);
}

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Render a friendly label for the months that fall in the given quarter,
 * e.g. "May-Jul". Reads the parallel `quarter_by_month` array; falls back
 * to the quarter label itself if no months match.
 */
export function quarterMonthRange(
  months: string[],
  quarterByMonth: readonly (string | null)[],
  quarter: DisplayQuarter,
): string {
  const labels = months
    .map((month, index) => (quarterByMonth[index] === quarter ? month : null))
    .filter((m): m is string => m !== null)
    .map((month) => {
      const monthIndex = Number(month.slice(5, 7)) - 1;
      return MONTH_LABELS[monthIndex] ?? month.slice(5, 7);
    });

  if (labels.length === 0) return quarter;
  if (labels.length === 1) return labels[0] ?? quarter;
  return `${labels[0]}-${labels[labels.length - 1]}`;
}

export function clampValue(value: number, min?: number, max?: number): number {
  if (typeof min === "number") value = Math.max(value, min);
  if (typeof max === "number") value = Math.min(value, max);
  return value;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function getPlanRateReference(value: unknown): number | null {
  const container = asRecord(value);
  const blended = asRecord(container?.blended);
  const rate = typeof blended?.rate === "number" ? blended.rate : null;
  if (rate === null) return null;
  return rate;
}

export function getQuarterPlanReference(
  quarter: DisplayQuarter,
  quarterRow: Record<string, unknown> | undefined,
  plan: PlanPreset | null,
  options?: {
    snapshotAsOf?: string | null;
    evaluationAsOf?: string;
    timeZone?: string;
  },
): QuarterPlanReference {
  const funnelTieout = asRecord(quarterRow?.funnel_tieout);
  const mqlWeeklyRow = asRecord(funnelTieout?.mqls_weekly);
  const conversionRates = asRecord(quarterRow?.conversion_rates);
  const snapshotAsOf = options?.snapshotAsOf ?? null;

  if (!plan?.availability.comparableOnOperatorPages) {
    return {
      comparable: false,
      quarterlySupported: false,
      quarterEndAeTarget: null,
      mqlWeekly: null,
      mqlToS0: null,
      s0ToS1: null,
      s1ToS2: null,
      avgDealSize: null,
      provenance: {
        mqlWeekly: null,
        mqlToS0: null,
        s0ToS1: null,
        s1ToS2: null,
      },
      note:
        "The selected plan has no operator-comparable default view, so quarter-level seat, pacing, and conversion references are suppressed on operator pages.",
    };
  }

  if (!plan.availability.quarterlyComparable) {
    return {
      comparable: true,
      quarterlySupported: false,
      quarterEndAeTarget: null,
      mqlWeekly: null,
      mqlToS0: null,
      s0ToS1: null,
      s1ToS2: null,
      avgDealSize:
        typeof plan.assumptions.avgDealSize === "number"
          ? plan.assumptions.avgDealSize
          : null,
      provenance: {
        mqlWeekly: null,
        mqlToS0: null,
        s0ToS1: null,
        s1ToS2: null,
      },
      note:
        "The selected comparable view does not support quarterly grain, so quarter-level seat, pacing, and conversion references are intentionally suppressed rather than synthesized.",
    };
  }

  const mqlWeeklyResolution = resolvePlanPacingField(plan, quarter, "mqls_weekly", {
    snapshotFallbackValue: typeof mqlWeeklyRow?.plan === "number" ? mqlWeeklyRow.plan : null,
    snapshotAsOf,
    evaluationAsOf: options?.evaluationAsOf,
    timeZone: options?.timeZone,
  });
  const mqlToS0Resolution = resolvePlanPacingField(plan, quarter, "mql_to_s0", {
    snapshotFallbackValue: getPlanRateReference(conversionRates?.mql_to_s0),
    snapshotAsOf,
    evaluationAsOf: options?.evaluationAsOf,
    timeZone: options?.timeZone,
  });
  const s0ToS1Resolution = resolvePlanPacingField(plan, quarter, "s0_to_s1", {
    snapshotFallbackValue: getPlanRateReference(conversionRates?.s0_to_s1),
    snapshotAsOf,
    evaluationAsOf: options?.evaluationAsOf,
    timeZone: options?.timeZone,
  });
  const s1ToS2Resolution = resolvePlanPacingField(plan, quarter, "s1_to_s2", {
    snapshotFallbackValue: getPlanRateReference(conversionRates?.s1_to_s2),
    snapshotAsOf,
    evaluationAsOf: options?.evaluationAsOf,
    timeZone: options?.timeZone,
  });

  const hasFallback =
    mqlWeeklyResolution.source === "fallback" ||
    mqlToS0Resolution.source === "fallback" ||
    s0ToS1Resolution.source === "fallback" ||
    s1ToS2Resolution.source === "fallback";
  const hasPlanPacing =
    mqlWeeklyResolution.source === "plan" ||
    mqlToS0Resolution.source === "plan" ||
    s0ToS1Resolution.source === "plan" ||
    s1ToS2Resolution.source === "plan";
  const hasStaleField =
    Boolean(mqlWeeklyResolution.provenance?.stale) ||
    Boolean(mqlToS0Resolution.provenance?.stale) ||
    Boolean(s0ToS1Resolution.provenance?.stale) ||
    Boolean(s1ToS2Resolution.provenance?.stale);
  const selectedPlanAeTarget = getPlanSeatQuarterTarget(plan, quarter);

  let note =
    "Quarter bookings use the selected comparable view. Seat targets stay owned by the selected view's declared seat owner component.";
  if (hasPlanPacing && hasFallback) {
    note += " Explicit plan pacing fields are preserved, and missing pacing fields fall back to the saved snapshot field-by-field.";
  } else if (hasPlanPacing) {
    note += " Pacing references come from the selected plan's quarter package.";
  } else if (hasFallback) {
    note += " Pacing references fall back to the saved snapshot because the selected plan does not ship every field explicitly.";
  } else {
    note += " No quarter-scoped pacing references are available for this quarter.";
  }
  if (hasStaleField) {
    note += " At least one visible pacing field is stale under the v2 freshness rule.";
  }

  return {
    comparable: true,
    quarterlySupported: true,
    quarterEndAeTarget: selectedPlanAeTarget,
    mqlWeekly: mqlWeeklyResolution.value,
    mqlToS0: mqlToS0Resolution.value,
    s0ToS1: s0ToS1Resolution.value,
    s1ToS2: s1ToS2Resolution.value,
    avgDealSize:
      typeof plan?.assumptions.avgDealSize === "number"
        ? plan.assumptions.avgDealSize
        : null,
    provenance: {
      mqlWeekly: mqlWeeklyResolution.provenance,
      mqlToS0: mqlToS0Resolution.provenance,
      s0ToS1: s0ToS1Resolution.provenance,
      s1ToS2: s1ToS2Resolution.provenance,
    },
    note,
  };
}

export function getQuarterMarketingMqlWeekly(
  quarterRow: Record<string, unknown> | undefined,
): number | null {
  if (!quarterRow) return null;
  const sourceBreakdown =
    quarterRow.source_breakdown && typeof quarterRow.source_breakdown === "object"
      ? (quarterRow.source_breakdown as Record<string, unknown>)
      : null;
  const streams =
    sourceBreakdown?.streams && typeof sourceBreakdown.streams === "object"
      ? (sourceBreakdown.streams as Record<string, unknown>)
      : null;
  const marketingStream =
    streams?.marketing_sdr && typeof streams.marketing_sdr === "object"
      ? (streams.marketing_sdr as Record<string, unknown>)
      : null;
  return typeof marketingStream?.weekly_input === "number" ? marketingStream.weekly_input : null;
}

export function resetQuarterOverrides(
  current: ScenarioOverrides,
  baseline: ScenarioOverrides,
  quarter: ScenarioQuarterKey,
): ScenarioOverrides {
  const next = cloneScenarioOverrides(current);
  next[quarter] = {
    ...baseline[quarter],
    aeMonthTargets: [...baseline[quarter].aeMonthTargets] as [number, number, number],
  };
  return next;
}

export function copyQuarterAssumptionsForward(
  current: ScenarioOverrides,
  sourceQuarter: ScenarioQuarterKey,
  sourceMqlWeekly: number | null,
  savedMqlWeeklyLookup: Record<ScenarioQuarterKey, number | null>,
): ScenarioOverrides {
  const next = cloneScenarioOverrides(current);
  const source = next[sourceQuarter];
  // Object.keys preserves insertion order, and overrides are built from
  // snapshot.scenario_building_blocks.overridable_quarters in order — so this
  // gives us the ordered list of overridable quarters for the active profile.
  const orderedQuarters = Object.keys(next);
  const sourceIndex = orderedQuarters.indexOf(sourceQuarter);

  orderedQuarters.forEach((quarter, quarterIndex) => {
    if (quarterIndex <= sourceIndex) return;
    next[quarter].mqlToS0 = source.mqlToS0;
    next[quarter].s0ToS1 = source.s0ToS1;
    next[quarter].s1ToS2 = source.s1ToS2;
    next[quarter].avgDealSize = source.avgDealSize;

    const savedMqlWeekly = savedMqlWeeklyLookup[quarter];
    if (sourceMqlWeekly !== null && savedMqlWeekly !== null && savedMqlWeekly > 0) {
      next[quarter].mqlChangePct = sourceMqlWeekly / savedMqlWeekly - 1;
    }
  });

  return next;
}
