import { Card, Text } from "../ui";

import type { MethodologyPrinciple } from "../../lib/methodology";
import { SectionHeader } from "../workbook";

export function MethodologyPrincipleList({ rows }: { rows: MethodologyPrinciple[] }) {
  return (
    <div>
      <SectionHeader
        title="Modeling Principles"
        subtitle="Key modeling decisions and their rationale."
      />
      <div className="flex flex-col gap-3">
        {rows.map((principle) => (
          <Card key={principle.title} className="p-4">
            <Text className="mb-2 font-semibold text-slate-800">{principle.title}</Text>
            <Text className="text-sm">{principle.summary}</Text>
          </Card>
        ))}
      </div>
    </div>
  );
}
