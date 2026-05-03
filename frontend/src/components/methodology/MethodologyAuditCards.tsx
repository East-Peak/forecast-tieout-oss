import type { AuditException, AuditHealthRow, AuditSignal } from "../../lib/audit";
import {
  AuditHealthTableCard,
  CriticalSignalTableCard,
  RegisterTableCard,
} from "../trust";

export function MethodologyAuditReadinessCard({
  overallStatus,
  asOf,
  healthRows,
  decaySourceSummary,
}: {
  overallStatus: string;
  asOf: string;
  healthRows: AuditHealthRow[];
  decaySourceSummary: string | null;
}) {
  return (
    <AuditHealthTableCard
      title="Finance Audit Readiness"
      subtitle="Current saved snapshot status, active runtime health checks, and close-timing provenance."
      rows={healthRows}
      overallStatus={overallStatus}
      overallLabel="Overall snapshot status"
      overallMeta={`Snapshot as of ${asOf}`}
      footnote={decaySourceSummary}
    />
  );
}

export function MethodologyCriticalSignalsCard({ signals }: { signals: AuditSignal[] }) {
  return (
    <CriticalSignalTableCard
      title="Critical Signal Ledger"
      subtitle="Human-readable source, sample, and method for the inputs that drive the saved forecast."
      rows={signals}
    />
  );
}

export function MethodologyFallbackCard({ rows }: { rows: AuditException[] }) {
  return (
    <RegisterTableCard
      title="Fallback Register"
      subtitle="Finance-critical signals still using static/config paths stay listed here. Accepted scope exclusions and inactive fallback debt are tracked on the Audit and Export surfaces."
      rows={rows}
      emptyText="No finance-critical signals in the current snapshot are using config fallbacks."
      middleHeader="Source"
      emptyTone="positive"
    />
  );
}
