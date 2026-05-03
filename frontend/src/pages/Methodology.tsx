import { PlanTimingSemanticsCard } from "../components/plans/PlanTimingSemanticsCard";
import { MethodologyPrincipleList } from "../components/methodology/MethodologyPrincipleList";
import { MethodologyAssumptionsCard } from "../components/methodology/MethodologyAssumptionsCard";
import {
  MethodologyAuditReadinessCard,
  MethodologyCriticalSignalsCard,
  MethodologyFallbackCard,
} from "../components/methodology/MethodologyAuditCards";
import { MethodologyNarrativeCard } from "../components/methodology/MethodologyNarrativeCard";
import { MethodologyProvenanceCard } from "../components/methodology/MethodologyProvenanceCard";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { SnapshotFooter } from "../components/trust";
import { buildMethodologyViewModel } from "../lib/methodology";

export default function Methodology() {
  const { snapshot, selectedOrgProfile, selectedPlan } =
    usePlanningSessionContext();
  const viewModel = buildMethodologyViewModel(
    snapshot,
    selectedOrgProfile,
    "Frontend local adapter (baseline)",
    selectedPlan,
  );

  return (
    <div className="flex max-w-5xl flex-col gap-8">
      <MethodologyNarrativeCard notes={viewModel.narrativeNotes} />
      <PlanTimingSemanticsCard semantics={viewModel.planTimingSemantics} />
      <MethodologyAuditReadinessCard
        overallStatus={viewModel.overallStatus}
        asOf={snapshot.as_of}
        healthRows={viewModel.healthRows}
        decaySourceSummary={viewModel.decaySourceSummary}
      />
      <MethodologyCriticalSignalsCard signals={viewModel.criticalSignals} />
      <MethodologyFallbackCard rows={viewModel.fallbackExceptions} />
      <MethodologyAssumptionsCard rows={viewModel.assumptions} />
      <MethodologyPrincipleList rows={viewModel.principles} />
      <MethodologyProvenanceCard items={viewModel.provenanceItems} />

      <SnapshotFooter snapshot={snapshot} />
    </div>
  );
}
