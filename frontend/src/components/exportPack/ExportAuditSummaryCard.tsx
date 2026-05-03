import { Card, Text } from "../ui";
import { SectionHeader } from "../workbook";
import type { ExportPackViewModel } from "../../lib/exportPack";
import { AuditStatusBadge } from "../trust";
import { statusLabel } from "../../lib/audit";

function RegisterSection({
  title,
  emptyText,
  rows,
}: {
  title: string;
  emptyText: string;
  rows: Array<{ label: string; source: string; detail: string }>;
}) {
  return (
    <div className="mt-4">
      <Text className="mb-2 text-xs uppercase tracking-wide text-slate-500">{title}</Text>
      {rows.length === 0 ? (
        <Text className="text-sm text-slate-600">{emptyText}</Text>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((row) => (
            <div key={`${row.label}-${row.source}`} className="rounded-lg border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-3">
                <Text className="font-medium text-slate-800">{row.label}</Text>
                <Text className="text-xs text-slate-500">{row.source}</Text>
              </div>
              <Text className="mt-1 text-xs text-slate-600">{row.detail}</Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ExportAuditSummaryCard({ viewModel }: { viewModel: ExportPackViewModel }) {
  const criticalSignals = viewModel.criticalSignals.slice(0, 6);

  return (
    <Card>
      <SectionHeader
        title="Audit Summary"
        subtitle="High-signal readiness checks and critical live-input sources from the saved snapshot."
      />
      <AuditStatusBadge
        status={viewModel.overallStatus}
        label="Overall snapshot status"
      />
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <Text className="mb-2 text-xs uppercase tracking-wide text-slate-500">Health Checks</Text>
          <div className="flex flex-col gap-2">
            {viewModel.healthRows.map((row) => (
              <div key={row.label} className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <Text className="font-medium text-slate-800">{row.label}</Text>
                  <Text className="text-xs text-slate-500">{statusLabel(row.status)}</Text>
                </div>
                <Text className="mt-1 text-xs text-slate-600">{row.message}</Text>
              </div>
            ))}
          </div>
        </div>
        <div>
          <Text className="mb-2 text-xs uppercase tracking-wide text-slate-500">Critical Sources</Text>
          <div className="flex flex-col gap-2">
            {criticalSignals.map((row) => (
              <div key={row.label} className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <Text className="font-medium text-slate-800">{row.label}</Text>
                  <Text className="text-xs text-slate-500">{row.source}</Text>
                </div>
                <Text className="mt-1 text-xs text-slate-600">
                  Sample: {row.sample} · Method: {row.method}
                </Text>
              </div>
            ))}
          </div>
        </div>
      </div>
      <RegisterSection
        title="Finance-Critical Exceptions"
        emptyText="No finance-critical signals in the current snapshot are using config fallbacks."
        rows={viewModel.fallbackExceptions}
      />
      <RegisterSection
        title="Accepted Scope Exclusions"
        emptyText="No accepted scope exclusions are recorded for the current snapshot."
        rows={viewModel.acceptedScopeExclusions}
      />
      <RegisterSection
        title="Inactive Fallback Debt"
        emptyText="No inactive fallback debt is recorded for the current snapshot."
        rows={viewModel.inactiveFallbackDebt}
      />
    </Card>
  );
}
