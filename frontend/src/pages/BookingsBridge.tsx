import {
  Card,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from "../components/ui";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { BookingsBridgeData, CapacityRow } from "../types/snapshot";
import { SectionHeader, MetricStrip, ProseNote } from "../components/workbook";
import type { MetricItem } from "../components/workbook";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { formatMoney, formatMonthLabel } from "../lib/format";
import {
  buildPlanMonthlyReference,
  getPlanFyTarget,
  getPlanQuarterTarget,
} from "../lib/plans";
import {
  CHART_COLORS,
  AXIS_STYLE,
  GRID_STYLE,
  TOOLTIP_STYLE,
  LEGEND_STYLE,
  currencyFormatter,
  currencyTooltipFormatter,
} from "../lib/chartTheme";

const MONTHLY_SERIES = {
  existing: "Wins from Existing Pipeline",
  future: "Wins from Future Pipeline",
  total: "Total Expected Wins",
  plan: "Plan Target",
  capacity: "AE Capacity",
} as const;

const CUMULATIVE_SERIES = {
  existing: "Cumulative Existing Wins",
  future: "Cumulative Future Wins",
  total: "Cumulative Total Expected",
  plan: "Cumulative Plan Target",
  capacity: "Cumulative AE Capacity",
} as const;

export default function BookingsBridge() {
  const { snapshot, selectedOrgProfile, selectedPlan: plan, snapshotMeta } = usePlanningSessionContext();
  const data: BookingsBridgeData = snapshot.model_output.bookings_bridge;
  const beginningArr = snapshot.beginning_arr;
  const capacityRows: CapacityRow[] | undefined = snapshot.roster.effective_capacity;
  const winRate = snapshot.rates.overall_win_rate;
  const monthLabels = data.months.map(formatMonthLabel);
  const planMonthlyReference = buildPlanMonthlyReference(data.months, plan);
  const monthlyPlanTarget = planMonthlyReference.values;
  const showMonthlyPlanTarget =
    (plan?.availability.comparableOnOperatorPages ?? false) &&
    (planMonthlyReference.basis === "explicit_monthly_plan" ||
      planMonthlyReference.basis === "derived_even_quarter_split" ||
      planMonthlyReference.basis === "mixed");
  const comparableAnnual =
    (plan?.availability.comparableOnOperatorPages ?? false) &&
    (plan?.availability.annualComparable ?? false);
  const comparableQuarterly =
    (plan?.availability.comparableOnOperatorPages ?? false) &&
    (plan?.availability.quarterlyComparable ?? false);

  // --- Top-level KPIs ---
  const fyTarget = comparableAnnual ? getPlanFyTarget(plan) : null;

  const fyTrajectory = data.trajectory_quarters.reduce((sum, tq) => {
    const bu =
      (tq as Record<string, unknown>).bu_sales_led_arr ??
      ((tq as Record<string, unknown>).bottoms_up as Record<string, unknown> | undefined)
        ?.sales_led_arr ??
      0;
    return sum + (bu as number);
  }, 0);

  const fyGap = typeof fyTarget === "number" ? fyTrajectory - fyTarget : null;
  const fyExistingTotal = data.existing_wins.reduce((a, b) => a + b, 0);
  const fyTotalExpected = data.total_expected.reduce((a, b) => a + b, 0);
  const fromExistingPct =
    fyTotalExpected > 0 ? fyExistingTotal / fyTotalExpected : 0;
  const fromFuturePct = 1 - fromExistingPct;

  const topMetrics: MetricItem[] = [
    {
      label: comparableAnnual ? "Sales-Led Target" : "Comparison Scope",
      value:
        comparableAnnual && typeof fyTarget === "number"
          ? formatMoney(fyTarget)
          : plan?.comparisonScopeLabel ?? "\u2014",
      delta:
        comparableAnnual
          ? undefined
          : "Target math suppressed",
      deltaType: "unchanged",
    },
    {
      label: "Trajectory Forecast",
      value: formatMoney(fyTrajectory),
      delta:
        typeof fyGap === "number"
          ? `${fyGap >= 0 ? "+" : ""}${formatMoney(fyGap)} vs target`
          : "No comparable FY target",
      deltaType: typeof fyGap === "number" ? (fyGap >= 0 ? "increase" : "decrease") : "unchanged",
    },
    {
      label: "FY Gap",
      value: typeof fyGap === "number" ? formatMoney(Math.abs(fyGap)) : "\u2014",
      deltaType: typeof fyGap === "number" ? (fyGap >= 0 ? "increase" : "decrease") : "unchanged",
      delta: typeof fyGap === "number" ? (fyGap >= 0 ? "Surplus" : "Shortfall") : "Suppressed",
    },
    {
      label: "From Existing Pipeline",
      value: `${(fromExistingPct * 100).toFixed(0)}%`,
    },
    {
      label: "From Future Pipeline",
      value: `${(fromFuturePct * 100).toFixed(0)}%`,
    },
  ];
  // --- Build AE Capacity lookup from roster rows ---
  const capacityByMonth: Record<string, number> = {};
  if (capacityRows) {
    for (const row of capacityRows) {
      capacityByMonth[row.month.slice(0, 7)] = row.ae_capacity;
    }
  }

  // --- Monthly Bookings Sources chart data ---
  const monthlyChartData = monthLabels.map((label, i) => ({
    month: label,
    [MONTHLY_SERIES.existing]: data.existing_wins[i] ?? 0,
    [MONTHLY_SERIES.future]: data.future_wins[i] ?? 0,
    [MONTHLY_SERIES.total]: data.total_expected[i] ?? 0,
    [MONTHLY_SERIES.plan]: showMonthlyPlanTarget ? monthlyPlanTarget[i] : null,
    [MONTHLY_SERIES.capacity]: capacityByMonth[data.months[i]?.slice(0, 7)] ?? null,
  }));

  // --- Cumulative arrays ---
  const cumulativeData: {
    month: string;
    [CUMULATIVE_SERIES.existing]: number;
    [CUMULATIVE_SERIES.future]: number;
    [CUMULATIVE_SERIES.total]: number;
    [CUMULATIVE_SERIES.plan]: number | null;
    [CUMULATIVE_SERIES.capacity]: number | null;
  }[] = [];
  let cumEx = 0;
  let cumFut = 0;
  let cumTotal = 0;
  let cumPlan = 0;
  let cumCapacity = 0;
  let hasAnyCap = false;
  for (let i = 0; i < data.months.length; i++) {
    cumEx += data.existing_wins[i] ?? 0;
    cumFut += data.future_wins[i] ?? 0;
    cumTotal += data.total_expected[i] ?? 0;
    cumPlan += showMonthlyPlanTarget ? monthlyPlanTarget[i] : 0;
    const monthlyCap = capacityByMonth[data.months[i]?.slice(0, 7)] ?? 0;
    if (monthlyCap > 0) hasAnyCap = true;
    cumCapacity += monthlyCap;
    cumulativeData.push({
      month: monthLabels[i],
      [CUMULATIVE_SERIES.existing]: cumEx,
      [CUMULATIVE_SERIES.future]: cumFut,
      [CUMULATIVE_SERIES.total]: cumTotal,
      [CUMULATIVE_SERIES.plan]: showMonthlyPlanTarget ? cumPlan : null,
      [CUMULATIVE_SERIES.capacity]: hasAnyCap ? cumCapacity : null,
    });
  }

  // --- Quarterly breakdown ---
  const quarterRows = data.trajectory_quarters.map((tq) => {
    const target = comparableQuarterly ? getPlanQuarterTarget(plan, tq.quarter) : null;
    const trajectory = getNestedNumber(tq, "bu_sales_led_arr", [
      "bottoms_up",
      "sales_led_arr",
    ]);
    const actuals = getNestedNumber(tq, "actual_bookings", [
      "actuals",
      "bookings",
    ]);
    const gap = typeof target === "number" ? trajectory - target : null;
    const gapPct =
      typeof target === "number" && typeof gap === "number" && target > 0 ? gap / target : null;

    // Existing vs future from monthly data for this quarter — uses the
    // engine-emitted quarter_by_month parallel array so the page is
    // calendar-agnostic.
    const quarterByMonth = snapshot.scenario_building_blocks.quarter_by_month ?? [];
    const qMonths = data.months
      .map((m, i) => ({ m, i }))
      .filter(({ i }) => quarterByMonth[i] === tq.quarter);
    const qExisting = qMonths.reduce(
      (s, { i }) => s + (data.existing_wins[i] ?? 0),
      0
    );
    const qFuture = qMonths.reduce(
      (s, { i }) => s + (data.future_wins[i] ?? 0),
      0
    );

    return {
      quarter: tq.quarter,
      target,
      trajectory,
      gap,
      gapPct,
      existing: qExisting,
      future: qFuture,
      actuals,
      basis: actuals > 0 ? "Actual + Projected" : "Projected",
    };
  });

  // FY summary row — labels derived from profile metadata so the page works
  // for any fiscal calendar.
  const fiscalYearLabel =
    typeof selectedOrgProfile?.metadata.fiscal_year === "string" && selectedOrgProfile.metadata.fiscal_year
      ? selectedOrgProfile.metadata.fiscal_year
      : "FY";
  const fySummary = {
    quarter: `${fiscalYearLabel} Total`,
    target: quarterRows.reduce((s, r) => s + (typeof r.target === "number" ? r.target : 0), 0),
    trajectory: quarterRows.reduce((s, r) => s + r.trajectory, 0),
    gap: quarterRows.reduce((s, r) => s + (typeof r.gap === "number" ? r.gap : 0), 0),
    gapPct: null as number | null,
    existing: quarterRows.reduce((s, r) => s + r.existing, 0),
    future: quarterRows.reduce((s, r) => s + r.future, 0),
    actuals: quarterRows.reduce((s, r) => s + r.actuals, 0),
    basis: "",
  };
  fySummary.gapPct =
    fySummary.target > 0 ? fySummary.gap / fySummary.target : null;

  // --- ARR KPIs ---
  const ytdClosedWon = data.trajectory_quarters.reduce((sum, tq) => {
    return sum + getNestedNumber(tq, "actual_bookings", ["actuals", "bookings"]);
  }, 0);

  const arrMetrics: MetricItem[] = [
    {
      label: "Beginning ARR",
      value: beginningArr ? formatMoney(beginningArr) : "--",
    },
      {
        label: "Top-Down Ending ARR",
        value:
          typeof fyTarget === "number"
            ? formatMoney((beginningArr ?? 0) + fyTarget)
            : "--",
      },
    {
      label: "YTD Closed-Won",
      value: formatMoney(ytdClosedWon),
    },
    {
      label: "YTD Recurring (~85%)",
      value: ytdClosedWon > 0 ? formatMoney(ytdClosedWon * 0.85) : "--",
    },
  ];

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      <SectionHeader
        title={`${fiscalYearLabel} Bookings Bridge`}
        subtitle="Sales-led trajectory versus the selected comparable plan target, sourced from the live snapshot pipeline and capacity model."
        caption={`Pipeline as of snapshot date. ${data.months.length} months modeled.`}
      />

      {/* Capacity Warnings */}
      {data.capacity_warnings && data.capacity_warnings.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="font-semibold text-amber-800 mb-2">Capacity Warnings</p>
          <ul className="list-disc list-inside space-y-0.5 text-sm text-amber-700">
            {data.capacity_warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <MetricStrip metrics={topMetrics} />

      {!plan?.availability.comparableOnOperatorPages && plan ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          {plan.name} does not ship an operator-comparable default view. Bookings Bridge suppresses selected-plan targets instead of inventing a comparable rail.
        </div>
      ) : null}

      {plan?.availability.comparableOnOperatorPages && !comparableQuarterly ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          The selected comparable view does not support quarterly grain. Quarterly target tables are suppressed on this page.
        </div>
      ) : null}

      {plan?.availability.comparableOnOperatorPages && !showMonthlyPlanTarget ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          {planMonthlyReference.note}
        </div>
      ) : null}

      <ProseNote>
        {typeof fyTarget === "number"
          ? `Sales-led target: ${formatMoney(fyTarget)}. Trajectory forecast: ${formatMoney(
              fyTrajectory,
            )} based on current pipeline inventory and capacity-driven future pipeline creation. The gap of ${formatMoney(
              Math.abs(fyGap ?? 0),
            )} must be closed through improved conversion, additional pipeline generation, or headcount acceleration.`
          : "The selected plan does not provide a comparable FY target for this page. The bridge stays focused on the live sales-led trajectory and suppresses selected-plan gap math."}
      </ProseNote>

      {/* Monthly Bookings Sources */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">Monthly Bookings Sources</h3>
        <p className="text-xs text-slate-500 mb-4">
          Monthly wins from existing pipeline and future pipeline, with total expected wins,
          plan target, and AE capacity overlaid for direct comparison.
        </p>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={monthlyChartData}>
            <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
            <XAxis dataKey="month" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
            <YAxis tickFormatter={currencyFormatter} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={60} />
            <Tooltip formatter={currencyTooltipFormatter} contentStyle={TOOLTIP_STYLE.contentStyle} labelStyle={TOOLTIP_STYLE.labelStyle} />
            <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
            <Area type="monotone" dataKey={MONTHLY_SERIES.existing} stackId="1" fill={CHART_COLORS.blue} stroke={CHART_COLORS.blue} strokeWidth={2} fillOpacity={0.7} isAnimationActive={false} />
            <Area type="monotone" dataKey={MONTHLY_SERIES.future} stackId="1" fill={CHART_COLORS.emerald} stroke={CHART_COLORS.emerald} strokeWidth={2} fillOpacity={0.7} isAnimationActive={false} />
            <Line type="monotone" dataKey={MONTHLY_SERIES.total} stroke="#475569" strokeWidth={2.5} dot={false} isAnimationActive={false} />
            {showMonthlyPlanTarget ? (
              <Line type="monotone" dataKey={MONTHLY_SERIES.plan} stroke={CHART_COLORS.red} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            ) : null}
            {capacityRows && capacityRows.length > 0 && (
              <Line type="monotone" dataKey={MONTHLY_SERIES.capacity} stroke={CHART_COLORS.amber} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      <ProseNote>
        Wins from existing pipeline represent expected closes from the current
        S2+ inventory. Wins from future pipeline represent closes from deals not
        yet created, modeled from AE capacity and observed conversion rates.
        Total expected wins is the finance-relevant monthly sum to compare
        directly against plan target and AE capacity.
      </ProseNote>

      {/* Cumulative Bookings Path */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">Cumulative Bookings Path</h3>
        <p className="text-xs text-slate-500 mb-4">
          Running totals of existing wins, future wins, and cumulative total expected against
          cumulative plan target and cumulative AE capacity.
        </p>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={cumulativeData}>
            <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
            <XAxis dataKey="month" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
            <YAxis tickFormatter={currencyFormatter} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={60} />
            <Tooltip formatter={currencyTooltipFormatter} contentStyle={TOOLTIP_STYLE.contentStyle} labelStyle={TOOLTIP_STYLE.labelStyle} />
            <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
            <Area type="monotone" dataKey={CUMULATIVE_SERIES.existing} stackId="1" fill={CHART_COLORS.blue} stroke={CHART_COLORS.blue} strokeWidth={2} fillOpacity={0.7} isAnimationActive={false} />
            <Area type="monotone" dataKey={CUMULATIVE_SERIES.future} stackId="1" fill={CHART_COLORS.emerald} stroke={CHART_COLORS.emerald} strokeWidth={2} fillOpacity={0.7} isAnimationActive={false} />
            <Line type="monotone" dataKey={CUMULATIVE_SERIES.total} stroke="#475569" strokeWidth={2.5} dot={false} isAnimationActive={false} />
            {showMonthlyPlanTarget ? (
              <Line type="monotone" dataKey={CUMULATIVE_SERIES.plan} stroke={CHART_COLORS.red} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            ) : null}
            {hasAnyCap && (
              <Line type="monotone" dataKey={CUMULATIVE_SERIES.capacity} stroke={CHART_COLORS.amber} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      {/* Quarterly Breakdown Table */}
      <Card>
        <SectionHeader title="Quarterly Breakdown" />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Quarter</TableHeaderCell>
              <TableHeaderCell className="text-right">
                Sales-Led Target
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                Trajectory
              </TableHeaderCell>
              <TableHeaderCell className="text-right">Gap</TableHeaderCell>
              <TableHeaderCell className="text-right">Gap %</TableHeaderCell>
              <TableHeaderCell className="text-right">
                From Existing
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                From Future
              </TableHeaderCell>
              <TableHeaderCell className="text-right">Actuals</TableHeaderCell>
              <TableHeaderCell>Data Basis</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {quarterRows.map((r) => (
              <TableRow key={r.quarter}>
                <TableCell>{r.quarter}</TableCell>
                <TableCell className="text-right">
                  {typeof r.target === "number" ? formatMoney(r.target) : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {formatMoney(r.trajectory)}
                </TableCell>
                <TableCell
                  className={`text-right font-medium ${
                    r.gap === null
                      ? "text-slate-500"
                      : r.gap >= 0
                        ? "text-emerald-600"
                        : "text-red-600"
                  }`}
                >
                  {typeof r.gap === "number" ? `${r.gap >= 0 ? "+" : ""}${formatMoney(r.gap)}` : "\u2014"}
                </TableCell>
                <TableCell
                  className={`text-right ${
                    r.gapPct === null
                      ? "text-slate-500"
                      : r.gapPct >= 0
                        ? "text-emerald-600"
                        : "text-red-600"
                  }`}
                >
                  {typeof r.gapPct === "number" ? `${r.gapPct >= 0 ? "+" : ""}${(r.gapPct * 100).toFixed(0)}%` : "\u2014"}
                </TableCell>
                <TableCell className="text-right">
                  {formatMoney(r.existing)}
                </TableCell>
                <TableCell className="text-right">
                  {formatMoney(r.future)}
                </TableCell>
                <TableCell className="text-right">
                  {r.actuals > 0 ? formatMoney(r.actuals) : "\u2014"}
                </TableCell>
                <TableCell>{r.basis}</TableCell>
              </TableRow>
            ))}
            {/* Fiscal-year summary row */}
            <TableRow className="bg-slate-50 font-semibold">
              <TableCell>{fySummary.quarter}</TableCell>
              <TableCell className="text-right">
                {comparableQuarterly ? formatMoney(fySummary.target) : "\u2014"}
              </TableCell>
              <TableCell className="text-right">
                {formatMoney(fySummary.trajectory)}
              </TableCell>
              <TableCell
                className={`text-right font-bold ${
                  comparableQuarterly
                    ? fySummary.gap >= 0
                      ? "text-emerald-600"
                      : "text-red-600"
                    : "text-slate-500"
                }`}
              >
                {comparableQuarterly ? `${fySummary.gap >= 0 ? "+" : ""}${formatMoney(fySummary.gap)}` : "\u2014"}
              </TableCell>
              <TableCell
                className={`text-right ${
                  typeof fySummary.gapPct === "number"
                    ? fySummary.gapPct >= 0
                      ? "text-emerald-600"
                      : "text-red-600"
                    : "text-slate-500"
                }`}
              >
                {typeof fySummary.gapPct === "number" ? `${fySummary.gapPct >= 0 ? "+" : ""}${(fySummary.gapPct * 100).toFixed(0)}%` : "\u2014"}
              </TableCell>
              <TableCell className="text-right">
                {formatMoney(fySummary.existing)}
              </TableCell>
              <TableCell className="text-right">
                {formatMoney(fySummary.future)}
              </TableCell>
              <TableCell className="text-right">
                {fySummary.actuals > 0 ? formatMoney(fySummary.actuals) : "\u2014"}
              </TableCell>
              <TableCell />
            </TableRow>
          </TableBody>
        </Table>
      </Card>

      {/* ARR Overview */}
      <SectionHeader
        title="ARR Overview"
        subtitle="Annual recurring revenue context for the bookings bridge."
      />
      <MetricStrip metrics={arrMetrics} />

      {/* What Needs to Change */}
      {typeof fyGap === "number" && fyGap < 0 && typeof fyTarget === "number" && (
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">What Needs to Change</h3>
          <p className="text-xs text-slate-500 mb-3">Top levers that could close the gap between trajectory and target.</p>
          <div className="text-sm text-slate-600">
            <p>The trajectory forecast of {formatMoney(fyTrajectory)} falls {formatMoney(Math.abs(fyGap))} short of the {formatMoney(fyTarget)} sales-led target. Key levers to close this gap include:</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li><strong>Headcount acceleration</strong> — hire ahead of plan to increase pipeline creation capacity</li>
              <li><strong>Conversion rate improvement</strong> — improve S2 to Won from {winRate ? `${(winRate * 100).toFixed(0)}%` : "--"} through deal qualification and sales enablement</li>
              <li><strong>Pipeline generation</strong> — increase marketing MQL volume and AE self-gen activity</li>
              <li><strong>Deal size uplift</strong> — focus on larger enterprise opportunities to increase average contract value</li>
            </ul>
            <p className="mt-2 text-xs text-slate-400">Use the Scenario Planner tab to model specific lever adjustments and see their impact on the forecast.</p>
          </div>
        </Card>
      )}

      {/* Data Provenance */}
      {snapshotMeta && (
        <p className="text-xs text-slate-400 mt-8 pt-4 border-t border-slate-100">
          Data as of {snapshotMeta.as_of} · Snapshot generated {new Date(snapshotMeta.generated_at).toLocaleString()} · Git {snapshotMeta.git_sha?.slice(0, 7) ?? "--"}
        </p>
      )}
    </div>
  );
}

// --- Helpers ---

function getNestedNumber(
  obj: Record<string, unknown> | null | undefined,
  directKey: string,
  nestedPath: string[]
): number {
  if (!obj) return 0;
  // Try direct key first
  if (typeof obj[directKey] === "number") return obj[directKey] as number;
  // Try nested path
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

