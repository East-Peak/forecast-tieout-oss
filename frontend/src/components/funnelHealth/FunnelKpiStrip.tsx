import { MetricStrip } from "../workbook";
import type { FunnelHealthMetric } from "../../lib/funnelHealthViewModel";

interface FunnelKpiStripProps {
  metrics: FunnelHealthMetric[];
}

export function FunnelKpiStrip({ metrics }: FunnelKpiStripProps) {
  return <MetricStrip metrics={metrics} />;
}
