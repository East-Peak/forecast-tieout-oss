import { useState } from "react";
import {
  Callout,
  Select,
  SelectItem,
  Text,
} from "../components/ui";
import { SectionHeader } from "../components/workbook";
import {
  FunnelArrMix,
  FunnelConversionSections,
  FunnelExpansionSection,
  FunnelKpiStrip,
  FunnelPaceTable,
  FunnelQuarterlySummary,
  FunnelSourceStreamSection,
  FunnelWaterfalls,
} from "../components/funnelHealth";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { buildFunnelHealthViewModel } from "../lib/funnelHealthViewModel";

export default function FunnelHealth() {
  const { snapshot, selectedPlan: plan, snapshotMeta } = usePlanningSessionContext();
  const quarters = snapshot.model_output.funnel_health.trajectory_quarters.map(
    (quarter) => quarter.quarter,
  );
  const [selectedQuarter, setSelectedQuarter] = useState(quarters[0] ?? "");
  const viewModel = buildFunnelHealthViewModel({
    snapshot,
    plan,
    selectedQuarter,
  });

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      <SectionHeader
        title="Funnel Health"
        subtitle="Observed conversion rates, quarterly funnel pacing, source-stream breakdown, and expansion workstream."
      />

      <div className="flex items-center gap-3">
        <Text className="text-xs font-medium text-slate-600 uppercase tracking-wide">
          Quarter
        </Text>
        <Select
          id="funnel-quarter"
          name="funnel-quarter"
          value={viewModel.selectedQuarter}
          onValueChange={setSelectedQuarter}
          className="max-w-[160px]"
        >
          {viewModel.quarters.map((quarter) => (
            <SelectItem key={quarter} value={quarter}>
              {quarter}
            </SelectItem>
          ))}
        </Select>
      </div>

      <FunnelKpiStrip metrics={viewModel.metrics} />

      {viewModel.notices.map((notice) => (
        <Callout key={notice.title} title={notice.title} color={notice.color}>
          {notice.message}
        </Callout>
      ))}

      {viewModel.alerts.map((alert) => (
        <Callout key={alert.message} title={alert.title} color={alert.color}>
          {alert.message}
        </Callout>
      ))}

      <FunnelPaceTable
        selectedQuarter={viewModel.selectedQuarter}
        rows={viewModel.paceRows}
      />

      <FunnelConversionSections
        rateRows={viewModel.rateRows}
        streamSection={viewModel.conversionStreams}
      />

      {viewModel.sourceStreams ? (
        <FunnelSourceStreamSection streams={viewModel.sourceStreams} />
      ) : null}

      {viewModel.expansion ? (
        <FunnelExpansionSection expansion={viewModel.expansion} />
      ) : null}

      <FunnelQuarterlySummary summary={viewModel.quarterlySummary} />
      <FunnelWaterfalls waterfalls={viewModel.waterfalls} />
      <FunnelArrMix arrMix={viewModel.arrMix} />

      {snapshotMeta ? (
        <p className="text-xs text-slate-400 mt-8 pt-4 border-t border-slate-100">
          Data as of {snapshotMeta.as_of} · Snapshot generated{" "}
          {new Date(snapshotMeta.generated_at).toLocaleString()} · Git{" "}
          {snapshotMeta.git_sha?.slice(0, 7) ?? "--"}
        </p>
      ) : null}
    </div>
  );
}
