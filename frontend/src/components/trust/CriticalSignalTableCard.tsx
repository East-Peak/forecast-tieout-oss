import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../ui";

import type { AuditSignal } from "../../lib/audit";
import { SectionHeader } from "../workbook";

interface Props {
  title: string;
  subtitle: string;
  rows: AuditSignal[];
}

export function CriticalSignalTableCard({ title, subtitle, rows }: Props) {
  return (
    <Card>
      <SectionHeader title={title} subtitle={subtitle} />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Signal</TableHeaderCell>
            <TableHeaderCell>Active Source</TableHeaderCell>
            <TableHeaderCell>Sample</TableHeaderCell>
            <TableHeaderCell>Method</TableHeaderCell>
            <TableHeaderCell>Notes</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell>{row.label}</TableCell>
              <TableCell>{row.source}</TableCell>
              <TableCell className="font-mono text-xs text-slate-600">{row.sample}</TableCell>
              <TableCell className="text-xs text-slate-600">{row.method}</TableCell>
              <TableCell className="text-xs text-slate-600">{row.note}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
