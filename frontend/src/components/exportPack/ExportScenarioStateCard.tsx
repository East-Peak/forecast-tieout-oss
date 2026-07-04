import { Card, Text } from "../ui";
import { MetricCard, SectionHeader } from "../workbook";

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
        title="Baseline Scenario State"
        subtitle="The exported CSV is built from the saved baseline scenario for the current snapshot."
      />
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard label="Baseline FY" value={baselineFy} className="p-3 bg-slate-50/80" />
        <MetricCard label="Baseline Export FY" value={scenarioFy} className="p-3 border-ft-accent bg-ft-accentSoft" />
        <MetricCard
          label="Delta Vs Baseline"
          value={scenarioDelta}
          className="p-3 bg-slate-50/80"
          valueClassName={scenarioDeltaPositive ? "text-green-700" : "text-red-700"}
        />
        <MetricCard
          label="Baseline Gap To Plan"
          value={scenarioGapToPlan}
          className="p-3 bg-slate-50/80"
          valueClassName={scenarioGapPositive ? "text-green-700" : "text-red-700"}
        />
      </div>
      <Text className="mt-3 text-xs text-slate-500">{plannerStateNote}</Text>
    </Card>
  );
}
