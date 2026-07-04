import { BadgeDelta, Card, Metric, Text } from "../ui";
import type { DeltaType } from "../ui";

export interface MetricCardProps {
  label: string;
  value: string;
  delta?: string;
  deltaType?: DeltaType;
  note?: string;
  className?: string;
  valueClassName?: string;
  children?: React.ReactNode;
  frame?: boolean;
}

export function MetricCard({
  label,
  value,
  delta,
  deltaType = "unchanged",
  note,
  className,
  valueClassName,
  children,
  frame = true,
}: MetricCardProps) {
  const content = (
    <>
      <Text className="text-xs font-medium text-slate-500" data-testid="metric-label">
        {label}
      </Text>
      <Metric className={`mt-1 text-2xl ${valueClassName ?? ""}`} data-testid="metric-value">
        {value}
      </Metric>
      {delta ? (
        <BadgeDelta deltaType={deltaType} className="mt-2">
          {delta}
        </BadgeDelta>
      ) : null}
      {note ? <Text className="mt-1 text-[11px] leading-tight text-slate-400">{note}</Text> : null}
      {children}
    </>
  );

  if (!frame) {
    return (
      <div className={className} data-testid="metric-card">
        {content}
      </div>
    );
  }

  return (
    <Card className={className} data-testid="metric-card">
      {content}
    </Card>
  );
}
