import { useMemo } from "react";
import { ExportAuditSummaryCard } from "../components/exportPack/ExportAuditSummaryCard";
import { ExportCsvPreviewCard } from "../components/exportPack/ExportCsvPreviewCard";
import { ExportDownloads } from "../components/exportPack/ExportDownloads";
import { ExportMetadataCard } from "../components/exportPack/ExportMetadataCard";
import { ExportScenarioStateCard } from "../components/exportPack/ExportScenarioStateCard";
import { ExportSemanticsCard } from "../components/exportPack/ExportSemanticsCard";
import { PlanTimingSemanticsCard } from "../components/plans/PlanTimingSemanticsCard";
import { SnapshotFooter } from "../components/trust";
import { SectionHeader } from "../components/workbook";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { buildDefaultScenarioOverrides, computeScenario } from "../engine/scenario";
import { buildAuditReportText } from "../lib/audit";
import {
  buildExportPackViewModel,
  buildScenarioCsvContent,
  downloadBlob,
  downloadXlsx,
} from "../lib/exportPack";
import { formatMoney } from "../lib/format";
import type { ScenarioComputation } from "../lib/scenarioEngine";

export default function ExportPack() {
  const {
    snapshot,
    selectedOrgProfile,
    selectedPlan: plan,
  } = usePlanningSessionContext();

  // Export uses baseline scenario only (no scenario overrides on this page)
  const baselineOverrides = useMemo(
    () => buildDefaultScenarioOverrides(snapshot),
    [snapshot],
  );
  const baselineComputation: ScenarioComputation = useMemo(() => ({
    engineId: "frontend-local",
    engineLabel: "Frontend local adapter (backend-compatible contract)",
    request: { version: 1, quarters: {} as ScenarioComputation["request"]["quarters"] },
    result: computeScenario(snapshot, baselineOverrides),
  }), [snapshot, baselineOverrides]);

  const viewModel = buildExportPackViewModel(
    snapshot,
    plan,
    baselineOverrides,
    baselineComputation,
    baselineComputation,
    selectedOrgProfile,
  );
  const buildingBlocks = snapshot.scenario_building_blocks;
  const ts = snapshot.as_of.replace(/-/g, "");

  function handleDownloadJSON() {
    downloadBlob(
      JSON.stringify(snapshot, null, 2),
      `forecast-tieout-snapshot-${ts}.json`,
      "application/json",
    );
  }

  function handleDownloadCSV() {
    downloadBlob(
      buildScenarioCsvContent(snapshot, viewModel),
      `forecast-tieout-monthly-summary-${ts}.csv`,
      "text/csv",
    );
  }

  function handleDownloadAuditReport() {
    downloadBlob(
      buildAuditReportText(snapshot),
      `forecast-tieout-audit-report-${ts}.txt`,
      "text/plain",
    );
  }

  function handleDownloadXLSX() {
    downloadXlsx(snapshot, viewModel);
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <SectionHeader
        title="Export Pack"
        subtitle="Download the saved snapshot baseline, a live scenario-aware monthly CSV, or a plain-text audit report for finance review."
      />

      <ExportDownloads
        onDownloadJSON={handleDownloadJSON}
        onDownloadCSV={handleDownloadCSV}
        onDownloadAuditReport={handleDownloadAuditReport}
        onDownloadXLSX={handleDownloadXLSX}
      />

      <ExportMetadataCard
        orgProfileName={viewModel.orgProfileName}
        generatedAt={snapshot.generated_at}
        asOf={snapshot.as_of}
        selectedPlan={plan?.name ?? "\u2014"}
        comparisonScope={viewModel.comparisonScopeLabel ?? "\u2014"}
        fyPlanTarget={typeof viewModel.fyPlanTarget === "number" ? formatMoney(viewModel.fyPlanTarget) : "\u2014"}
        scenarioEngine={viewModel.scenarioEngineLabel}
        plannerState={
          viewModel.hasScenarioEdits ? "Scenario override active" : "Matches saved baseline"
        }
        editedQuarters={
          viewModel.editedQuarters.length > 0 ? viewModel.editedQuarters.join(", ") : "\u2014"
        }
        gitSha={snapshot.git_sha ? snapshot.git_sha.slice(0, 8) : "\u2014"}
        dealCount={String(viewModel.dealCount)}
        monthsInModel={String(buildingBlocks.months.length)}
        actualMonths={String(buildingBlocks.monthly_is_actual.filter(Boolean).length)}
      />

      <ExportScenarioStateCard
        baselineFy={formatMoney(viewModel.baselineScenario.fy_capped)}
        scenarioFy={formatMoney(viewModel.activeScenario.fy_capped)}
        scenarioDelta={`${viewModel.scenarioDelta >= 0 ? "+" : "-"}${formatMoney(
          Math.abs(viewModel.scenarioDelta),
        )}`}
        scenarioDeltaPositive={viewModel.scenarioDelta >= 0}
        scenarioGapToPlan={
          typeof viewModel.scenarioGapToPlan === "number"
            ? `${viewModel.scenarioGapToPlan >= 0 ? "+" : "-"}${formatMoney(
                Math.abs(viewModel.scenarioGapToPlan),
              )}`
            : "\u2014"
        }
        scenarioGapPositive={
          typeof viewModel.scenarioGapToPlan === "number"
            ? viewModel.scenarioGapToPlan >= 0
            : false
        }
        plannerStateNote={
          viewModel.hasScenarioEdits
            ? `Quarter overrides are currently active in ${viewModel.editedQuarters.join(", ")}. The CSV preview and download below reflect that live planner state.`
            : typeof viewModel.scenarioGapToPlan === "number"
              ? "No planner overrides are active. The scenario CSV currently matches the saved baseline for projected months."
              : "No planner overrides are active. Primary gap math is suppressed because the selected plan does not expose an operator-comparable annual target."
        }
      />

      <ExportAuditSummaryCard viewModel={viewModel} />
      <PlanTimingSemanticsCard semantics={viewModel.planTimingSemantics} />
      <ExportSemanticsCard
        planNote={viewModel.planMonthlyReference.note}
        orgProfileName={viewModel.orgProfileName}
        connectorPolicyNotes={viewModel.connectorPolicyNotes}
      />
      <ExportCsvPreviewCard
        planNote={viewModel.planMonthlyReference.note}
        rows={viewModel.previewRows}
      />

      <SnapshotFooter snapshot={snapshot} />
    </div>
  );
}
