import { formatMoney } from "./format";
import {
  getPlanQuarterTarget,
  getPlanSeatQuarterTarget,
  resolvePlanPacingField,
} from "./plans";
import type { PlanPacingFieldId, PlanPreset } from "./plans";
import type {
  FunnelHealthConversionRate,
  FunnelHealthConversionRateByStream,
  FunnelHealthData,
  FunnelHealthExpansionBreakdown,
  FunnelHealthQuarter,
  FunnelHealthSourceStream,
  Snapshot,
} from "../types/snapshot";

type DeltaTone = "positive" | "negative" | "neutral";

interface FunnelHealthViewModelInput {
  snapshot: Snapshot;
  plan: PlanPreset | null;
  selectedQuarter?: string;
}

export interface FunnelHealthMetric {
  label: string;
  value: string;
  delta?: string;
  deltaType?: "decrease" | "moderateIncrease" | "unchanged";
}

interface FunnelHealthNotice {
  title: string;
  color: "red" | "emerald";
  message: string;
}

export interface FunnelHealthPaceRow {
  stage: string;
  plan: string;
  actual: string;
  delta: string;
  deltaPct: string;
  deltaTone: DeltaTone;
}

export interface FunnelHealthRateRow {
  transition: string;
  rate: string;
  source: string;
  sourceKey: string;
  sampleSize: string;
  methodology: string;
}

interface FunnelHealthStreamRateColumn {
  key: string;
  label: string;
}

interface FunnelHealthStreamRateCell {
  columnKey: string;
  rate: string;
  sampleSize: string | null;
}

interface FunnelHealthStreamRateRow {
  transition: string;
  cells: FunnelHealthStreamRateCell[];
}

export interface FunnelHealthConversionStreamSection {
  title: string;
  subtitle: string;
  hasConversionRates: boolean;
  columns: FunnelHealthStreamRateColumn[];
  rows: FunnelHealthStreamRateRow[];
}

interface FunnelHealthSourceStreamRow {
  key: string;
  displayName: string;
  weeklyInput: string;
  weeklyS0: string;
  weeklyS1: string;
  weeklyS2: string;
  quarterPipeline: string;
  actualOpps: string;
  actualPipeline: string;
}

export interface FunnelHealthSourceStreams {
  title: string;
  mode: string;
  rows: FunnelHealthSourceStreamRow[];
  total: Omit<FunnelHealthSourceStreamRow, "key" | "displayName">;
  showActualColumns: boolean;
}

interface FunnelHealthExpansionMetric {
  label: string;
  value: string;
  tone: "slate" | "emerald";
  note?: string;
}

interface FunnelHealthExpansionRow {
  key: string;
  label: string;
  arr: string;
  share: string;
}

export interface FunnelHealthExpansion {
  title: string;
  subtitle: string;
  metrics: FunnelHealthExpansionMetric[];
  rows: FunnelHealthExpansionRow[];
  totalArr: string;
}

interface FunnelHealthQuarterlySummaryRow {
  quarter: string;
  selected: boolean;
  bookings: string;
}

export interface FunnelHealthQuarterlySummary {
  headers: string[];
  rows: FunnelHealthQuarterlySummaryRow[];
}

interface FunnelHealthWaterfallDatum {
  stage: string;
  plan: number | null;
  trajectory: number | null;
}

interface FunnelHealthWaterfallQuarter {
  quarter: string;
  data: FunnelHealthWaterfallDatum[];
  primaryValues: Array<number | null>;
}

export interface FunnelHealthWaterfalls {
  quarters: FunnelHealthWaterfallQuarter[];
  emptyMessage: string;
}

interface FunnelHealthArrMixComponent {
  salesLed: number;
  plg: number;
  expansion: number;
}

interface FunnelHealthArrMixQuarter {
  quarter: string;
  plan: FunnelHealthArrMixComponent;
  trajectory: FunnelHealthArrMixComponent;
}

export interface FunnelHealthArrMix {
  hasBreakdown: boolean;
  quarters: FunnelHealthArrMixQuarter[];
  suppressedMessage: string;
}

interface FunnelHealthViewModel {
  quarters: string[];
  selectedQuarter: string;
  metrics: FunnelHealthMetric[];
  notices: FunnelHealthNotice[];
  alerts: FunnelHealthNotice[];
  paceRows: FunnelHealthPaceRow[];
  rateRows: FunnelHealthRateRow[];
  conversionStreams: FunnelHealthConversionStreamSection;
  sourceStreams: FunnelHealthSourceStreams | null;
  expansion: FunnelHealthExpansion | null;
  quarterlySummary: FunnelHealthQuarterlySummary;
  waterfalls: FunnelHealthWaterfalls;
  arrMix: FunnelHealthArrMix;
}

const SOURCE_LABELS: { [source: string]: string | undefined } = {
  registry: "Config assumption",
  blended_cohort: "Blended cohort",
  Salesforce: "Salesforce observed",
  warehouse: "warehouse observed",
  config: "Config assumption",
  static: "Static config",
  plan: "Plan config",
};

const STREAM_RATE_COLUMNS = [
  { key: "marketing_sdr", label: "Marketing/SDR" },
  { key: "ae_selfgen", label: "AE Self-Gen" },
  { key: "plg", label: "PLG" },
] as const;

const FUNNEL_STAGE_KEYS = [
  "mqls_weekly",
  "s0_weekly",
  "s1_weekly",
  "s2_weekly",
] as const;

const FUNNEL_STAGE_LABELS: { [stage: string]: string | undefined } = {
  mqls_weekly: "MQLs / wk",
  s0_weekly: "S0 / wk",
  s1_weekly: "S1 / wk",
  s2_weekly: "S2 / wk",
};

const RATE_TRANSITIONS: Array<{ key: PlanPacingFieldId; label: string }> = [
  { key: "mql_to_s0", label: "MQL to S0 rate" },
  { key: "s0_to_s1", label: "S0 to S1 rate" },
  { key: "s1_to_s2", label: "S1 to S2 rate" },
];

export function buildFunnelHealthViewModel({
  snapshot,
  plan,
  selectedQuarter,
}: FunnelHealthViewModelInput): FunnelHealthViewModel {
  const data = snapshot.model_output.funnel_health;
  const quarters = data.trajectory_quarters.map((quarter) => quarter.quarter);
  const activeQuarter = resolveSelectedQuarter(quarters, selectedQuarter);
  const selected = data.trajectory_quarters.find(
    (quarter) => quarter.quarter === activeQuarter,
  );

  const comparablePlanActive = plan?.availability.comparableOnOperatorPages ?? false;
  const comparableQuarterly = plan?.availability.quarterlyComparable ?? false;

  return {
    quarters,
    selectedQuarter: activeQuarter,
    metrics: buildMetrics({
      plan,
      quarter: selected,
      comparablePlanActive,
      comparableQuarterly,
    }),
    notices: buildPlanNotices(plan, comparablePlanActive, comparableQuarterly),
    alerts: buildAlerts(data),
    paceRows: buildPaceRows({
      snapshot,
      plan,
      quarter: selected,
      comparablePlanActive,
      comparableQuarterly,
    }),
    rateRows: buildRateRows(data),
    conversionStreams: buildConversionStreamSection(selected, data),
    sourceStreams: buildSourceStreams(selected, data),
    expansion: buildExpansion(selected),
    quarterlySummary: buildQuarterlySummary(data, activeQuarter),
    waterfalls: buildWaterfalls({
      snapshot,
      plan,
      data,
      comparablePlanActive,
      comparableQuarterly,
    }),
    arrMix: buildArrMix({ data, plan, comparablePlanActive, comparableQuarterly }),
  };
}

function resolveSelectedQuarter(
  quarters: string[],
  selectedQuarter: string | undefined,
): string {
  if (selectedQuarter && quarters.includes(selectedQuarter)) return selectedQuarter;
  return quarters[0] ?? "";
}

function buildMetrics({
  plan,
  quarter,
  comparablePlanActive,
  comparableQuarterly,
}: {
  plan: PlanPreset | null;
  quarter: FunnelHealthQuarter | undefined;
  comparablePlanActive: boolean;
  comparableQuarterly: boolean;
}): FunnelHealthMetric[] {
  const selectedPlanBookings =
    quarter && comparablePlanActive && comparableQuarterly
      ? getPlanQuarterTarget(plan, quarter.quarter)
      : null;
  const selectedPlanAes =
    quarter && comparablePlanActive && comparableQuarterly
      ? getPlanSeatQuarterTarget(plan, quarter.quarter)
      : null;
  const bottomsUp = quarter?.bottoms_up;
  const actuals = quarter?.actuals;
  const reforecast = quarter?.reforecast;
  const gap = quarter?.gap;

  const buSalesLed = numberOrNull(quarter?.bu_sales_led_arr ?? bottomsUp?.sales_led_arr);
  const actualBookings = numberOrNull(actuals?.bookings ?? reforecast?.actual_bookings);
  const reforecastBookings = numberOrNull(reforecast?.reforecast_bookings);
  const gapPct = numberOrNull(gap?.bookings_pct);
  const gapStatus = gap?.status ?? null;
  const buAes = numberOrNull(bottomsUp?.total_aes);
  const rampedAes = numberOrNull(bottomsUp?.ramped_aes);
  const elapsedFraction = numberOrNull(reforecast?.elapsed_fraction);

  return [
    {
      label: "Plan Bookings",
      value: selectedPlanBookings !== null ? formatMoney(selectedPlanBookings) : "—",
    },
    {
      label: "Reforecast",
      value:
        reforecastBookings !== null
          ? formatMoney(reforecastBookings)
          : buSalesLed !== null
            ? formatMoney(buSalesLed)
            : "—",
      delta: gapPct !== null ? `${(gapPct * 100).toFixed(0)}% gap` : undefined,
      deltaType:
        gapStatus === "critical_gap"
          ? "decrease"
          : gapPct !== null && gapPct > 0
            ? "decrease"
            : "moderateIncrease",
    },
    {
      label: "Actual Bookings",
      value: actualBookings !== null ? formatMoney(actualBookings) : "—",
      delta:
        elapsedFraction !== null
          ? `${(elapsedFraction * 100).toFixed(0)}% through Q`
          : undefined,
      deltaType: "unchanged",
    },
    {
      label: "AEs (Plan / Model)",
      value: `${selectedPlanAes ?? "—"} / ${buAes ?? "—"}`,
      delta: rampedAes !== null ? `${rampedAes} ramped` : undefined,
      deltaType: "unchanged",
    },
    {
      label: "Confidence",
      value: quarter?.confidence_tier ?? "—",
    },
  ];
}

function buildPlanNotices(
  plan: PlanPreset | null,
  comparablePlanActive: boolean,
  comparableQuarterly: boolean,
): FunnelHealthNotice[] {
  const notices: FunnelHealthNotice[] = [];
  if (!comparablePlanActive && plan) {
    notices.push({
      title: "Selected Plan Not Comparable",
      color: "red",
      message:
        `${plan.name} does not ship an operator-comparable default view. ` +
        "Funnel Health suppresses plan-facing top metrics, seat targets, pacing sections, and conversion targets.",
    });
  }
  if (comparablePlanActive && !comparableQuarterly) {
    notices.push({
      title: "Quarterly Plan Support Unavailable",
      color: "red",
      message:
        "The selected comparable view does not support quarterly grain. Quarter-scoped plan targets, pacing, and conversion references are suppressed here.",
    });
  }
  return notices;
}

function buildPaceRows({
  snapshot,
  plan,
  quarter,
  comparablePlanActive,
  comparableQuarterly,
}: {
  snapshot: Snapshot;
  plan: PlanPreset | null;
  quarter: FunnelHealthQuarter | undefined;
  comparablePlanActive: boolean;
  comparableQuarterly: boolean;
}): FunnelHealthPaceRow[] {
  const selectedMqlWeekly = resolvePlanPacingField(
    plan,
    quarter?.quarter ?? "",
    "mqls_weekly",
    {
      snapshotFallbackValue: quarter?.funnel_tieout?.mqls_weekly?.plan ?? null,
      snapshotAsOf: snapshot.as_of,
    },
  );
  const selectedMqlToS0 = resolvePlanPacingField(
    plan,
    quarter?.quarter ?? "",
    "mql_to_s0",
    {
      snapshotFallbackValue: getPlanRateReference(quarter?.conversion_rates?.mql_to_s0),
      snapshotAsOf: snapshot.as_of,
    },
  );
  const selectedS0ToS1 = resolvePlanPacingField(
    plan,
    quarter?.quarter ?? "",
    "s0_to_s1",
    {
      snapshotFallbackValue: getPlanRateReference(quarter?.conversion_rates?.s0_to_s1),
      snapshotAsOf: snapshot.as_of,
    },
  );
  const selectedS1ToS2 = resolvePlanPacingField(
    plan,
    quarter?.quarter ?? "",
    "s1_to_s2",
    {
      snapshotFallbackValue: getPlanRateReference(quarter?.conversion_rates?.s1_to_s2),
      snapshotAsOf: snapshot.as_of,
    },
  );
  const selectedPlanBookings =
    quarter && comparablePlanActive && comparableQuarterly
      ? getPlanQuarterTarget(plan, quarter.quarter)
      : null;
  const selectedPlanAes =
    quarter && comparablePlanActive && comparableQuarterly
      ? getPlanSeatQuarterTarget(plan, quarter.quarter)
      : null;
  const bottomsUp = quarter?.bottoms_up;
  const buSalesLed = numberOrNull(quarter?.bu_sales_led_arr ?? bottomsUp?.sales_led_arr);
  const buAes = numberOrNull(bottomsUp?.total_aes);

  const rows: FunnelHealthPaceRow[] = FUNNEL_STAGE_KEYS.map((stage) =>
    buildPaceRow({
      stage: FUNNEL_STAGE_LABELS[stage] ?? stage,
      plan: comparablePlanActive && comparableQuarterly ? selectedMqlWeekly.value : null,
      actual: quarter?.funnel_tieout?.[stage]?.actual ?? null,
    }),
  );

  for (const transition of RATE_TRANSITIONS) {
    const planRate =
      transition.key === "mql_to_s0"
        ? selectedMqlToS0.value
        : transition.key === "s0_to_s1"
          ? selectedS0ToS1.value
          : selectedS1ToS2.value;
    rows.push(
      buildPaceRow({
        stage: transition.label,
        plan: planRate,
        actual: snapshot.model_output.funnel_health.funnel_rates[transition.key] ?? null,
        isRate: true,
      }),
    );
  }

  rows.push(
    buildPaceRow({
      stage: "AEs in Seat",
      plan: selectedPlanAes,
      actual: buAes,
      valueDecimals: 0,
    }),
  );
  rows.push(
    buildPaceRow({
      stage: "Sales-Led ARR",
      plan: selectedPlanBookings,
      actual: buSalesLed,
      isMoney: true,
    }),
  );

  return rows;
}

function buildRateRows(data: FunnelHealthData): FunnelHealthRateRow[] {
  const seenFunnelRateKeys = new Set<string>();
  const rows = Object.entries(data.funnel_rates).flatMap(([key, value]) => {
    const canonicalKey = key === "plg_pql_to_s0" ? "plg_pql_to_s1" : key;
    if (seenFunnelRateKeys.has(canonicalKey)) return [];
    seenFunnelRateKeys.add(canonicalKey);

    const desc =
      data.funnel_rate_descriptions?.[key] ??
      data.funnel_rate_descriptions?.[canonicalKey] ??
      null;
    const source = desc?.source ?? "plan";
    const sampleSize = desc?.n ?? 0;
    const methodology =
      desc?.methodology ?? defaultMethodologyLabel(source, canonicalKey);

    return [
      {
        transition: formatTransition(canonicalKey),
        rate: pct(value),
        source: humanSourceLabel(source),
        sourceKey: source,
        sampleSize: sampleSize > 0 ? `n=${sampleSize}` : "—",
        methodology: methodology || "—",
      },
    ];
  });

  const rollingS2 = data.rolling_s2_to_won;
  if (typeof rollingS2?.rate === "number") {
    rows.push({
      transition: "s2 → won",
      rate: pct(rollingS2.rate),
      source: rollingS2.source ?? "unknown",
      sourceKey: rollingS2.source ?? "unknown",
      sampleSize: `n=${rollingS2.sample ?? 0}`,
      methodology: rollingS2.method || "—",
    });
  }

  return rows;
}

function buildConversionStreamSection(
  quarter: FunnelHealthQuarter | undefined,
  data: FunnelHealthData,
): FunnelHealthConversionStreamSection {
  const conversionRates = quarter?.conversion_rates;
  const profileHasPlgSourceStream = hasPlgSourceStream(data);
  const columns = STREAM_RATE_COLUMNS.filter((column) => {
    if (column.key === "plg" && !profileHasPlgSourceStream) return false;
    return Object.values(conversionRates ?? {}).some((streamsByTransition) =>
      readRate(streamsByTransition?.[column.key]) !== null,
    );
  }).map((column) => ({ key: column.key, label: column.label }));

  return {
    title: `${quarter?.quarter ?? ""} Conversion Rates by Stream`,
    subtitle: "Per-stream rates used in bottoms-up model for this quarter.",
    hasConversionRates: Object.keys(conversionRates ?? {}).length > 0,
    columns,
    rows: Object.entries(conversionRates ?? {}).map(([transition, streams]) => ({
      transition: formatTransition(transition),
      cells: columns.map((column) => {
        const stream = streams?.[column.key];
        return {
          columnKey: column.key,
          rate: pct(readRate(stream)),
          sampleSize: stream?.n ? `n=${stream.n}` : null,
        };
      }),
    })),
  };
}

function buildSourceStreams(
  quarter: FunnelHealthQuarter | undefined,
  data: FunnelHealthData,
): FunnelHealthSourceStreams | null {
  const streams = Object.values(quarter?.source_breakdown?.streams ?? {}).filter(
    isDefined,
  );
  const profileHasPlgSourceStream = hasPlgSourceStream(data);
  const visibleStreams = streams.filter((stream) => {
    return stream.stream_key !== "plg" || profileHasPlgSourceStream;
  });
  if (visibleStreams.length === 0) return null;

  const showActualColumns = hasActualStreamData(visibleStreams);
  const rows = visibleStreams.map((stream) => formatSourceStreamRow(stream));
  const total = formatSourceStreamTotals(visibleStreams);

  return {
    title: `${quarter?.quarter ?? ""} Source Stream Breakdown`,
    mode: quarter?.source_breakdown?.mode ?? "unknown",
    rows,
    total,
    showActualColumns,
  };
}

function buildExpansion(
  quarter: FunnelHealthQuarter | undefined,
): FunnelHealthExpansion | null {
  const expansion = quarter?.expansion_breakdown;
  if (!expansion) return null;
  const total = numeric(expansion.total_expansion_arr);
  const rows = [
    { label: "Renewal Expansion", key: "renewal_expansion_arr" },
    { label: "Usage-Based Expansion", key: "usage_expansion_arr" },
    { label: "PLG Expansion", key: "plg_expansion_arr" },
    { label: "Consumption True-Forward", key: "consumption_true_forward_arr" },
  ].map((row) => {
    const value = expansionValue(expansion, row.key);
    return {
      key: row.key,
      label: row.label,
      arr: formatMoney(value),
      share: total > 0 ? `${((value / total) * 100).toFixed(1)}%` : "—",
    };
  });

  return {
    title: `${quarter?.quarter ?? ""} Expansion Workstream`,
    subtitle:
      "Expansion ARR breakdown by source: renewal upsell, usage-based, PLG, and consumption.",
    metrics: [
      {
        label: "Opening ARR",
        value: formatMoney(numeric(expansion.opening_arr)),
        tone: "slate",
      },
      {
        label: "Total Expansion",
        value: formatMoney(total),
        tone: "emerald",
      },
      {
        label: "Program Maturity",
        value: pct(numberOrNull(expansion.program_maturity_factor)),
        tone: "slate",
        note: "Fraction of expansion program that's operational and producing results.",
      },
      {
        label: "Renewable Sales-Led",
        value: formatMoney(numeric(expansion.renewable_sales_led_arr)),
        tone: "slate",
      },
    ],
    rows,
    totalArr: formatMoney(total),
  };
}

function buildQuarterlySummary(
  data: FunnelHealthData,
  selectedQuarter: string,
): FunnelHealthQuarterlySummary {
  return {
    headers: ["Quarter", "Bookings"],
    rows: data.trajectory_quarters.map((quarter) => ({
      quarter: quarter.quarter,
      selected: quarter.quarter === selectedQuarter,
      bookings: formatMoney(salesLedBookings(quarter)),
    })),
  };
}

function buildWaterfalls({
  snapshot,
  plan,
  data,
  comparablePlanActive,
  comparableQuarterly,
}: {
  snapshot: Snapshot;
  plan: PlanPreset | null;
  data: FunnelHealthData;
  comparablePlanActive: boolean;
  comparableQuarterly: boolean;
}): FunnelHealthWaterfalls {
  const quarters = data.trajectory_quarters
    .map((quarter) => {
      const planQuarter = data.plan_quarters.find(
        (candidate) => candidate.quarter === quarter.quarter,
      );
      const trajectoryFunnel = quarter.funnel_tieout;
      const planFunnel = planQuarter?.funnel_tieout;
      const planMqls =
        comparablePlanActive && comparableQuarterly
          ? resolvePlanPacingField(plan, quarter.quarter, "mqls_weekly", {
              snapshotFallbackValue: planFunnel?.mqls_weekly?.plan ?? null,
              snapshotAsOf: snapshot.as_of,
            }).value
          : null;
      const planS0 =
        comparablePlanActive && comparableQuarterly
          ? planFunnel?.s0_weekly?.plan ?? null
          : null;
      const planS1 =
        comparablePlanActive && comparableQuarterly
          ? planFunnel?.s1_weekly?.plan ?? null
          : null;
      const planS2 =
        comparablePlanActive && comparableQuarterly
          ? planFunnel?.s2_weekly?.plan ?? null
          : null;
      const dataRows = [
        {
          stage: "MQLs/wk",
          plan: planMqls,
          trajectory: trajectoryFunnel?.mqls_weekly?.actual ?? null,
        },
        {
          stage: "S0/wk",
          plan: planS0,
          trajectory: trajectoryFunnel?.s0_weekly?.actual ?? null,
        },
        {
          stage: "S1/wk",
          plan: planS1,
          trajectory: trajectoryFunnel?.s1_weekly?.actual ?? null,
        },
        {
          stage: "S2/wk",
          plan: planS2,
          trajectory: trajectoryFunnel?.s2_weekly?.actual ?? null,
        },
      ];
      const hasData = dataRows.some(
        (row) => typeof row.trajectory === "number" && Math.abs(row.trajectory) > 1e-9,
      );
      if (!hasData) return null;
      return {
        quarter: quarter.quarter,
        data: dataRows,
        primaryValues: dataRows.map((row) => row.trajectory),
      };
    })
    .filter(isDefined);

  return {
    quarters,
    emptyMessage:
      "Funnel waterfall data not available. Ensure snapshot includes weekly funnel metrics (mqls_weekly, s0_weekly, s1_weekly, s2_weekly) in quarter data.",
  };
}

function buildArrMix({
  data,
  plan,
  comparablePlanActive,
  comparableQuarterly,
}: {
  data: FunnelHealthData;
  plan: PlanPreset | null;
  comparablePlanActive: boolean;
  comparableQuarterly: boolean;
}): FunnelHealthArrMix {
  return {
    hasBreakdown: false,
    quarters: data.trajectory_quarters.map((quarter) => ({
      quarter: quarter.quarter,
      plan: {
        salesLed:
          comparablePlanActive && comparableQuarterly
            ? getPlanQuarterTarget(plan, quarter.quarter) ?? 0
            : 0,
        plg: 0,
        expansion: 0,
      },
      trajectory: {
        salesLed: salesLedBookings(quarter),
        plg: numeric(quarter.bu_plg_arr ?? quarter.bottoms_up?.plg_arr),
        expansion: numeric(quarter.bu_expansion_arr ?? quarter.bottoms_up?.expansion_arr),
      },
    })),
    suppressedMessage:
      "The selected comparable view does not own a multi-component scenario-modeled ARR mix in v2, so ARR mix plan breakdown is suppressed on operator pages.",
  };
}

function buildAlerts(data: FunnelHealthData): FunnelHealthNotice[] {
  const alerts: FunnelHealthNotice[] = [];
  for (const row of buildQuarterDiagnostics(data)) {
    if (row.mqlPlan !== null && row.mqlActual !== null && row.mqlActual > 0) {
      const ratio = row.mqlActual / row.mqlPlan;
      if (ratio < 0.7) {
        alerts.push({
          title: "Below Plan",
          color: "red",
          message: `${row.quarter}: MQLs/week at ${row.mqlActual} vs plan ${row.mqlPlan} (${(ratio * 100).toFixed(0)}% of plan)`,
        });
      } else if (ratio > 1.2) {
        alerts.push({
          title: "Above Plan",
          color: "emerald",
          message: `${row.quarter}: MQLs/week at ${row.mqlActual} vs plan ${row.mqlPlan} (${(ratio * 100).toFixed(0)}% of plan)`,
        });
      }
    }
    if (row.s2Plan !== null && row.s2Actual !== null && row.s2Actual > 0) {
      const ratio = row.s2Actual / row.s2Plan;
      if (ratio < 0.7) {
        alerts.push({
          title: "Below Plan",
          color: "red",
          message: `${row.quarter}: S2/week at ${row.s2Actual} vs plan ${row.s2Plan} (${(ratio * 100).toFixed(0)}% of plan)`,
        });
      }
    }
  }
  return alerts;
}

function buildQuarterDiagnostics(data: FunnelHealthData) {
  return data.trajectory_quarters.map((quarter) => {
    const planQuarter = data.plan_quarters.find(
      (candidate) => candidate.quarter === quarter.quarter,
    );
    const actuals = quarter.actuals;
    const planFunnel = planQuarter?.funnel_tieout;
    return {
      quarter: quarter.quarter,
      mqlPlan: numberOrNull(planFunnel?.mqls_weekly?.plan),
      mqlActual: numberOrNull(actuals?.mqls_weekly),
      s2Plan: numberOrNull(planFunnel?.s2_weekly?.plan),
      s2Actual: numberOrNull(actuals?.s2_weekly),
    };
  });
}

function buildPaceRow({
  stage,
  plan,
  actual,
  isRate = false,
  isMoney = false,
  valueDecimals = 1,
}: {
  stage: string;
  plan: number | null;
  actual: number | null;
  isRate?: boolean;
  isMoney?: boolean;
  valueDecimals?: number;
}): FunnelHealthPaceRow {
  const delta = plan !== null && actual !== null ? actual - plan : null;
  return {
    stage,
    plan: formatPaceValue(plan, { isRate, isMoney, decimals: valueDecimals }),
    actual: formatPaceValue(actual, { isRate, isMoney, decimals: valueDecimals }),
    delta: formatDelta(delta, { isRate, isMoney }),
    deltaPct: deltaPctStr(plan, actual),
    deltaTone: deltaTone(delta),
  };
}

function formatPaceValue(
  value: number | null,
  options: { isRate: boolean; isMoney: boolean; decimals: number },
): string {
  if (value === null) return "—";
  if (options.isRate) return pct(value);
  if (options.isMoney) return formatMoney(value);
  return num(value, options.decimals);
}

function formatDelta(
  delta: number | null,
  options: { isRate: boolean; isMoney: boolean },
): string {
  if (delta === null) return "—";
  if (options.isMoney) return formatMoney(delta);
  if (options.isRate) return `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}pp`;
  return `${delta >= 0 ? "+" : ""}${num(delta, 1)}`;
}

function getPlanRateReference(
  value: FunnelHealthConversionRateByStream | undefined,
): number | null {
  return readRate(value?.blended);
}

function readRate(value: FunnelHealthConversionRate | undefined): number | null {
  return typeof value?.rate === "number" ? value.rate : null;
}

function streamHasPipelineActivity(stream: FunnelHealthSourceStream | undefined): boolean {
  if (!stream) return false;
  return [
    stream.weekly_input,
    stream.weekly_s0_count,
    stream.weekly_s1_count,
    stream.weekly_s2_count,
    stream.quarter_pipeline_created,
    stream.actual_opp_count,
    stream.actual_pipeline,
  ].some((value) => typeof value === "number" && Math.abs(value) > 1e-9);
}

function hasPlgSourceStream(data: FunnelHealthData): boolean {
  return data.trajectory_quarters.some((quarter) =>
    streamHasPipelineActivity(quarter.source_breakdown?.streams?.plg),
  );
}

function hasActualStreamData(streams: FunnelHealthSourceStream[]): boolean {
  return streams.some((stream) => {
    return (
      (typeof stream.actual_opp_count === "number" &&
        Math.abs(stream.actual_opp_count) > 1e-9) ||
      (typeof stream.actual_pipeline === "number" &&
        Math.abs(stream.actual_pipeline) > 1e-9)
    );
  });
}

function formatSourceStreamRow(
  stream: FunnelHealthSourceStream,
): FunnelHealthSourceStreamRow {
  return {
    key: stream.stream_key,
    displayName: stream.display_name ?? stream.stream_key,
    weeklyInput: num(numeric(stream.weekly_input), 1),
    weeklyS0: num(numeric(stream.weekly_s0_count), 1),
    weeklyS1: num(numeric(stream.weekly_s1_count), 1),
    weeklyS2: num(numeric(stream.weekly_s2_count), 1),
    quarterPipeline: formatMoney(numeric(stream.quarter_pipeline_created)),
    actualOpps: num(numeric(stream.actual_opp_count), 0),
    actualPipeline: formatMoney(numeric(stream.actual_pipeline)),
  };
}

function formatSourceStreamTotals(
  streams: FunnelHealthSourceStream[],
): Omit<FunnelHealthSourceStreamRow, "key" | "displayName"> {
  const sum = (pick: (stream: FunnelHealthSourceStream) => number | undefined) =>
    streams.reduce((total, stream) => total + numeric(pick(stream)), 0);
  return {
    weeklyInput: num(sum((stream) => stream.weekly_input), 1),
    weeklyS0: num(sum((stream) => stream.weekly_s0_count), 1),
    weeklyS1: num(sum((stream) => stream.weekly_s1_count), 1),
    weeklyS2: num(sum((stream) => stream.weekly_s2_count), 1),
    quarterPipeline: formatMoney(sum((stream) => stream.quarter_pipeline_created)),
    actualOpps: num(sum((stream) => stream.actual_opp_count), 0),
    actualPipeline: formatMoney(sum((stream) => stream.actual_pipeline)),
  };
}

function expansionValue(
  expansion: FunnelHealthExpansionBreakdown,
  key: string,
): number {
  switch (key) {
    case "renewal_expansion_arr":
      return numeric(expansion.renewal_expansion_arr);
    case "usage_expansion_arr":
      return numeric(expansion.usage_expansion_arr);
    case "plg_expansion_arr":
      return numeric(expansion.plg_expansion_arr);
    case "consumption_true_forward_arr":
      return numeric(expansion.consumption_true_forward_arr);
    default:
      return 0;
  }
}

function salesLedBookings(quarter: FunnelHealthQuarter): number {
  return numeric(quarter.bu_sales_led_arr ?? quarter.bottoms_up?.sales_led_arr);
}

function humanSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

function defaultMethodologyLabel(source: string, rateName: string): string {
  if (source === "registry") {
    return rateName === "mql_to_s0" ? "registry_activity_rate" : "registry_fallback";
  }
  if (source === "static") return "static_config_assumption";
  if (source === "plan") return "quarter_plan_assumption";
  return "";
}

function formatTransition(key: string): string {
  return key.replace(/_/g, " ").replace(/to/g, "→");
}

function deltaPctStr(plan: number | null, actual: number | null): string {
  if (plan === null || actual === null || plan === 0) return "—";
  const pctVal = ((actual - plan) / Math.abs(plan)) * 100;
  const sign = pctVal >= 0 ? "+" : "";
  return `${sign}${pctVal.toFixed(0)}%`;
}

function deltaTone(delta: number | null): DeltaTone {
  if (delta === null || delta === 0) return "neutral";
  return delta > 0 ? "positive" : "negative";
}

function pct(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(decimals);
}

function numberOrNull(value: number | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}

function numeric(value: number | null | undefined): number {
  return typeof value === "number" ? value : 0;
}

function isDefined<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}
