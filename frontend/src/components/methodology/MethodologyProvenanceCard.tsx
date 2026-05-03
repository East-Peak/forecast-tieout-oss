import { Card, Text } from "../ui";

import type { MethodologyProvenanceItem } from "../../lib/methodology";
import { SectionHeader } from "../workbook";

function ProvenanceItem({ label, value }: MethodologyProvenanceItem) {
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

export function MethodologyProvenanceCard({
  items,
}: {
  items: MethodologyProvenanceItem[];
}) {
  return (
    <Card>
      <SectionHeader title="Data Provenance" />
      <dl className="grid grid-cols-2 gap-x-8 gap-y-2">
        {items.map((item) => (
          <ProvenanceItem key={item.label} {...item} />
        ))}
      </dl>
    </Card>
  );
}
