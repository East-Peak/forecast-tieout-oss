import { Badge, Text } from "../ui";

import { statusColor, statusLabel } from "../../lib/audit";

interface Props {
  status: string;
  label?: string;
  meta?: string | null;
}

export function AuditStatusBadge({ status, label, meta }: Props) {
  return (
    <div className="mb-4 flex items-center gap-3">
      {label ? <Text className="text-sm text-slate-600">{label}</Text> : null}
      <Badge color={statusColor(status)}>{statusLabel(status)}</Badge>
      {meta ? <Text className="text-xs text-slate-500">{meta}</Text> : null}
    </div>
  );
}
