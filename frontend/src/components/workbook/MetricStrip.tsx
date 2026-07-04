import type { DeltaType } from "../ui";
import { getVerdictTint } from "../../lib/verdictTint";
import { MetricCard } from "./MetricCard";

export interface MetricItem {
  label: string;
  value: string;
  delta?: string;
  deltaType?: DeltaType;
  note?: string;
  verdictValue?: number | null;
}

interface Props {
  metrics: MetricItem[];
}

export function MetricStrip({ metrics }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
      {metrics.map((m, i) => {
        const verdict =
          m.verdictValue === undefined ? null : getVerdictTint(m.verdictValue);
        return (
          <MetricCard
            key={i}
            label={m.label}
            value={m.value}
            delta={m.delta}
            deltaType={m.deltaType}
            note={m.note}
            className={`p-4 ${verdict?.metricClassName ?? ""}`}
            valueClassName={verdict?.cellClassName}
          />
        );
      })}
    </div>
  );
}
