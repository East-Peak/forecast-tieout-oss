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
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { CapacityHeadcountData, Deal, PipelineInventoryData, ObservedValues } from "../types/snapshot";
import { SectionHeader, ProseNote } from "../components/workbook";
import { formatMoney, formatMonthLabel } from "../lib/format";
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
import { usePlanningSessionContext } from "../context/PlanningSessionContext";

export default function CapacityHeadcount() {
  const { snapshot, selectedPlan: plan, snapshotMeta } = usePlanningSessionContext();
  const data: CapacityHeadcountData = snapshot.model_output.capacity_headcount;
  const pipelineDeals: Deal[] = snapshot.pipeline.deals;
  const pipelineInventory: PipelineInventoryData =
    snapshot.model_output.pipeline_inventory;
  const observedValues: ObservedValues =
    snapshot.scenario_building_blocks.observed_values;
  const rows = data.trajectory_capacity;
  const monthLabels = rows.map((r) => formatMonthLabel(r.month));
  const planMonthlyReference = buildPlanMonthlyReference(rows.map((row) => row.month), plan);
  const showPlanMonthlyTarget =
    (plan?.availability.comparableOnOperatorPages ?? false) &&
    (planMonthlyReference.basis === "explicit_monthly_plan" ||
      planMonthlyReference.basis === "derived_even_quarter_split" ||
      planMonthlyReference.basis === "mixed");

  // --- SE data check ---
  const hasSEData = rows.some((r) => r.se_total > 0);

  // --- SE deal loading metrics ---
  const S2_PLUS_STAGES = ["S2", "S3", "S4", "S5"];
  const PLG_PATTERNS = ["self", "plg", "self-serve", "self_serve"];

  const allS2PlusDeals = pipelineDeals.filter((d) =>
    S2_PLUS_STAGES.includes(d.stage)
  );
  const seSupportedS2PlusDeals = allS2PlusDeals.filter((d) => {
    const stream = (d.source_stream ?? "").toLowerCase();
    return !PLG_PATTERNS.some((p) => stream.includes(p));
  });

  const snapshotMonthKey =
    snapshotMeta?.as_of?.slice(0, 7) ?? new Date().toISOString().slice(0, 7);
  const snapshotIndex = rows.findIndex((r) => r.month.slice(0, 7) === snapshotMonthKey);
  const currentRow =
    snapshotIndex >= 0 ? rows[snapshotIndex] : rows[rows.length - 1];
  const currentSECount = currentRow?.se_total ?? 0;
  const currentAECount = currentRow?.ae_total ?? 0;
  const aeSeRatioCurrent = currentSECount > 0 ? currentAECount / currentSECount : null;
  const dealsPerSE = currentSECount > 0 ? seSupportedS2PlusDeals.length / currentSECount : null;

  // --- Project monthly S2+ deal count ---
  // Use the current snapshot's observed non-PLG S2+ open opp count as the base,
  // then roll forward only for months after the snapshot month.
  const avgDealSize = observedValues?.avg_deal_size ?? 0;
  const monthlyProjectedDeals: Array<number | null> = new Array(rows.length).fill(null);
  if (snapshotIndex >= 0) {
    let runningDeals = seSupportedS2PlusDeals.length;
    monthlyProjectedDeals[snapshotIndex] = runningDeals;
    if (avgDealSize > 0) {
      for (let i = snapshotIndex + 1; i < rows.length; i++) {
        const winsVal = pipelineInventory?.existing_wins[i] ?? 0;
        const lossesVal = pipelineInventory?.existing_losses[i] ?? 0;
        const creationVal = pipelineInventory?.pipeline_creation[i] ?? 0;
        const dealsOut = (winsVal + lossesVal) / avgDealSize;
        const dealsIn = creationVal / avgDealSize;
        runningDeals = Math.max(0, runningDeals - dealsOut + dealsIn);
        monthlyProjectedDeals[i] = Math.round(runningDeals);
      }
    }
  }
  const SE_DEAL_THRESHOLD = 5;

  // --- AE Headcount stacked bar data ---
  const headcountData = rows.map((r, i) => ({
    month: monthLabels[i],
    Ramped: r.ae_ramped,
    Ramping: r.ae_ramping,
  }));

  // --- Capacity vs Targets line data ---
  const capacityData = rows.map((r, i) => ({
    month: monthLabels[i],
    Capacity: r.ae_capacity,
    Target: showPlanMonthlyTarget ? (planMonthlyReference.values[i] ?? 0) : null,
  }));

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      <SectionHeader
        title="Monthly Sales Capacity"
        subtitle="Roster-backed headcount and close capacity derived from confirmed hires only."
        caption="Open requisitions excluded. Use scenario sliders to model headcount upside."
      />

      <ProseNote>
        Capacity is calculated from the confirmed AE roster. Ramped AEs
        contribute at full productivity; ramping AEs contribute proportionally
        based on time since start date. The blended ramp percentage reflects the
        weighted average across all AEs. Close capacity = ramped equivalents
        multiplied by observed productivity per AE per month.
      </ProseNote>

      {!plan?.availability.comparableOnOperatorPages && plan ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          {plan.name} does not ship an operator-comparable default view. Capacity target rails are suppressed on this page.
        </div>
      ) : null}

      {plan?.availability.comparableOnOperatorPages && !showPlanMonthlyTarget ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          {planMonthlyReference.note}
        </div>
      ) : null}

      {/* AE Headcount Chart */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">AE Headcount</h3>
        <p className="text-xs text-slate-500 mb-4">Confirmed roster only (active + incoming hires with signed agreements). Does not include planned-but-unfilled positions.</p>
        <ResponsiveContainer width="100%" height={288}>
          <BarChart data={headcountData}>
            <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
            <XAxis dataKey="month" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
            <YAxis tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={40} />
            <Tooltip contentStyle={TOOLTIP_STYLE.contentStyle} labelStyle={TOOLTIP_STYLE.labelStyle} />
            <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
            <Bar dataKey="Ramped" stackId="a" fill={CHART_COLORS.blue} radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Ramping" stackId="a" fill="#93c5fd" radius={[2, 2, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Close Capacity vs Targets */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">Close Capacity vs Targets</h3>
        <p className="text-xs text-slate-500 mb-4">Monthly close capacity (amber) against plan targets (red).</p>
        <ResponsiveContainer width="100%" height={288}>
          <LineChart data={capacityData}>
            <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
            <XAxis dataKey="month" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
            <YAxis tickFormatter={currencyFormatter} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={60} />
            <Tooltip formatter={currencyTooltipFormatter} contentStyle={TOOLTIP_STYLE.contentStyle} labelStyle={TOOLTIP_STYLE.labelStyle} />
            <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
            <Line type="monotone" dataKey="Capacity" stroke={CHART_COLORS.amber} strokeWidth={2} dot={false} isAnimationActive={false} />
            {showPlanMonthlyTarget ? (
              <Line type="monotone" dataKey="Target" stroke={CHART_COLORS.red} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <ProseNote>
        The gap between AE close capacity (amber) and monthly targets (red
        dashed) indicates hiring urgency. When capacity falls below targets, the
        team cannot physically close enough deals to meet plan even with perfect
        conversion. Use the Scenario Planner to model headcount acceleration
        scenarios.
      </ProseNote>

      {/* Monthly Roster Detail Table */}
      <Card>
        <SectionHeader title="Monthly Roster Detail" />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Month</TableHeaderCell>
              <TableHeaderCell className="text-right">Total AEs</TableHeaderCell>
              <TableHeaderCell className="text-right">Ramped</TableHeaderCell>
              <TableHeaderCell className="text-right">Ramping</TableHeaderCell>
              <TableHeaderCell className="text-right">Ramp %</TableHeaderCell>
              <TableHeaderCell className="text-right">Capacity</TableHeaderCell>
              <TableHeaderCell className="text-right">Target</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={r.month}>
                <TableCell>{monthLabels[i]}</TableCell>
                <TableCell className="text-right">{r.ae_total}</TableCell>
                <TableCell className="text-right">{r.ae_ramped}</TableCell>
                <TableCell className="text-right">{r.ae_ramping}</TableCell>
                <TableCell className="text-right">
                  {(r.blended_ramp_pct * 100).toFixed(0)}%
                </TableCell>
                <TableCell className="text-right">
                  {formatMoney(r.ae_capacity)}
                </TableCell>
                <TableCell className="text-right">
                  {showPlanMonthlyTarget ? formatMoney(planMonthlyReference.values[i] ?? 0) : "\u2014"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* SE Capacity */}
      <SectionHeader
        title="SE Capacity & Deal Loading"
        subtitle="Solutions Engineers support AEs during technical evaluations (S2+)."
      />

      {hasSEData ? (
        <>
          {/* SE Metrics Strip */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Card className="p-4">
              <p className="text-xs text-slate-500 mb-1">SEs at Snapshot</p>
              <p className="text-2xl font-semibold text-slate-800">{currentSECount}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-slate-500 mb-1">S2+ Open Opps (SE-supported)</p>
              <p className="text-2xl font-semibold text-slate-800">{seSupportedS2PlusDeals.length}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-slate-500 mb-1">S2+ Opps/SE at Snapshot</p>
              <p className={`text-2xl font-semibold ${dealsPerSE !== null && dealsPerSE > SE_DEAL_THRESHOLD ? "text-red-600" : "text-slate-800"}`}>
                {dealsPerSE !== null ? dealsPerSE.toFixed(1) : "\u2014"}
              </p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-slate-500 mb-1">AE:SE at Snapshot</p>
              <p className="text-2xl font-semibold text-slate-800">
                {aeSeRatioCurrent !== null ? `${aeSeRatioCurrent.toFixed(1)}:1` : "\u2014"}
              </p>
            </Card>
          </div>

          {/* SE Capacity Risk Warning */}
          {dealsPerSE !== null && dealsPerSE > SE_DEAL_THRESHOLD && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="font-semibold text-red-800">SE Capacity Risk</p>
              <p className="text-sm text-red-700">
                {dealsPerSE.toFixed(1)} active S2+ opportunities per SE exceeds the 5-opp threshold.
                Technical evaluations may stall without additional SE capacity.
              </p>
            </div>
          )}

          <ProseNote>
            SE loading excludes PLG and self-serve opportunities (SEs do not support the product-led growth motion).
            The 5-opp threshold per SE is the capacity limit — above this, technical evaluations may stall.
            As the commercial team scales, finer-grain SE assignment by segment will be needed.
          </ProseNote>

          {/* Monthly AE:SE Ratio Table */}
          <Card>
            <SectionHeader title="Monthly AE:SE Ratio & Opportunity Loading" subtitle="Snapshot month uses observed open S2+ opps. Future months are projected from pipeline flow. Earlier months are not reconstructed from historical snapshots. S2+ Opps/SE turns red above 5 opps per SE (capacity threshold)." />
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Month</TableHeaderCell>
                  <TableHeaderCell className="text-right">AEs</TableHeaderCell>
                  <TableHeaderCell className="text-right">SEs</TableHeaderCell>
                  <TableHeaderCell className="text-right">AE:SE Ratio</TableHeaderCell>
                  <TableHeaderCell className="text-right">S2+ Opps</TableHeaderCell>
                  <TableHeaderCell className="text-right">S2+ Opps/SE</TableHeaderCell>
                  <TableHeaderCell className="text-right">Monthly Target</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((r, i) => {
                  const projOpps = monthlyProjectedDeals[i];
                  const oppsSERatio =
                    projOpps !== null && r.se_total > 0 ? projOpps / r.se_total : null;
                  const oppsColor =
                    oppsSERatio !== null && oppsSERatio > SE_DEAL_THRESHOLD
                      ? "text-red-600 font-medium"
                      : "";
                  const rowBasis =
                    i === snapshotIndex ? "(obs)" : i > snapshotIndex ? "(proj)" : "(n/a)";
                  return (
                    <TableRow key={`se-${r.month}`}>
                      <TableCell>{monthLabels[i]}</TableCell>
                      <TableCell className="text-right">{r.ae_total}</TableCell>
                      <TableCell className="text-right">{r.se_total}</TableCell>
                      <TableCell className="text-right">
                        {r.se_total > 0 ? `${(r.ae_total / r.se_total).toFixed(1)}:1` : "\u2014"}
                      </TableCell>
                      <TableCell className="text-right">
                        {projOpps ?? "\u2014"}
                        <span className="ml-1 text-xs text-slate-400">{rowBasis}</span>
                      </TableCell>
                      <TableCell className={`text-right ${oppsColor}`}>
                        {oppsSERatio !== null ? oppsSERatio.toFixed(1) : "\u2014"}
                      </TableCell>
                      <TableCell className="text-right">
                        {showPlanMonthlyTarget ? formatMoney(planMonthlyReference.values[i] ?? 0) : "\u2014"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>
        </>
      ) : (
        <Card className="p-5">
          <p className="text-sm text-slate-500">SE headcount data not available. Add SE entries to config/roster.yaml to enable SE capacity tracking.</p>
        </Card>
      )}

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
