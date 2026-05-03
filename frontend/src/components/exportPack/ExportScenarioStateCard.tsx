import { Card, Text } from "../ui";
import { SectionHeader } from "../workbook";

interface Props {
  baselineFy: string;
  scenarioFy: string;
  scenarioDelta: string;
  scenarioDeltaPositive: boolean;
  scenarioGapToPlan: string;
  scenarioGapPositive: boolean;
  plannerStateNote: string;
}

export function ExportScenarioStateCard({
  baselineFy,
  scenarioFy,
  scenarioDelta,
  scenarioDeltaPositive,
  scenarioGapToPlan,
  scenarioGapPositive,
  plannerStateNote,
}: Props) {
  return (
    <Card>
      <SectionHeader
        title="Active Scenario State"
        subtitle="The live planner state currently carried by the app session and exported in the scenario CSV."
      />
      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
          <Text className="text-xs uppercase tracking-wide text-slate-500">Baseline FY</Text>
          <Text className="mt-2 text-xl font-semibold text-slate-900">{baselineFy}</Text>
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50/70 p-3">
          <Text className="text-xs uppercase tracking-wide text-blue-700">Scenario FY</Text>
          <Text className="mt-2 text-xl font-semibold text-slate-900">{scenarioFy}</Text>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
          <Text className="text-xs uppercase tracking-wide text-slate-500">Delta Vs Baseline</Text>
          <Text
            className={`mt-2 text-xl font-semibold ${
              scenarioDeltaPositive ? "text-emerald-700" : "text-red-700"
            }`}
          >
            {scenarioDelta}
          </Text>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
          <Text className="text-xs uppercase tracking-wide text-slate-500">Scenario Gap To Plan</Text>
          <Text
            className={`mt-2 text-xl font-semibold ${
              scenarioGapPositive ? "text-emerald-700" : "text-red-700"
            }`}
          >
            {scenarioGapToPlan}
          </Text>
        </div>
      </div>
      <Text className="mt-3 text-xs text-slate-500">{plannerStateNote}</Text>
    </Card>
  );
}
