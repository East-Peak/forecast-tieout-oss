import { Badge } from "../ui";
import { getDataBasisBadge } from "../../lib/dataBasisBadge";

interface DataBasisBadgeProps {
  actualValue: number | null | undefined;
}

export function DataBasisBadge({ actualValue }: DataBasisBadgeProps) {
  const badge = getDataBasisBadge(actualValue);
  return (
    <Badge
      color={badge.tone === "actualProjected" ? "green" : "slate"}
      size="xs"
      className="font-normal"
    >
      {badge.label}
    </Badge>
  );
}
