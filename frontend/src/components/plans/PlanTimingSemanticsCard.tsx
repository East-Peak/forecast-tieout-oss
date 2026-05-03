import type { PlanTimingSemantics } from "../../lib/plans";
import { Card, Text } from "../ui";
import { SectionHeader } from "../workbook";

const TONE_STYLES = {
  slate: "border-slate-200 bg-slate-50/80",
  blue: "border-blue-100 bg-blue-50/70",
  emerald: "border-emerald-100 bg-emerald-50/70",
  amber: "border-amber-100 bg-amber-50/70",
} as const;

interface Props {
  semantics: PlanTimingSemantics;
}

export function PlanTimingSemanticsCard({ semantics }: Props) {
  return (
    <Card>
      <SectionHeader
        title="Plan Timing Semantics"
        subtitle="How the selected plan's comparable view, forward context, and ownership rules should be read relative to the saved forecast math."
        caption={
          semantics.comparisonScopeLabel
            ? `${semantics.selectedPlanName} · ${semantics.comparisonScopeLabel}`
            : semantics.selectedPlanName
        }
      />
      <Text className="mb-4 text-sm text-slate-600">{semantics.overview}</Text>
      <div className="grid gap-3 md:grid-cols-2">
        {semantics.items.map((item) => (
          <div
            key={item.label}
            className={`rounded-lg border p-3 ${TONE_STYLES[item.tone]}`}
          >
            <Text className="text-xs uppercase tracking-wide text-slate-500">{item.label}</Text>
            <Text className="mt-2 text-sm leading-6 text-slate-700">{item.detail}</Text>
          </div>
        ))}
      </div>
    </Card>
  );
}
