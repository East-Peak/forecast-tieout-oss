import { PlanTimingSemanticsCard } from "../components/plans/PlanTimingSemanticsCard";
import { buildAuditReadinessViewModel } from "../lib/auditReadiness";
import { MetricStrip, ProseNote, SectionHeader } from "../components/workbook";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import {
  ActualMonthLockCard,
  AuditHealthTableCard,
  CriticalSignalTableCard,
  QuarterTieoutCard,
  RegisterTableCard,
  SnapshotFooter,
} from "../components/trust";

export default function AuditReadiness() {
  const { snapshot, selectedOrgProfile, selectedPlan } = usePlanningSessionContext();
  const viewModel = buildAuditReadinessViewModel(snapshot, selectedOrgProfile, selectedPlan);

  return (
    <div className="flex max-w-6xl flex-col gap-8">
      <div>
        <SectionHeader
          title="Finance Audit Readiness"
          subtitle="Canonical audit surface for the saved snapshot: health, tie-out, provenance, and explicit fallback exceptions."
        />
        <ProseNote>
          This tab is the finance-review surface for the current artifact. It is designed to answer
          three questions quickly: whether the app pages tie out, whether actual months are locked,
          and which live systems are feeding the forecast versus any remaining fallback paths.
        </ProseNote>
        {viewModel.connectorPolicyNotes.map((note) => (
          <ProseNote key={note}>{note}</ProseNote>
        ))}
      </div>

      <MetricStrip metrics={viewModel.topMetrics} />
      <PlanTimingSemanticsCard semantics={viewModel.planTimingSemantics} />

      <AuditHealthTableCard
        title="Health Checks"
        subtitle="Snapshot freshness, bookings reconciliation, close timing, and target alignment from the runtime health block."
        rows={viewModel.healthRows}
      />
      <QuarterTieoutCard rows={viewModel.quarterTieoutRows} />
      <ActualMonthLockCard rows={viewModel.monthLockRows} />
      <CriticalSignalTableCard
        title="Critical Signal Ledger"
        subtitle="Active source, sample, and method for the inputs that materially drive the saved forecast."
        rows={viewModel.criticalSignals}
      />
      <RegisterTableCard
        title="Finance-Critical Exceptions"
        subtitle="Only active finance-facing signals still using config-like paths remain here."
        rows={viewModel.fallbackExceptions}
        emptyText="No finance-critical exceptions are recorded for the current snapshot."
        middleHeader="Source"
        emptyTone="positive"
      />
      <RegisterTableCard
        title="Accepted Scope Exclusions"
        subtitle="Explicitly accepted config-backed areas that are outside the current finance-critical motion."
        rows={viewModel.acceptedScopeExclusions}
        emptyText="No accepted scope exclusions are recorded for the current snapshot."
        middleHeader="Source"
      />
      <RegisterTableCard
        title="Inactive Fallback Debt"
        subtitle="Non-active fallback paths that should still be refactored or recalibrated, but are not driving the live forecast."
        rows={viewModel.inactiveFallbackDebt}
        emptyText="No inactive fallback debt is recorded for the current snapshot."
        middleHeader="Type"
      />

      <SnapshotFooter snapshot={snapshot} />
    </div>
  );
}
