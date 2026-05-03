import {
  buildAcceptedScopeExclusions,
  buildCriticalSignals,
  buildFallbackExceptions,
  buildInactiveFallbackDebt,
  getAuditHealthRows,
  getAuditOverallStatus,
} from "./audit";
import {
  buildDefaultScenarioOverrides,
  hasAnyScenarioOverride,
  hasQuarterOverride,
} from "../engine/scenario";
import type { ScenarioOverrides, ScenarioResult } from "../engine/scenario";
import type { OrgProfile } from "./orgProfiles";
import type { ScenarioComputation } from "./scenarioEngine";
import type { Snapshot } from "../types/snapshot";
import type { PlanPreset } from "./plans";
import {
  buildPlanTimingSemantics,
  buildPlanMonthlyReference,
  getPlanFyTarget,
  type PlanTimingSemantics,
} from "./plans";
import { buildConnectorPolicyNotes } from "./orgProfiles";
import { formatMoney } from "./scenarioPlanner";
import { formatMonthLabel } from "./format";
import * as XLSX from "xlsx";

export interface ExportPreviewRow {
  month: string;
  inventoryWins: string;
  scenarioFutureWins: string;
  scenarioExpected: string;
  baselineCapped: string;
  scenarioCapped: string;
  planReference: string;
  baselineAeCount: number;
  scenarioAeCount: number;
  baselineAeCapacity: string;
  scenarioAeCapacity: string;
  isActual: boolean;
}

export interface ExportPackViewModel {
  orgProfileName: string;
  connectorPolicyNotes: string[];
  comparisonScopeLabel: string | null;
  comparisonScopeId: string | null;
  dealCount: number;
  overallStatus: ReturnType<typeof getAuditOverallStatus>;
  healthRows: ReturnType<typeof getAuditHealthRows>;
  criticalSignals: ReturnType<typeof buildCriticalSignals>;
  fallbackExceptions: ReturnType<typeof buildFallbackExceptions>;
  acceptedScopeExclusions: ReturnType<typeof buildAcceptedScopeExclusions>;
  inactiveFallbackDebt: ReturnType<typeof buildInactiveFallbackDebt>;
  planMonthlyReference: ReturnType<typeof buildPlanMonthlyReference>;
  planTimingSemantics: PlanTimingSemantics;
  planMonthly: number[];
  fyPlanTarget: number | null;
  baselineScenario: ScenarioResult;
  activeScenario: ScenarioResult;
  scenarioEngineId: string;
  scenarioEngineLabel: string;
  hasScenarioEdits: boolean;
  scenarioGapToPlan: number | null;
  scenarioDelta: number;
  editedQuarters: string[];
  previewRows: ExportPreviewRow[];
}

export function buildExportPackViewModel(
  snapshot: Snapshot,
  plan: PlanPreset | null,
  scenarioOverrides: ScenarioOverrides,
  baselineScenario: ScenarioComputation,
  activeScenario: ScenarioComputation,
  orgProfile: OrgProfile | null = null,
): ExportPackViewModel {
  const bb = snapshot.scenario_building_blocks;
  const planMonthlyReference = buildPlanMonthlyReference(bb.months, plan);
  const planTimingSemantics = buildPlanTimingSemantics(bb.months, plan);
  const planMonthly = planMonthlyReference.values;
  const fyPlanTarget = getPlanFyTarget(plan);
  const baselineOverrides = buildDefaultScenarioOverrides(snapshot);
  const baselineResult = baselineScenario.result;
  const activeResult = activeScenario.result;
  const hasScenarioEdits = hasAnyScenarioOverride(scenarioOverrides, baselineOverrides);
  // Iterate the overrides themselves — they're the source of truth for which
  // quarters the scenario engine treats as editable. The list is populated by
  // buildDefaultScenarioOverrides from snapshot.scenario_building_blocks.overridable_quarters.
  const editedQuarters = Object.keys(baselineOverrides).filter((quarter) =>
    hasQuarterOverride(quarter, scenarioOverrides, baselineOverrides),
  );
  const orgProfileName = orgProfile?.name ?? "Default org profile";

  return {
    orgProfileName,
    connectorPolicyNotes: orgProfile ? buildConnectorPolicyNotes(orgProfile) : [],
    comparisonScopeLabel: plan?.comparisonScopeLabel ?? null,
    comparisonScopeId: plan?.comparisonScopeId ?? null,
    dealCount: snapshot.pipeline.deals.length,
    overallStatus: getAuditOverallStatus(snapshot),
    healthRows: getAuditHealthRows(snapshot),
    criticalSignals: buildCriticalSignals(snapshot),
    fallbackExceptions: buildFallbackExceptions(snapshot),
    acceptedScopeExclusions: buildAcceptedScopeExclusions(snapshot),
    inactiveFallbackDebt: buildInactiveFallbackDebt(snapshot),
    planMonthlyReference,
    planTimingSemantics,
    planMonthly,
    fyPlanTarget,
    baselineScenario: baselineResult,
    activeScenario: activeResult,
    scenarioEngineId: activeScenario.engineId,
    scenarioEngineLabel: activeScenario.engineLabel,
    hasScenarioEdits,
    scenarioGapToPlan:
      typeof fyPlanTarget === "number" ? activeResult.fy_capped - fyPlanTarget : null,
    scenarioDelta: activeResult.fy_capped - baselineResult.fy_capped,
    editedQuarters,
    previewRows: bb.months.slice(0, 6).map((month, index) => ({
      month: formatMonthLabel(month),
      inventoryWins: formatMoney(bb.monthly_inventory_wins[index] ?? 0),
      scenarioFutureWins: formatMoney(activeResult.monthly_future_wins[index] ?? 0),
      scenarioExpected: formatMoney(activeResult.monthly_expected[index] ?? 0),
      baselineCapped: formatMoney(bb.monthly_capped[index] ?? 0),
      scenarioCapped: formatMoney(activeResult.monthly_capped[index] ?? 0),
      planReference: formatMoney(planMonthly[index] ?? 0),
      baselineAeCount: bb.monthly_ae_count[index] ?? 0,
      scenarioAeCount: Math.round(activeResult.monthly_ae_count[index] ?? 0),
      baselineAeCapacity: formatMoney(bb.monthly_ae_capacity[index] ?? 0),
      scenarioAeCapacity: formatMoney(activeResult.monthly_capacity[index] ?? 0),
      isActual: Boolean(bb.monthly_is_actual[index]),
    })),
  };
}

export function buildScenarioCsvContent(
  snapshot: Snapshot,
  viewModel: ExportPackViewModel,
): string {
  const headers = [
    "Org Profile",
    "Month",
    "Inventory Wins",
    "Scenario Future Wins",
    "Scenario Expected",
    "Saved Trajectory Capped",
    "Active Scenario Capped",
    viewModel.planMonthlyReference.label,
    "Baseline AE Count",
    "Scenario AE Count",
    "Baseline AE Capacity",
    "Scenario AE Capacity",
    "Is Actual",
  ];

  const rows = snapshot.scenario_building_blocks.months.map((month, index) => [
    viewModel.orgProfileName,
    formatMonthLabel(month),
    formatMoney(snapshot.scenario_building_blocks.monthly_inventory_wins[index] ?? 0),
    formatMoney(viewModel.activeScenario.monthly_future_wins[index] ?? 0),
    formatMoney(viewModel.activeScenario.monthly_expected[index] ?? 0),
    formatMoney(snapshot.scenario_building_blocks.monthly_capped[index] ?? 0),
    formatMoney(viewModel.activeScenario.monthly_capped[index] ?? 0),
    formatMoney(viewModel.planMonthly[index] ?? 0),
    String(snapshot.scenario_building_blocks.monthly_ae_count[index] ?? 0),
    String(Math.round(viewModel.activeScenario.monthly_ae_count[index] ?? 0)),
    formatMoney(snapshot.scenario_building_blocks.monthly_ae_capacity[index] ?? 0),
    formatMoney(viewModel.activeScenario.monthly_capacity[index] ?? 0),
    snapshot.scenario_building_blocks.monthly_is_actual[index] ? "true" : "false",
  ]);

  return [headers, ...rows].map((row) => row.map((cell) => `"${cell}"`).join(",")).join("\n");
}

export function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// XLSX Export — Auditable workbook with formulas
// ---------------------------------------------------------------------------

/** Column letter for a 0-based column index (A, B, ... Z, AA, AB, ...) */
function colLetter(idx: number): string {
  let letter = "";
  let n = idx;
  while (n >= 0) {
    letter = String.fromCharCode(65 + (n % 26)) + letter;
    n = Math.floor(n / 26) - 1;
  }
  return letter;
}

/** Set a cell in a worksheet at the given address. */
function setCell(
  ws: XLSX.WorkSheet,
  ref: string,
  value: string | number | boolean,
  opts?: { bold?: boolean },
) {
  const cell: XLSX.CellObject =
    typeof value === "number"
      ? { t: "n", v: value }
      : typeof value === "boolean"
        ? { t: "b", v: value }
        : { t: "s", v: value };
  if (opts?.bold) {
    cell.s = { font: { bold: true } };
  }
  ws[ref] = cell;
}

/** Set a formula cell in a worksheet. */
function setFormula(ws: XLSX.WorkSheet, ref: string, formula: string) {
  ws[ref] = { t: "n", f: formula };
}

/** Ensure a sheet's !ref range covers the given cell. */
function extendRange(ws: XLSX.WorkSheet, col: number, row: number) {
  const range = XLSX.utils.decode_range(ws["!ref"] ?? "A1:A1");
  if (col > range.e.c) range.e.c = col;
  if (row > range.e.r) range.e.r = row;
  ws["!ref"] = XLSX.utils.encode_range(range);
}

function buildSummarySheet(snapshot: Snapshot, viewModel: ExportPackViewModel): XLSX.WorkSheet {
  const ws: XLSX.WorkSheet = {};
  ws["!ref"] = "A1:B20";

  const rows: [string, string | number | null, string | null][] = [
    ["Forecast Tieout — Summary", null, null],
    ["", null, null],
    ["Generated At", snapshot.generated_at, null],
    ["As Of", snapshot.as_of, null],
    ["Org Profile", viewModel.orgProfileName, null],
    ["Revenue Metric", String(snapshot.assumptions?.revenue_metric ?? "metric_value"), null],
    ["Deal Count", viewModel.dealCount, null],
    ["", null, null],
    ["Annual Target", typeof viewModel.fyPlanTarget === "number" ? viewModel.fyPlanTarget : 0, null],
    ["Trajectory (Capped)", viewModel.activeScenario.fy_capped, null],
    ["Gap to Plan", null, "=B9-B10"], // formula
    ["", null, null],
    ["Weighted Pipeline", null, null], // computed below
    ["Overall Win Rate", snapshot.rates.overall_win_rate, null],
    ["Avg Deal Size", snapshot.scenario_building_blocks.observed_values.avg_deal_size, null],
    ["Avg Cycle Days", snapshot.scenario_building_blocks.observed_values.avg_cycle_days, null],
  ];

  // Calculate weighted pipeline for the value
  const weightedPipeline = snapshot.pipeline.deals.reduce((sum, d) => {
    const prob = snapshot.rates.stage_conversion[d.stage] ?? 0;
    return sum + d.metric_value * prob;
  }, 0);

  rows.forEach(([label, value, formula], i) => {
    const r = i + 1;
    setCell(ws, `A${r}`, label, { bold: i === 0 });
    if (formula) {
      setFormula(ws, `B${r}`, formula);
    } else if (value !== null && value !== undefined) {
      setCell(ws, `B${r}`, value);
    }
  });

  // Set weighted pipeline value
  setCell(ws, `B13`, weightedPipeline);

  // Column widths
  ws["!cols"] = [{ wch: 24 }, { wch: 20 }];

  return ws;
}

function buildBookingsBridgeSheet(
  snapshot: Snapshot,
  viewModel: ExportPackViewModel,
): XLSX.WorkSheet {
  const bb = snapshot.scenario_building_blocks;
  const months = bb.months;
  const ws: XLSX.WorkSheet = {};

  // Header row
  setCell(ws, "A1", "Month", { bold: true });
  setCell(ws, "B1", "Inventory Wins", { bold: true });
  setCell(ws, "C1", "Future Wins", { bold: true });
  setCell(ws, "D1", "Total Expected", { bold: true });
  setCell(ws, "E1", "Capped (Trajectory)", { bold: true });
  setCell(ws, "F1", "Plan Reference", { bold: true });
  setCell(ws, "G1", "Is Actual", { bold: true });

  months.forEach((month, i) => {
    const r = i + 2;
    setCell(ws, `A${r}`, formatMonthLabel(month));
    setCell(ws, `B${r}`, bb.monthly_inventory_wins[i] ?? 0);
    setCell(ws, `C${r}`, viewModel.activeScenario.monthly_future_wins[i] ?? 0);
    // Total Expected = Inventory Wins + Future Wins
    setFormula(ws, `D${r}`, `=B${r}+C${r}`);
    setCell(ws, `E${r}`, viewModel.activeScenario.monthly_capped[i] ?? 0);
    setCell(ws, `F${r}`, viewModel.planMonthly[i] ?? 0);
    setCell(ws, `G${r}`, bb.monthly_is_actual[i] ? "Actual" : "Projected");
  });

  // Totals row
  const totalRow = months.length + 2;
  setCell(ws, `A${totalRow}`, "TOTAL", { bold: true });
  for (const col of ["B", "C", "D", "E", "F"]) {
    setFormula(ws, `${col}${totalRow}`, `=SUM(${col}2:${col}${totalRow - 1})`);
  }

  // Quarterly subtotals below the total row
  // Group months by quarter (3-month groups)
  const qStartRow = totalRow + 2;
  setCell(ws, `A${qStartRow}`, "Quarterly Breakdown", { bold: true });
  const numQuarters = Math.ceil(months.length / 3);
  for (let q = 0; q < numQuarters; q++) {
    const qRow = qStartRow + 1 + q;
    const startMonth = q * 3;
    const endMonth = Math.min(startMonth + 2, months.length - 1);
    const startDataRow = startMonth + 2;
    const endDataRow = endMonth + 2;
    setCell(ws, `A${qRow}`, `Q${q + 1}`);
    for (const col of ["B", "C", "D", "E", "F"]) {
      setFormula(ws, `${col}${qRow}`, `=SUM(${col}${startDataRow}:${col}${endDataRow})`);
    }
  }

  const lastRow = qStartRow + numQuarters;
  ws["!ref"] = `A1:G${lastRow}`;
  ws["!cols"] = [
    { wch: 14 },
    { wch: 16 },
    { wch: 16 },
    { wch: 18 },
    { wch: 20 },
    { wch: 16 },
    { wch: 12 },
  ];

  return ws;
}

function buildPipelineSheet(snapshot: Snapshot): XLSX.WorkSheet {
  const deals = snapshot.pipeline.deals;
  const stageConversion = snapshot.rates.stage_conversion;

  // Header row
  const headers = [
    "Opp ID",
    "Stage",
    "Amount",
    "Metric Value",
    "Probability",
    "Weighted Value",
    "Owner",
    "Close Date",
    "Source Stream",
    "Forecast Category",
  ];

  const aoa: (string | number)[][] = [headers];

  // Sort deals by stage then amount descending
  const sortedDeals = [...deals].sort((a, b) => {
    if (a.stage !== b.stage) return a.stage.localeCompare(b.stage);
    return b.metric_value - a.metric_value;
  });

  sortedDeals.forEach((deal) => {
    aoa.push([
      deal.opp_id,
      deal.stage,
      deal.amount,
      deal.metric_value,
      stageConversion[deal.stage] ?? 0,
      0, // placeholder — formula will override
      deal.owner_name,
      deal.close_date ?? "",
      deal.source_stream,
      deal.forecast_category,
    ]);
  });

  const ws = XLSX.utils.aoa_to_sheet(aoa);

  // Replace Weighted Value column (F) with formulas: =D{n}*E{n}
  for (let i = 0; i < sortedDeals.length; i++) {
    const r = i + 2; // row 2 onwards (row 1 is header)
    setFormula(ws, `F${r}`, `=D${r}*E${r}`);
  }

  // Stage subtotals
  let currentRow = sortedDeals.length + 2;
  currentRow++; // blank row
  setCell(ws, `A${currentRow}`, "Stage Subtotals", { bold: true });
  currentRow++;

  const stages = [...new Set(sortedDeals.map((d) => d.stage))];
  stages.forEach((stage) => {
    const stageDeals = sortedDeals
      .map((d, i) => (d.stage === stage ? i + 2 : -1))
      .filter((r) => r > 0);
    setCell(ws, `A${currentRow}`, stage);
    setCell(ws, `B${currentRow}`, stageDeals.length);
    // Sum of metric values for this stage
    const metricRefs = stageDeals.map((r) => `D${r}`).join("+");
    setFormula(ws, `D${currentRow}`, `=${metricRefs}`);
    // Sum of weighted values for this stage
    const weightedRefs = stageDeals.map((r) => `F${r}`).join("+");
    setFormula(ws, `F${currentRow}`, `=${weightedRefs}`);
    currentRow++;
  });

  // Grand total
  currentRow++;
  setCell(ws, `A${currentRow}`, "GRAND TOTAL", { bold: true });
  setCell(ws, `B${currentRow}`, sortedDeals.length);
  setFormula(ws, `D${currentRow}`, `=SUM(D2:D${sortedDeals.length + 1})`);
  setFormula(ws, `F${currentRow}`, `=SUM(F2:F${sortedDeals.length + 1})`);

  // Update range
  extendRange(ws, 9, currentRow - 1); // 10 columns (J), row is 0-indexed

  ws["!cols"] = [
    { wch: 20 }, // Opp ID
    { wch: 18 }, // Stage
    { wch: 14 }, // Amount
    { wch: 14 }, // Metric Value
    { wch: 12 }, // Probability
    { wch: 16 }, // Weighted Value
    { wch: 18 }, // Owner
    { wch: 12 }, // Close Date
    { wch: 16 }, // Source Stream
    { wch: 18 }, // Forecast Category
  ];

  return ws;
}

function buildCapacitySheet(snapshot: Snapshot): XLSX.WorkSheet {
  const capacity = snapshot.roster.effective_capacity;
  const currentAes = snapshot.roster.current_aes;

  const ws: XLSX.WorkSheet = {};

  // Section 1: Current AE Roster
  setCell(ws, "A1", "Current AE Roster", { bold: true });
  const rosterHeaders = ["Name", "Segment", "Start Date", "Is Ramping"];
  rosterHeaders.forEach((h, i) => {
    setCell(ws, `${colLetter(i)}2`, h, { bold: true });
  });

  currentAes.forEach((ae, i) => {
    const r = i + 3;
    setCell(ws, `A${r}`, String(ae.name ?? ae.ae_name ?? "Unknown"));
    setCell(ws, `B${r}`, String(ae.segment ?? ae.territory ?? ""));
    setCell(ws, `C${r}`, String(ae.start_date ?? ae.hire_date ?? ""));
    setCell(ws, `D${r}`, ae.is_ramping ? "Yes" : "No");
  });

  // Section 2: Monthly Capacity Projection
  const capStartRow = currentAes.length + 5;
  setCell(ws, `A${capStartRow}`, "Monthly Capacity Projection", { bold: true });

  const capHeaders = [
    "Month",
    "AE Total",
    "AE Ramped",
    "AE Ramping",
    "Blended Ramp %",
    "AE Capacity",
    "Capacity (Ramped)",
    "Capacity (Ramping)",
    "Monthly Target",
  ];
  capHeaders.forEach((h, i) => {
    setCell(ws, `${colLetter(i)}${capStartRow + 1}`, h, { bold: true });
  });

  capacity.forEach((row, i) => {
    const r = capStartRow + 2 + i;
    setCell(ws, `A${r}`, row.label ?? row.month);
    setCell(ws, `B${r}`, row.ae_total);
    setCell(ws, `C${r}`, row.ae_ramped);
    setCell(ws, `D${r}`, row.ae_ramping);
    setCell(ws, `E${r}`, row.blended_ramp_pct);
    // AE Capacity = Ramped Capacity + Ramping Capacity
    setFormula(ws, `F${r}`, `=G${r}+H${r}`);
    setCell(ws, `G${r}`, row.ae_capacity_ramped);
    setCell(ws, `H${r}`, row.ae_capacity_ramping);
    setCell(ws, `I${r}`, row.monthly_target);
  });

  // Totals
  const capTotalRow = capStartRow + 2 + capacity.length;
  setCell(ws, `A${capTotalRow}`, "TOTAL", { bold: true });
  for (const col of ["F", "G", "H", "I"]) {
    setFormula(
      ws,
      `${col}${capTotalRow}`,
      `=SUM(${col}${capStartRow + 2}:${col}${capTotalRow - 1})`,
    );
  }

  ws["!ref"] = `A1:I${capTotalRow}`;
  ws["!cols"] = [
    { wch: 18 },
    { wch: 10 },
    { wch: 12 },
    { wch: 12 },
    { wch: 14 },
    { wch: 14 },
    { wch: 18 },
    { wch: 18 },
    { wch: 16 },
  ];

  return ws;
}

function buildAssumptionsSheet(snapshot: Snapshot): XLSX.WorkSheet {
  const ws: XLSX.WorkSheet = {};

  let row = 1;

  // Section 1: Stage Conversion Rates
  setCell(ws, `A${row}`, "Stage Conversion Rates", { bold: true });
  row++;
  setCell(ws, `A${row}`, "Stage", { bold: true });
  setCell(ws, `B${row}`, "Win Rate", { bold: true });
  row++;

  const stageConv = snapshot.rates.stage_conversion;
  Object.entries(stageConv)
    .sort(([, a], [, b]) => b - a)
    .forEach(([stage, rate]) => {
      setCell(ws, `A${row}`, stage);
      setCell(ws, `B${row}`, rate);
      row++;
    });

  // Section 2: Stage Win Rates (from building blocks)
  row++;
  setCell(ws, `A${row}`, "Scenario Stage Win Rates", { bold: true });
  row++;
  setCell(ws, `A${row}`, "Stage", { bold: true });
  setCell(ws, `B${row}`, "Win Rate", { bold: true });
  row++;

  const stageWinRates = snapshot.scenario_building_blocks.stage_win_rates;
  Object.entries(stageWinRates)
    .sort(([, a], [, b]) => b - a)
    .forEach(([stage, rate]) => {
      setCell(ws, `A${row}`, stage);
      setCell(ws, `B${row}`, rate);
      row++;
    });

  // Section 3: Observed Values
  row++;
  setCell(ws, `A${row}`, "Observed Values", { bold: true });
  row++;

  const obs = snapshot.scenario_building_blocks.observed_values;
  const obsRows: [string, number][] = [
    ["Win Rate", obs.win_rate],
    ["Avg Deal Size", obs.avg_deal_size],
    ["Avg Cycle Days", obs.avg_cycle_days],
    ["Ramp Months", obs.ramp_months],
    ["Productivity per AE per Month", obs.productivity_per_ae_per_month],
  ];
  obsRows.forEach(([label, val]) => {
    setCell(ws, `A${row}`, label);
    setCell(ws, `B${row}`, val);
    row++;
  });

  // Section 4: Decay Curve
  row++;
  setCell(ws, `A${row}`, "Decay Curve", { bold: true });
  row++;
  snapshot.scenario_building_blocks.decay_curve.forEach((val, i) => {
    setCell(ws, `A${row}`, `Month ${i + 1}`);
    setCell(ws, `B${row}`, val);
    row++;
  });

  // Section 5: Metadata
  row++;
  setCell(ws, `A${row}`, "Data Freshness", { bold: true });
  row++;
  setCell(ws, `A${row}`, "Generated At");
  setCell(ws, `B${row}`, snapshot.generated_at);
  row++;
  setCell(ws, `A${row}`, "As Of");
  setCell(ws, `B${row}`, snapshot.as_of);
  row++;
  setCell(ws, `A${row}`, "Engine Version");
  setCell(ws, `B${row}`, snapshot.engine_version);
  row++;
  setCell(ws, `A${row}`, "Schema Version");
  setCell(ws, `B${row}`, snapshot.schema_version);
  row++;
  setCell(ws, `A${row}`, "Revenue Metric");
  setCell(ws, `B${row}`, String(snapshot.assumptions?.revenue_metric ?? "metric_value"));

  ws["!ref"] = `A1:B${row}`;
  ws["!cols"] = [{ wch: 30 }, { wch: 20 }];

  return ws;
}

export function generateXlsxWorkbook(
  snapshot: Snapshot,
  viewModel: ExportPackViewModel,
): XLSX.WorkBook {
  const wb = XLSX.utils.book_new();

  const summaryWs = buildSummarySheet(snapshot, viewModel);
  XLSX.utils.book_append_sheet(wb, summaryWs, "Summary");

  const bridgeWs = buildBookingsBridgeSheet(snapshot, viewModel);
  XLSX.utils.book_append_sheet(wb, bridgeWs, "Bookings Bridge");

  const pipelineWs = buildPipelineSheet(snapshot);
  XLSX.utils.book_append_sheet(wb, pipelineWs, "Pipeline");

  const capacityWs = buildCapacitySheet(snapshot);
  XLSX.utils.book_append_sheet(wb, capacityWs, "Capacity");

  const assumptionsWs = buildAssumptionsSheet(snapshot);
  XLSX.utils.book_append_sheet(wb, assumptionsWs, "Assumptions");

  return wb;
}

export function downloadXlsx(snapshot: Snapshot, viewModel: ExportPackViewModel): void {
  const wb = generateXlsxWorkbook(snapshot, viewModel);
  const ts = snapshot.as_of.replace(/-/g, "");
  XLSX.writeFile(wb, `forecast-tieout-${ts}.xlsx`);
}
