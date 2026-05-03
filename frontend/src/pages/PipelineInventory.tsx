import {
  Card,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Badge,
} from "../components/ui";
import {
  ComposedChart,
  BarChart,
  Bar,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { PipelineInventoryData, CapacityRow, Actuals } from "../types/snapshot";
import { SectionHeader, MetricStrip, ProseNote } from "../components/workbook";
import type { MetricItem } from "../components/workbook";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { formatIsoDate, formatMoney, formatMonthLabel } from "../lib/format";
import { buildPlanMonthlyReference } from "../lib/plans";
import {
  CHART_COLORS,
  AXIS_STYLE,
  GRID_STYLE,
  TOOLTIP_STYLE,
  LEGEND_STYLE,
  currencyFormatter,
  currencyTooltipFormatter,
} from "../lib/chartTheme";

export default function PipelineInventory() {
  const { snapshot, selectedPlan: plan, snapshotMeta } = usePlanningSessionContext();
  const data: PipelineInventoryData = snapshot.model_output.pipeline_inventory;
  const capacityRows: CapacityRow[] | undefined = snapshot.roster.effective_capacity;
  const actuals: Actuals | undefined = snapshot.actuals;
  const actualMonthFlags: boolean[] | undefined =
    snapshot.scenario_building_blocks.monthly_is_actual;
  const monthLabels = data.months.map(formatMonthLabel);

  const totalExistingWins = data.existing_wins.reduce((a, b) => a + b, 0);
  const totalFutureWins = data.future_wins.reduce((a, b) => a + b, 0);
  const openInventory = data.existing_remaining[0] ?? 0;
  const totalProjected = totalExistingWins + totalFutureWins;

  const kpiMetrics: MetricItem[] = [
    { label: "Open Inventory", value: formatMoney(openInventory) },
    { label: "Expected from Existing", value: formatMoney(totalExistingWins) },
    { label: "Expected from Future", value: formatMoney(totalFutureWins) },
    {
      label: "Total Projected",
      value: formatMoney(totalProjected),
    },
  ];

  // --- Build actual won/lost/S2-entry lookups from snapshot actuals ---
  const actualWonByMonth: Record<string, number> = {};
  const actualLostByMonth: Record<string, number> = {};
  const actualS2EnteredByMonth: Record<string, number> = {};
  for (const entry of actuals?.bookings_by_month ?? []) {
    actualWonByMonth[entry.month.slice(0, 7)] = entry.total;
  }
  for (const entry of actuals?.losses_by_month ?? []) {
    actualLostByMonth[entry.month.slice(0, 7)] = entry.total;
  }
  for (const entry of actuals?.pipeline_entered_s2_by_month ?? actuals?.pipeline_created_by_month ?? []) {
    actualS2EnteredByMonth[entry.month.slice(0, 7)] = entry.total;
  }

  const actualFlags = data.months.map((month, i) => {
    const provided = actualMonthFlags?.[i];
    if (typeof provided === "boolean") {
      return provided;
    }
    if (snapshotMeta?.as_of) {
      return (
        new Date(`${month.slice(0, 10)}T00:00:00`).getTime() <
        new Date(`${snapshotMeta.as_of}T00:00:00`).getTime()
      );
    }
    return month.slice(0, 7) < new Date().toISOString().slice(0, 7);
  });
  const firstProjectedIndex = actualFlags.findIndex((isActual) => !isActual);
  const projectionStartLabel =
    firstProjectedIndex > 0 ? monthLabels[firstProjectedIndex] : undefined;
  const actualsThroughLabel = snapshotMeta?.as_of
    ? formatIsoDate(snapshotMeta.as_of)
    : "the snapshot date";

  const planMonthlyReference = buildPlanMonthlyReference(data.months, plan);
  const monthlyPlanTarget = planMonthlyReference.values;
  const showPlanTarget =
    (plan?.availability.comparableOnOperatorPages ?? false) &&
    (planMonthlyReference.basis === "explicit_monthly_plan" ||
      planMonthlyReference.basis === "derived_even_quarter_split" ||
      planMonthlyReference.basis === "mixed");

  // --- Chart 1: Monthly Pipeline Activity (bar chart) ---
  const activityData = monthLabels.map((label, i) => {
    const monthKey = data.months[i]?.slice(0, 7);
    const isActual = actualFlags[i] ?? false;

    return {
      month: label,
      Won: isActual ? (actualWonByMonth[monthKey!] ?? 0) : (data.existing_wins[i] ?? 0),
      Lost: -(isActual ? (actualLostByMonth[monthKey!] ?? 0) : (data.existing_losses[i] ?? 0)),
      "New S2+ Pipeline": isActual ? (actualS2EnteredByMonth[monthKey!] ?? 0) : (data.pipeline_creation[i] ?? 0),
    };
  });

  // --- Chart 2: Pipeline Roll-Forward (stacked area) ---
  const capacityByMonth: Record<string, number> = {};
  if (capacityRows) {
    for (const row of capacityRows) {
      capacityByMonth[row.month.slice(0, 7)] = row.ae_capacity;
    }
  }

  const rollForwardData = monthLabels.map((label, i) => ({
    month: label,
    "Existing Pipeline": data.existing_wins[i] ?? 0,
    "Future Pipeline": data.future_wins[i] ?? 0,
    "Plan Target": showPlanTarget ? monthlyPlanTarget[i] : null,
    "AE Capacity": capacityByMonth[data.months[i]?.slice(0, 7)] ?? null,
  }));

  // --- Enhanced table data ---
  const tableRows = data.months.map((m, i) => {
    const monthKey = m.slice(0, 7);
    const isActual = actualFlags[i] ?? false;

    const won = isActual ? (actualWonByMonth[monthKey] ?? 0) : (data.existing_wins[i] ?? 0);
    const lost = isActual ? (actualLostByMonth[monthKey] ?? 0) : (data.existing_losses[i] ?? 0);
    const newPipeline = isActual ? (actualS2EnteredByMonth[monthKey] ?? 0) : (data.pipeline_creation[i] ?? 0);
    const net = won - lost + newPipeline;
    const remaining = data.existing_remaining[i] ?? 0;

    return {
      label: monthLabels[i],
      basis: isActual ? "Actual" : "Projected" as const,
      newPipeline,
      won,
      lost,
      net,
      remaining,
    };
  });

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      <SectionHeader
        title="Pipeline Inventory: Existing Inventory + Future Generation"
        subtitle="How current pipeline converts and how future S2+ pipeline creation fills the gap."
      />

      <MetricStrip metrics={kpiMetrics} />

      {!plan?.availability.comparableOnOperatorPages && plan ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          {plan.name} does not ship an operator-comparable default view. Pipeline Inventory suppresses selected-plan target rails on this page.
        </div>
      ) : null}

      {plan?.availability.comparableOnOperatorPages && !showPlanTarget ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          {planMonthlyReference.note}
        </div>
      ) : null}

      <ProseNote>
        Open inventory represents the S2+ deal set in the snapshot as of the
        snapshot date. Expected wins from existing pipeline are calculated using
        stage-based all-inclusive conversion rates. Future S2+ pipeline is
        modeled from AE capacity and observed S2-entry rates, with wins
        projected using the same conversion assumptions.
      </ProseNote>

      {/* Chart 1: Monthly Pipeline Activity */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">Monthly Pipeline Activity</h3>
        <p className="text-xs text-slate-500 mb-4">Won (green) is grouped by contractual CloseDate month. New S2+ pipeline (blue) is grouped by the month a deal first entered S2. Losses (red) are grouped by actual Closed At month. Solid line marks where projections begin — left is observed through {actualsThroughLabel}, right is model projections. Note: losses include all closed-lost opps, not filtered to S2+ stage history.</p>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={activityData}>
            <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
            <XAxis dataKey="month" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
            <YAxis tickFormatter={currencyFormatter} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={60} />
            <Tooltip formatter={currencyTooltipFormatter} contentStyle={TOOLTIP_STYLE.contentStyle} labelStyle={TOOLTIP_STYLE.labelStyle} />
            <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
            <ReferenceLine y={0} stroke="#94a3b8" strokeWidth={1} />
            {projectionStartLabel && (
              <ReferenceLine
                x={projectionStartLabel}
                stroke="#64748b"
                strokeWidth={2}
                label={{ value: "Projected", position: "top", fill: "#64748b", fontSize: 11 }}
              />
            )}
            <Bar dataKey="Won" fill={CHART_COLORS.emerald} radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="New S2+ Pipeline" fill={CHART_COLORS.blue} radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Lost" fill={CHART_COLORS.red} radius={[0, 0, 2, 2]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Chart 2: Pipeline Roll-Forward */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">Pipeline Roll-Forward</h3>
        <p className="text-xs text-slate-500 mb-4">Projected monthly wins from existing pipeline (blue) and future S2+ pipeline creation (green). Plan Target (red dashed) and AE Capacity (amber dashed) show the monthly demand vs close-capacity envelope.</p>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rollForwardData}>
            <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
            <XAxis dataKey="month" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
            <YAxis tickFormatter={currencyFormatter} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={60} />
            <Tooltip formatter={currencyTooltipFormatter} contentStyle={TOOLTIP_STYLE.contentStyle} labelStyle={TOOLTIP_STYLE.labelStyle} />
            <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
            <Area type="monotone" dataKey="Existing Pipeline" stackId="1" fill={CHART_COLORS.blue} stroke={CHART_COLORS.blue} strokeWidth={2} fillOpacity={0.7} isAnimationActive={false} />
            <Area type="monotone" dataKey="Future Pipeline" stackId="1" fill={CHART_COLORS.emerald} stroke={CHART_COLORS.emerald} strokeWidth={2} fillOpacity={0.7} isAnimationActive={false} />
            {showPlanTarget && (
              <Line type="monotone" dataKey="Plan Target" stroke={CHART_COLORS.red} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            )}
            {capacityRows && capacityRows.length > 0 && (
              <Line type="monotone" dataKey="AE Capacity" stroke={CHART_COLORS.amber} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      {/* Enhanced Monthly Detail Table */}
      <Card>
        <SectionHeader title="Monthly Pipeline Detail" />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Month</TableHeaderCell>
              <TableHeaderCell>Basis</TableHeaderCell>
              <TableHeaderCell className="text-right">New S2+ Pipeline</TableHeaderCell>
              <TableHeaderCell className="text-right">Won</TableHeaderCell>
              <TableHeaderCell className="text-right">Lost</TableHeaderCell>
              <TableHeaderCell className="text-right">Net</TableHeaderCell>
              <TableHeaderCell className="text-right">Remaining (Model)</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {tableRows.map((row, i) => (
              <TableRow key={data.months[i]}>
                <TableCell>{row.label}</TableCell>
                <TableCell>
                  <Badge color={row.basis === "Actual" ? "emerald" : "gray"} size="xs">
                    {row.basis}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">{formatMoney(row.newPipeline)}</TableCell>
                <TableCell className="text-right">{formatMoney(row.won)}</TableCell>
                <TableCell className="text-right">{formatMoney(row.lost)}</TableCell>
                <TableCell className="text-right font-medium">
                  {formatMoney(row.net)}
                </TableCell>
                <TableCell className="text-right">{formatMoney(row.remaining)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
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
