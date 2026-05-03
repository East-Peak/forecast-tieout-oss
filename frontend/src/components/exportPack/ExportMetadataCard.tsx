import { Card, Text } from "../ui";
import { SectionHeader } from "../workbook";

interface Props {
  orgProfileName: string;
  generatedAt: string;
  asOf: string;
  selectedPlan: string;
  comparisonScope: string;
  fyPlanTarget: string;
  scenarioEngine: string;
  plannerState: string;
  editedQuarters: string;
  gitSha: string;
  dealCount: string;
  monthsInModel: string;
  actualMonths: string;
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>
        <Text as="span" className="text-xs text-slate-500">{label}</Text>
      </dt>
      <dd>
        <Text as="span" className="text-xs font-mono text-slate-700">{value}</Text>
      </dd>
    </>
  );
}

export function ExportMetadataCard(props: Props) {
  return (
    <Card>
      <SectionHeader title="Snapshot Metadata" />
      <dl className="grid grid-cols-2 gap-x-8 gap-y-3">
        <MetaItem label="Org Profile" value={props.orgProfileName} />
        <MetaItem label="Generated At" value={props.generatedAt} />
        <MetaItem label="As Of" value={props.asOf} />
        <MetaItem label="Selected Plan" value={props.selectedPlan} />
        <MetaItem label="Comparison Scope" value={props.comparisonScope} />
        <MetaItem label="FY Plan Target" value={props.fyPlanTarget} />
        <MetaItem label="Scenario Engine" value={props.scenarioEngine} />
        <MetaItem label="Planner State" value={props.plannerState} />
        <MetaItem label="Edited Quarters" value={props.editedQuarters} />
        <MetaItem label="Git SHA" value={props.gitSha} />
        <MetaItem label="Deal Count" value={props.dealCount} />
        <MetaItem label="Months in Model" value={props.monthsInModel} />
        <MetaItem label="Actual Months" value={props.actualMonths} />
      </dl>
    </Card>
  );
}
