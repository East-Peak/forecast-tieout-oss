import { useState } from "react";
import {
  Card,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Callout,
  Metric,
  Text,
  Select,
  SelectItem,
} from "../components/ui";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { FunnelHealthData } from "../types/snapshot";
import { SectionHeader, MetricStrip, ProseNote } from "../components/workbook";
import { formatMoney } from "../lib/format";
import {
  AXIS_STYLE,
  GRID_STYLE,
  TOOLTIP_STYLE,
  LEGEND_STYLE,
} from "../lib/chartTheme";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import {
  getPlanQuarterTarget,
  getPlanSeatQuarterTarget,
  resolvePlanPacingField,
} from "../lib/plans";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getNestedNumber(
  obj: Record<string, unknown> | null | undefined,
  directKey: string,
  nestedPath: string[]
): number {
  if (!obj) return 0;
  if (typeof obj[directKey] === "number") return obj[directKey] as number;
  let current: unknown = obj;
  for (const key of nestedPath) {
    if (current && typeof current === "object") {
      current = (current as Record<string, unknown>)[key];
    } else {
      return 0;
    }
  }
  return typeof current === "number" ? current : 0;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function getPlanRateReference(value: unknown): number | null {
  const container = asRecord(value);
  const blended = asRecord(container?.blended);
  return typeof blended?.rate === "number" ? blended.rate : null;
}

function pct(v: number | null): string {
  if (v === null || v === undefined) return "\u2014";
  return `${(v * 100).toFixed(1)}%`;
}

function num(v: number | null | undefined, decimals = 0): string {
  if (v === null || v === undefined) return "\u2014";
  return v.toFixed(decimals);
}

const SOURCE_LABELS: Record<string, string> = {
  registry: "Config assumption",
  blended_cohort: "Blended cohort",
  Salesforce: "Salesforce observed",
  warehouse: "warehouse observed",
  config: "Config assumption",
  static: "Static config",
  plan: "Plan config",
};

function humanSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

function defaultMethodologyLabel(source: string, rateName: string): string {
  if (source === "registry") {
    return rateName === "mql_to_s0" ? "registry_activity_rate" : "registry_fallback";
  }
  if (source === "static") {
    return "static_config_assumption";
  }
  if (source === "plan") {
    return "quarter_plan_assumption";
  }
  return "";
}

function deltaColor(delta: number | null): string {
  if (delta === null) return "";
  if (delta > 0) return "text-emerald-600";
  if (delta < 0) return "text-red-600";
  return "";
}

function deltaPctStr(plan: number | null, actual: number | null): string {
  if (plan === null || actual === null || plan === 0) return "\u2014";
  const pctVal = ((actual - plan) / Math.abs(plan)) * 100;
  const sign = pctVal >= 0 ? "+" : "";
  return `${sign}${pctVal.toFixed(0)}%`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FunnelHealth() {
  const { snapshot, selectedPlan: plan, snapshotMeta } = usePlanningSessionContext();
  const data: FunnelHealthData = snapshot.model_output.funnel_health;
  const quarters = data.trajectory_quarters.map((q) => q.quarter);
  const [selectedQtr, setSelectedQtr] = useState(quarters[0] ?? "");

  const tq = data.trajectory_quarters.find((q) => q.quarter === selectedQtr);
  const tqR = tq as Record<string, unknown> | undefined;

  // --- Extract nested objects for selected quarter ---
  const bottomsUp = tqR?.bottoms_up as Record<string, unknown> | undefined;
  const actuals = tqR?.actuals as Record<string, unknown> | undefined;
  const funnelTieout = tqR?.funnel_tieout as Record<string, Record<string, unknown>> | undefined;
  const conversionRates = tqR?.conversion_rates as Record<string, Record<string, Record<string, unknown>>> | undefined;
  const sourceBreakdown = tqR?.source_breakdown as Record<string, unknown> | undefined;
  const expansionBreakdown = tqR?.expansion_breakdown as Record<string, unknown> | undefined;
  const reforecast = tqR?.reforecast as Record<string, unknown> | undefined;
  const gap = tqR?.gap as Record<string, unknown> | undefined;
  const comparablePlanActive = plan?.availability.comparableOnOperatorPages ?? false;
  const comparableQuarterly = plan?.availability.quarterlyComparable ?? false;
  const selectedPlanBookings =
    comparablePlanActive && comparableQuarterly ? getPlanQuarterTarget(plan, selectedQtr) : null;
  const selectedPlanAes =
    comparablePlanActive && comparableQuarterly ? getPlanSeatQuarterTarget(plan, selectedQtr) : null;
  const selectedMqlWeekly = resolvePlanPacingField(plan, selectedQtr, "mqls_weekly", {
    snapshotFallbackValue:
      ((tqR?.funnel_tieout as Record<string, Record<string, unknown>> | undefined)?.mqls_weekly
        ?.plan as number) ?? null,
    snapshotAsOf: snapshot.as_of,
  });
  const selectedMqlToS0 = resolvePlanPacingField(plan, selectedQtr, "mql_to_s0", {
    snapshotFallbackValue: getPlanRateReference(conversionRates?.mql_to_s0),
    snapshotAsOf: snapshot.as_of,
  });
  const selectedS0ToS1 = resolvePlanPacingField(plan, selectedQtr, "s0_to_s1", {
    snapshotFallbackValue: getPlanRateReference(conversionRates?.s0_to_s1),
    snapshotAsOf: snapshot.as_of,
  });
  const selectedS1ToS2 = resolvePlanPacingField(plan, selectedQtr, "s1_to_s2", {
    snapshotFallbackValue: getPlanRateReference(conversionRates?.s1_to_s2),
    snapshotAsOf: snapshot.as_of,
  });

  // --- Top-level metrics ---
  const planBookings = selectedPlanBookings;
  const buSalesLed = (tqR?.bu_sales_led_arr as number) ?? (bottomsUp?.sales_led_arr as number) ?? null;
  const actualBookings = (actuals?.bookings as number) ?? (reforecast?.actual_bookings as number) ?? null;
  const reforecastBookings = (reforecast?.reforecast_bookings as number) ?? null;
  const gapPct = (gap?.bookings_pct as number) ?? null;
  const gapStatus = (gap?.status as string) ?? null;
  const aes = selectedPlanAes;
  const buAes = (bottomsUp?.total_aes as number) ?? null;
  const rampedAes = (bottomsUp?.ramped_aes as number) ?? null;
  const confidenceTier = tqR?.confidence_tier as string | undefined;
  const elapsedFraction = (reforecast?.elapsed_fraction as number) ?? null;

  const topMetrics = [
    {
      label: "Plan Bookings",
      value: planBookings !== null ? formatMoney(planBookings) : "\u2014",
    },
    {
      label: "Reforecast",
      value: reforecastBookings !== null ? formatMoney(reforecastBookings) : buSalesLed !== null ? formatMoney(buSalesLed) : "\u2014",
      delta: gapPct !== null ? `${(gapPct * 100).toFixed(0)}% gap` : undefined,
      deltaType: (gapStatus === "critical_gap" ? "decrease" : gapPct !== null && gapPct > 0 ? "decrease" : "moderateIncrease") as "decrease" | "moderateIncrease" | "unchanged",
    },
    {
      label: "Actual Bookings",
      value: actualBookings !== null ? formatMoney(actualBookings) : "\u2014",
      delta: elapsedFraction !== null ? `${(elapsedFraction * 100).toFixed(0)}% through Q` : undefined,
      deltaType: "unchanged" as const,
    },
    {
      label: "AEs (Plan / Model)",
      value: `${aes ?? "\u2014"} / ${buAes ?? "\u2014"}`,
      delta: rampedAes !== null ? `${rampedAes} ramped` : undefined,
      deltaType: "unchanged" as const,
    },
    {
      label: "Confidence",
      value: confidenceTier ?? "\u2014",
    },
  ];

  // --- Weekly Funnel Pace Table ---
  const paceRows: {
    stage: string;
    plan: number | null;
    actual: number | null;
    isRate?: boolean;
  }[] = [];

  // Volume rows from funnel_tieout
  const stages = ["mqls_weekly", "s0_weekly", "s1_weekly", "s2_weekly"] as const;
  const stageLabels: Record<string, string> = {
    mqls_weekly: "MQLs / wk",
    s0_weekly: "S0 / wk",
    s1_weekly: "S1 / wk",
    s2_weekly: "S2 / wk",
  };
  for (const stage of stages) {
    const ft = funnelTieout?.[stage];
    paceRows.push({
      stage: stageLabels[stage],
      plan: comparablePlanActive && comparableQuarterly ? selectedMqlWeekly.value : null,
      actual: (ft?.actual as number) ?? null,
    });
  }

  // Conversion rate rows from conversion_rates (blended)
  const rateTransitions = [
    { key: "mql_to_s0", label: "MQL to S0 rate" },
    { key: "s0_to_s1", label: "S0 to S1 rate" },
    { key: "s1_to_s2", label: "S1 to S2 rate" },
  ];
  for (const rt of rateTransitions) {
    const runtimeRate = data.funnel_rates[rt.key] ?? null;
    const planRate =
      rt.key === "mql_to_s0"
        ? selectedMqlToS0.value
        : rt.key === "s0_to_s1"
          ? selectedS0ToS1.value
          : selectedS1ToS2.value;
    const actualRate = runtimeRate;
    paceRows.push({
      stage: rt.label,
      plan: planRate,
      actual: actualRate,
      isRate: true,
    });
  }

  // AEs in seat
  paceRows.push({
    stage: "AEs in Seat",
    plan: aes,
    actual: buAes,
  });

  // Sales-Led ARR
  paceRows.push({
    stage: "Sales-Led ARR",
    plan: planBookings,
    actual: buSalesLed,
  });

  // --- Observed Funnel Rate rows ---
  const seenFunnelRateKeys = new Set<string>();
  const funnelRateRows = Object.entries(data.funnel_rates).flatMap(
    ([key, value]) => {
      const canonicalKey = key === "plg_pql_to_s0" ? "plg_pql_to_s1" : key;
      if (seenFunnelRateKeys.has(canonicalKey)) {
        return [];
      }
      seenFunnelRateKeys.add(canonicalKey);

      const desc = data.funnel_rate_descriptions
        ? data.funnel_rate_descriptions[key] ?? data.funnel_rate_descriptions[canonicalKey]
        : null;
      let source = "plan";
      let sampleSize = 0;
      let methodology = "";
      if (desc && typeof desc === "object") {
        const d = desc as Record<string, unknown>;
        source = (d.source as string) ?? "plan";
        sampleSize = (d.n as number) ?? 0;
        methodology = (d.methodology as string) ?? "";
      }
      methodology = methodology || defaultMethodologyLabel(source, canonicalKey);
      return [{ rate_name: canonicalKey, observed_pct: value, source, sampleSize, methodology }];
    }
  );

  // --- Rolling S2 Win Rate ---
  const rollingS2 = data.rolling_s2_to_won;
  const hasRolling =
    rollingS2 && typeof rollingS2 === "object" && "rate" in rollingS2;
  const rollingRate = hasRolling
    ? (rollingS2 as Record<string, unknown>).rate as number
    : null;
  const rollingSample = hasRolling
    ? ((rollingS2 as Record<string, unknown>).sample as number) ?? 0
    : 0;
  const rollingSource = hasRolling
    ? ((rollingS2 as Record<string, unknown>).source as string) ?? "unknown"
    : "";
  const rollingMethod = hasRolling
    ? ((rollingS2 as Record<string, unknown>).method as string) ?? ""
    : "";

  // --- Source Stream Breakdown ---
  const streams = sourceBreakdown?.streams as Record<string, Record<string, unknown>> | undefined;
  const streamEntries = streams ? Object.values(streams).filter((s) => typeof s === "object") : [];

  // --- Expansion Breakdown ---
  const hasExpansion = expansionBreakdown && typeof expansionBreakdown === "object";

  // --- Quarterly summary across all quarters ---
  const quarterRows = data.trajectory_quarters.map((tq) => {
    const pq = data.plan_quarters.find((p) => p.quarter === tq.quarter);
    const a = (tq as Record<string, unknown>).actuals as
      | Record<string, unknown>
      | undefined;

    const mqlActual = (a?.mqls_weekly as number) ?? null;
    const s2Actual = (a?.s2_weekly as number) ?? null;
    const s0Actual = (a?.s0_weekly as number) ?? null;

    const funnel = (pq as Record<string, unknown> | undefined)
      ?.funnel_tieout as Record<string, Record<string, unknown>> | undefined;
    const mqlPlan = (funnel?.mqls_weekly?.plan as number) ?? null;
    const s2Plan = (funnel?.s2_weekly?.plan as number) ?? null;

    const bookings = getNestedNumber(tq, "bu_sales_led_arr", [
      "bottoms_up",
      "sales_led_arr",
    ]);

    return {
      quarter: tq.quarter,
      mql_plan: mqlPlan,
      mql_actual: mqlActual,
      s0_actual: s0Actual,
      s2_plan: s2Plan,
      s2_actual: s2Actual,
      bookings,
    };
  });

  // --- Funnel Waterfall: Plan vs Trajectory per quarter ---
  const waterfallByQuarter = data.trajectory_quarters.map((tq) => {
    const pq = data.plan_quarters.find((p) => p.quarter === tq.quarter);
    const tqR = tq as Record<string, unknown>;
    const pqR = pq as Record<string, unknown> | undefined;

    // Trajectory values come from funnel_tieout.{stage}.actual
    const trajFunnel = tqR.funnel_tieout as Record<string, Record<string, unknown>> | undefined;
    const trajMqls = (trajFunnel?.mqls_weekly?.actual as number) ?? null;
    const trajS0 = (trajFunnel?.s0_weekly?.actual as number) ?? null;
    const trajS1 = (trajFunnel?.s1_weekly?.actual as number) ?? null;
    const trajS2 = (trajFunnel?.s2_weekly?.actual as number) ?? null;

    // Plan values come from funnel_tieout.{stage}.plan (same structure on plan quarter)
    const planFunnel = pqR?.funnel_tieout as Record<string, Record<string, unknown>> | undefined;
    const planMqls =
      comparablePlanActive && comparableQuarterly
        ? resolvePlanPacingField(plan, tq.quarter, "mqls_weekly", {
            snapshotFallbackValue: (planFunnel?.mqls_weekly?.plan as number) ?? null,
            snapshotAsOf: snapshot.as_of,
          }).value
        : null;
    const planS0 = comparablePlanActive && comparableQuarterly ? (planFunnel?.s0_weekly?.plan as number) ?? null : null;
    const planS1 = comparablePlanActive && comparableQuarterly ? (planFunnel?.s1_weekly?.plan as number) ?? null : null;
    const planS2 = comparablePlanActive && comparableQuarterly ? (planFunnel?.s2_weekly?.plan as number) ?? null : null;

    return {
      quarter: tq.quarter,
      data: [
        { stage: "MQLs/wk", plan: planMqls, trajectory: trajMqls },
        { stage: "S0/wk", plan: planS0, trajectory: trajS0 },
        { stage: "S1/wk", plan: planS1, trajectory: trajS1 },
        { stage: "S2/wk", plan: planS2, trajectory: trajS2 },
      ],
      hasData:
        trajMqls !== null ||
        trajS0 !== null ||
        trajS2 !== null ||
        planMqls !== null ||
        planS0 !== null ||
        planS2 !== null,
    };
  });

  // --- ARR Mix: Plan vs Trajectory ---
  const arrMixByQuarter = data.trajectory_quarters.map((tq) => {
    const tqR = tq as Record<string, unknown>;

    const trajSalesLed = getNestedNumber(tq, "bu_sales_led_arr", ["bottoms_up", "sales_led_arr"]);
    const trajPlg = (tqR.bu_plg_arr as number) ?? ((tqR.bottoms_up as Record<string, unknown> | undefined)?.plg_arr as number) ?? 0;
    const trajExpansion = (tqR.bu_expansion_arr as number) ?? ((tqR.bottoms_up as Record<string, unknown> | undefined)?.expansion_arr as number) ?? 0;

    const planBookings = comparablePlanActive && comparableQuarterly ? getPlanQuarterTarget(plan, tq.quarter) ?? 0 : 0;
    const planPlg = 0;
    const planExpansion = 0;

    return {
      quarter: tq.quarter,
      plan: { salesLed: planBookings, plg: planPlg, expansion: planExpansion },
      trajectory: { salesLed: trajSalesLed, plg: trajPlg, expansion: trajExpansion },
      hasBreakdown: false,
    };
  });
  const hasArrMixBreakdown = false;

  // --- Conversion rate alerts ---
  const alerts: { message: string; color: "red" | "emerald" }[] = [];
  for (const row of quarterRows) {
    if (row.mql_plan !== null && row.mql_actual !== null && row.mql_actual > 0) {
      const ratio = row.mql_actual / row.mql_plan;
      if (ratio < 0.7) {
        alerts.push({
          message: `${row.quarter}: MQLs/week at ${row.mql_actual} vs plan ${row.mql_plan} (${(ratio * 100).toFixed(0)}% of plan)`,
          color: "red",
        });
      } else if (ratio > 1.2) {
        alerts.push({
          message: `${row.quarter}: MQLs/week at ${row.mql_actual} vs plan ${row.mql_plan} (${(ratio * 100).toFixed(0)}% of plan)`,
          color: "emerald",
        });
      }
    }
    if (row.s2_plan !== null && row.s2_actual !== null && row.s2_actual > 0) {
      const ratio = row.s2_actual / row.s2_plan;
      if (ratio < 0.7) {
        alerts.push({
          message: `${row.quarter}: S2/week at ${row.s2_actual} vs plan ${row.s2_plan} (${(ratio * 100).toFixed(0)}% of plan)`,
          color: "red",
        });
      }
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      <SectionHeader
        title="Funnel Health"
        subtitle="Observed conversion rates, quarterly funnel pacing, source-stream breakdown, and expansion workstream."
      />

      {/* Quarter Selector */}
      <div className="flex items-center gap-3">
        <Text className="text-xs font-medium text-slate-600 uppercase tracking-wide">
          Quarter
        </Text>
        <Select
          id="funnel-quarter"
          name="funnel-quarter"
          value={selectedQtr}
          onValueChange={setSelectedQtr}
          className="max-w-[160px]"
        >
          {quarters.map((q) => (
            <SelectItem key={q} value={q}>
              {q}
            </SelectItem>
          ))}
        </Select>
      </div>

      {/* Top-Level Metric Strip */}
      <MetricStrip metrics={topMetrics} />

      {!comparablePlanActive && plan ? (
        <Callout title="Selected Plan Not Comparable" color="red">
          {plan.name} does not ship an operator-comparable default view. Funnel Health suppresses plan-facing top metrics, seat targets, pacing sections, and conversion targets.
        </Callout>
      ) : null}

      {comparablePlanActive && !comparableQuarterly ? (
        <Callout title="Quarterly Plan Support Unavailable" color="red">
          The selected comparable view does not support quarterly grain. Quarter-scoped plan targets, pacing, and conversion references are suppressed here.
        </Callout>
      ) : null}

      {/* Conversion Rate Alerts */}
      {alerts.map((alert, i) => (
        <Callout
          key={i}
          title={alert.color === "red" ? "Below Plan" : "Above Plan"}
          color={alert.color}
        >
          {alert.message}
        </Callout>
      ))}

      {/* ================================================================= */}
      {/* Section 1: Weekly Funnel Pace Table                                */}
      {/* ================================================================= */}
      <Card>
        <SectionHeader
          title="Weekly Funnel Pace"
          subtitle={`${selectedQtr}: Top-down plan vs actual/forecast for each funnel stage.`}
        />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Stage</TableHeaderCell>
              <TableHeaderCell className="text-right">Top-Down Plan</TableHeaderCell>
              <TableHeaderCell className="text-right">Actual / Forecast</TableHeaderCell>
              <TableHeaderCell className="text-right">Delta</TableHeaderCell>
              <TableHeaderCell className="text-right">Delta %</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {paceRows.map((r) => {
              const delta =
                r.plan !== null && r.actual !== null ? r.actual - r.plan : null;
              const isMoney = r.stage === "Sales-Led ARR";
              const formatVal = (v: number | null) => {
                if (v === null) return "\u2014";
                if (r.isRate) return pct(v);
                if (isMoney) return formatMoney(v);
                return num(v, r.stage === "AEs in Seat" ? 0 : 1);
              };
              return (
                <TableRow key={r.stage}>
                  <TableCell className="font-medium text-sm">{r.stage}</TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatVal(r.plan)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatVal(r.actual)}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono text-sm ${deltaColor(delta)}`}
                  >
                    {delta !== null
                      ? isMoney
                        ? formatMoney(delta)
                        : r.isRate
                          ? `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}pp`
                          : `${delta >= 0 ? "+" : ""}${num(delta, 1)}`
                      : "\u2014"}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono text-sm ${deltaColor(delta)}`}
                  >
                    {deltaPctStr(r.plan, r.actual)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      {/* ================================================================= */}
      {/* Section 2: Conversion Rate Details                                 */}
      {/* ================================================================= */}
      <Card>
        <SectionHeader
          title="Conversion Rate Details"
          subtitle="Observed cohort rates use all-inclusive methodology: Won / (Won + Lost + Open). Rows without observed cohort coverage remain explicit config assumptions."
        />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Transition</TableHeaderCell>
              <TableHeaderCell className="text-right">Rate</TableHeaderCell>
              <TableHeaderCell>Source</TableHeaderCell>
              <TableHeaderCell className="text-right">Sample Size</TableHeaderCell>
              <TableHeaderCell>Methodology</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {funnelRateRows.map((r) => (
              <TableRow key={r.rate_name}>
                <TableCell className="font-mono text-sm">
                  {r.rate_name.replace(/_/g, " ").replace(/to/g, "\u2192")}
                </TableCell>
                <TableCell className="text-right font-medium">
                  {(r.observed_pct * 100).toFixed(1)}%
                </TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      r.source === "blended_cohort"
                        ? "bg-blue-50 text-blue-700"
                        : r.source === "observed"
                          ? "bg-emerald-50 text-emerald-700"
                          : r.source === "warehouse"
                            ? "bg-purple-50 text-purple-700"
                            : r.source === "registry"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-slate-50 text-slate-600"
                    }`}
                  >
                    {humanSourceLabel(r.source)}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  {r.sampleSize > 0 ? `n=${r.sampleSize}` : "\u2014"}
                </TableCell>
                <TableCell className="text-xs text-slate-500">
                  {r.methodology || "\u2014"}
                </TableCell>
              </TableRow>
            ))}
            {/* S2 to Won (rolling) as final row */}
            {rollingRate !== null && (
              <TableRow>
                <TableCell className="font-mono text-sm">
                  s2 {"\u2192"} won
                </TableCell>
                <TableCell className="text-right font-medium">
                  {(rollingRate * 100).toFixed(1)}%
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-purple-50 text-purple-700">
                    {rollingSource}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  n={rollingSample}
                </TableCell>
                <TableCell className="text-xs text-slate-500">
                  {rollingMethod || "\u2014"}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <ProseNote>
        Cohort-based observed rates use all-inclusive methodology (Won / All
        including Open), which captures zombie pipeline. Early-funnel and PLG
        rows may still be registry or static assumptions when no compatible
        observed cohort methodology is available in the snapshot.
      </ProseNote>

      {/* ================================================================= */}
      {/* Section 3: Per-Quarter Conversion Rates by Stream                  */}
      {/* ================================================================= */}
      {conversionRates && Object.keys(conversionRates).length > 0 && (
        <Card>
          <SectionHeader
            title={`${selectedQtr} Conversion Rates by Stream`}
            subtitle="Per-stream rates used in bottoms-up model for this quarter."
          />
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Transition</TableHeaderCell>
                <TableHeaderCell className="text-right">Marketing/SDR</TableHeaderCell>
                <TableHeaderCell className="text-right">AE Self-Gen</TableHeaderCell>
                <TableHeaderCell className="text-right">PLG</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(conversionRates).map(([transition, streams]) => {
                const mktg = streams?.marketing_sdr as Record<string, unknown> | undefined;
                const ae = streams?.ae_selfgen as Record<string, unknown> | undefined;
                const plg = streams?.plg as Record<string, unknown> | undefined;
                return (
                  <TableRow key={transition}>
                    <TableCell className="font-mono text-sm">
                      {transition.replace(/_/g, " ").replace(/to/g, "\u2192")}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="font-medium">{pct(mktg?.rate as number | null)}</span>
                      {(mktg?.n as number) ? (
                        <span className="text-xs text-slate-400 ml-1">
                          n={mktg?.n as number}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="font-medium">{pct(ae?.rate as number | null)}</span>
                      {(ae?.n as number) ? (
                        <span className="text-xs text-slate-400 ml-1">
                          n={ae?.n as number}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="font-medium">{pct(plg?.rate as number | null)}</span>
                      {(plg?.n as number) ? (
                        <span className="text-xs text-slate-400 ml-1">
                          n={plg?.n as number}
                        </span>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* ================================================================= */}
      {/* Section 4: Source Stream Breakdown                                  */}
      {/* ================================================================= */}
      {streamEntries.length > 0 && (
        <Card>
          <SectionHeader
            title={`${selectedQtr} Source Stream Breakdown`}
            subtitle={`Pipeline creation by source. Mode: ${(sourceBreakdown?.mode as string) ?? "unknown"}.`}
          />
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Stream</TableHeaderCell>
                <TableHeaderCell className="text-right">Input / wk</TableHeaderCell>
                <TableHeaderCell className="text-right">S0 / wk</TableHeaderCell>
                <TableHeaderCell className="text-right">S1 / wk</TableHeaderCell>
                <TableHeaderCell className="text-right">S2 / wk</TableHeaderCell>
                <TableHeaderCell className="text-right">Qtr Pipeline</TableHeaderCell>
                <TableHeaderCell className="text-right">Actual Opps</TableHeaderCell>
                <TableHeaderCell className="text-right">Actual Pipeline</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {streamEntries.map((stream) => {
                const s = stream as Record<string, unknown>;
                return (
                  <TableRow key={s.stream_key as string}>
                    <TableCell className="font-medium text-sm">
                      {(s.display_name as string) ?? (s.stream_key as string)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {num(s.weekly_input as number, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {num(s.weekly_s0_count as number, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {num(s.weekly_s1_count as number, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {num(s.weekly_s2_count as number, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatMoney((s.quarter_pipeline_created as number) ?? 0)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {num(s.actual_opp_count as number)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatMoney((s.actual_pipeline as number) ?? 0)}
                    </TableCell>
                  </TableRow>
                );
              })}
              {/* Totals row */}
              <TableRow className="border-t-2 border-slate-300">
                <TableCell className="font-semibold text-sm">Total</TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {num(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).weekly_input as number ?? 0),
                      0
                    ),
                    1
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {num(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).weekly_s0_count as number ?? 0),
                      0
                    ),
                    1
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {num(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).weekly_s1_count as number ?? 0),
                      0
                    ),
                    1
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {num(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).weekly_s2_count as number ?? 0),
                      0
                    ),
                    1
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {formatMoney(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).quarter_pipeline_created as number ?? 0),
                      0
                    )
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {num(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).actual_opp_count as number ?? 0),
                      0
                    )
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {formatMoney(
                    streamEntries.reduce(
                      (acc, s) => acc + ((s as Record<string, unknown>).actual_pipeline as number ?? 0),
                      0
                    )
                  )}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      )}

      {/* ================================================================= */}
      {/* Section 5: Expansion Workstream                                     */}
      {/* ================================================================= */}
      {hasExpansion && (
        <Card>
          <SectionHeader
            title={`${selectedQtr} Expansion Workstream`}
            subtitle="Expansion ARR breakdown by source: renewal upsell, usage-based, PLG, and consumption."
          />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="rounded-lg bg-slate-50 p-3">
              <Text className="text-xs text-slate-500">Opening ARR</Text>
              <Metric className="text-lg">
                {formatMoney((expansionBreakdown as Record<string, unknown>).opening_arr as number)}
              </Metric>
            </div>
            <div className="rounded-lg bg-emerald-50 p-3">
              <Text className="text-xs text-slate-500">Total Expansion</Text>
              <Metric className="text-lg text-emerald-700">
                {formatMoney((expansionBreakdown as Record<string, unknown>).total_expansion_arr as number)}
              </Metric>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <Text className="text-xs text-slate-500">Program Maturity</Text>
              <Metric className="text-lg">
                {pct((expansionBreakdown as Record<string, unknown>).program_maturity_factor as number)}
              </Metric>
              <Text className="text-[10px] text-slate-400 mt-1 leading-tight">
                Fraction of expansion program that's operational and producing results.
              </Text>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <Text className="text-xs text-slate-500">Renewable Sales-Led</Text>
              <Metric className="text-lg">
                {formatMoney((expansionBreakdown as Record<string, unknown>).renewable_sales_led_arr as number)}
              </Metric>
            </div>
          </div>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Expansion Source</TableHeaderCell>
                <TableHeaderCell className="text-right">ARR</TableHeaderCell>
                <TableHeaderCell className="text-right">% of Total</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {[
                { label: "Renewal Expansion", key: "renewal_expansion_arr" },
                { label: "Usage-Based Expansion", key: "usage_expansion_arr" },
                { label: "PLG Expansion", key: "plg_expansion_arr" },
                { label: "Consumption True-Forward", key: "consumption_true_forward_arr" },
              ].map((row) => {
                const val = (expansionBreakdown as Record<string, unknown>)[row.key] as number ?? 0;
                const total = (expansionBreakdown as Record<string, unknown>).total_expansion_arr as number ?? 1;
                return (
                  <TableRow key={row.key}>
                    <TableCell className="font-medium text-sm">{row.label}</TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatMoney(val)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {total > 0 ? `${((val / total) * 100).toFixed(1)}%` : "\u2014"}
                    </TableCell>
                  </TableRow>
                );
              })}
              <TableRow className="border-t-2 border-slate-300">
                <TableCell className="font-semibold text-sm">Total</TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {formatMoney((expansionBreakdown as Record<string, unknown>).total_expansion_arr as number ?? 0)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  100%
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      )}

      {/* ================================================================= */}
      {/* Section 6: Quarterly Funnel Summary (all quarters)                  */}
      {/* ================================================================= */}
      <Card>
        <SectionHeader
          title="Quarterly Funnel Summary"
          subtitle="Weekly activity rates vs plan across all quarters, with projected bookings."
        />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Quarter</TableHeaderCell>
              <TableHeaderCell className="text-right">
                MQLs/wk (Plan)
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                MQLs/wk (Actual)
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                S0/wk (Actual)
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                S2/wk (Plan)
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                S2/wk (Actual)
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                Bookings
              </TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {quarterRows.map((r) => (
              <TableRow
                key={r.quarter}
                className={r.quarter === selectedQtr ? "bg-blue-50/50" : ""}
              >
                <TableCell className={r.quarter === selectedQtr ? "font-semibold" : ""}>
                  {r.quarter}
                </TableCell>
                <TableCell className="text-right">
                  {r.mql_plan !== null ? r.mql_plan.toFixed(0) : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {r.mql_actual !== null && r.mql_actual > 0 ? r.mql_actual.toFixed(0) : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {r.s0_actual !== null && r.s0_actual > 0 ? r.s0_actual.toFixed(0) : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {r.s2_plan !== null ? r.s2_plan.toFixed(0) : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {r.s2_actual !== null && r.s2_actual > 0 ? r.s2_actual.toFixed(0) : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {formatMoney(r.bookings)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* ================================================================= */}
      {/* Section 7: Funnel Waterfall Charts                                  */}
      {/* ================================================================= */}
      <SectionHeader
        title="Funnel Waterfall: Plan vs Trajectory"
        subtitle="Grouped bar comparison of weekly funnel activity rates."
      />
      {waterfallByQuarter.filter((q) => q.hasData).length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {waterfallByQuarter
            .filter((q) => q.hasData)
            .map((q) => (
              <Card key={q.quarter} className="p-5">
                <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-3">
                  {q.quarter}
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={q.data}>
                    <CartesianGrid
                      horizontal={GRID_STYLE.horizontal}
                      vertical={GRID_STYLE.vertical}
                      stroke={GRID_STYLE.stroke}
                      strokeDasharray={GRID_STYLE.strokeDasharray}
                    />
                    <XAxis
                      dataKey="stage"
                      tick={AXIS_STYLE.tick}
                      axisLine={AXIS_STYLE.axisLine}
                      tickLine={false}
                    />
                    <YAxis
                      tick={AXIS_STYLE.tick}
                      axisLine={false}
                      tickLine={false}
                      width={40}
                    />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE.contentStyle}
                      labelStyle={TOOLTIP_STYLE.labelStyle}
                    />
                    <Legend
                      iconSize={LEGEND_STYLE.iconSize}
                      wrapperStyle={LEGEND_STYLE.wrapperStyle}
                    />
                    <Bar
                      dataKey="plan"
                      fill="#94a3b8"
                      name="Top-Down Plan"
                      radius={[2, 2, 0, 0]}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="trajectory"
                      fill="#2563eb"
                      name="Trajectory"
                      radius={[2, 2, 0, 0]}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            ))}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-500">
            Funnel waterfall data not available. Ensure snapshot includes weekly
            funnel metrics (mqls_weekly, s0_weekly, s1_weekly, s2_weekly) in
            quarter data.
          </p>
        </div>
      )}

      {/* ================================================================= */}
      {/* Section 8: ARR Mix: Plan vs Trajectory                              */}
      {/* ================================================================= */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">
          ARR Mix: Plan vs Trajectory
        </h3>
        {hasArrMixBreakdown ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-3">
            {arrMixByQuarter.map((q) => (
              <div key={q.quarter}>
                <p className="text-xs font-medium text-slate-700 mb-2">{q.quarter}</p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Top-Down Plan</p>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-600">Sales-Led</span>
                        <span className="font-medium">{formatMoney(q.plan.salesLed)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-600">PLG</span>
                        <span className="font-medium">{formatMoney(q.plan.plg)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-600">Expansion</span>
                        <span className="font-medium">{formatMoney(q.plan.expansion)}</span>
                      </div>
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Trajectory Forecast</p>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-600">Sales-Led</span>
                        <span className="font-medium">{formatMoney(q.trajectory.salesLed)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-600">PLG</span>
                        <span className="font-medium">{formatMoney(q.trajectory.plg)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-600">Expansion</span>
                        <span className="font-medium">{formatMoney(q.trajectory.expansion)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500 mt-2">
            The selected comparable view does not own a multi-component scenario-modeled ARR mix in v2, so ARR mix plan breakdown is suppressed on operator pages.
          </p>
        )}
      </Card>

      {/* Data Provenance */}
      {snapshotMeta && (
        <p className="text-xs text-slate-400 mt-8 pt-4 border-t border-slate-100">
          Data as of {snapshotMeta.as_of} · Snapshot generated{" "}
          {new Date(snapshotMeta.generated_at).toLocaleString()} · Git{" "}
          {snapshotMeta.git_sha?.slice(0, 7) ?? "--"}
        </p>
      )}
    </div>
  );
}
