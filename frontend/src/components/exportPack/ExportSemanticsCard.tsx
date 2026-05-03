import { Card, Text } from "../ui";
import { SectionHeader } from "../workbook";

interface Props {
  planNote: string | null;
  orgProfileName: string;
  connectorPolicyNotes: string[];
}

export function ExportSemanticsCard({
  planNote,
  orgProfileName,
  connectorPolicyNotes,
}: Props) {
  return (
    <Card>
      <SectionHeader
        title="Planner / Plan Semantics"
        subtitle="How each export should be interpreted relative to the saved baseline, live planner state, and selected plan reference."
      />
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
          <Text className="text-xs uppercase tracking-wide text-slate-500">Saved Baseline</Text>
          <Text className="mt-2 text-sm text-slate-700">
            The JSON export is the saved snapshot baseline. It does not embed ad hoc Scenario Planner
            overrides.
          </Text>
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50/70 p-3">
          <Text className="text-xs uppercase tracking-wide text-blue-700">Active Scenario CSV</Text>
          <Text className="mt-2 text-sm text-slate-700">
            The monthly CSV carries the live planner scenario alongside the saved baseline so finance
            can inspect the current what-if path against plan month by month.
          </Text>
        </div>
        <div className="rounded-lg border border-red-100 bg-red-50/70 p-3">
          <Text className="text-xs uppercase tracking-wide text-red-700">Selected Plan</Text>
          <Text className="mt-2 text-sm text-slate-700">
            The current plan reference stays separate from both the saved baseline and any active
            scenario overrides.
          </Text>
          {planNote ? <Text className="mt-2 text-xs leading-5 text-slate-600">{planNote}</Text> : null}
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50/70 p-3">
          <Text className="text-xs uppercase tracking-wide text-blue-700">Timing Semantics</Text>
          <Text className="mt-2 text-sm text-slate-700">
            Wins are anchored to `CloseDate`, losses to `Closed At`, and finance-facing pipeline
            creation actuals to first entry into `S2`.
          </Text>
        </div>
        <div className="rounded-lg border border-emerald-100 bg-emerald-50/70 p-3 md:col-span-2">
          <Text className="text-xs uppercase tracking-wide text-emerald-700">
            {orgProfileName} Connector Policy
          </Text>
          <div className="mt-2 space-y-2">
            {connectorPolicyNotes.map((note) => (
              <Text key={note} className="text-sm text-slate-700">
                {note}
              </Text>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
