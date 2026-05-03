import { BadgeDelta, Card, Metric, Text } from "../ui";
import type { DeltaType } from "../ui";

export interface MetricItem {
  label: string;
  value: string;
  delta?: string;
  deltaType?: DeltaType;
}

interface Props {
  metrics: MetricItem[];
}

export function MetricStrip({ metrics }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
      {metrics.map((m, i) => (
        <Card key={i} className="p-4">
          <Text>{m.label}</Text>
          <Metric className="mt-1">{m.value}</Metric>
          {m.delta && (
            <BadgeDelta
              deltaType={m.deltaType ?? "unchanged"}
              className="mt-2"
            >
              {m.delta}
            </BadgeDelta>
          )}
        </Card>
      ))}
    </div>
  );
}
