import { Card } from "../ui";

import { ProseNote, SectionHeader } from "../workbook";

export function MethodologyNarrativeCard({ notes }: { notes: string[] }) {
  return (
    <Card>
      <SectionHeader title="How the Forecast Works" />
      <div className="flex flex-col gap-3">
        {notes.map((note) => (
          <ProseNote key={note.slice(0, 32)}>{note}</ProseNote>
        ))}
      </div>
    </Card>
  );
}
