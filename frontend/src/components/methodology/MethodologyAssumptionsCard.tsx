import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../ui";

import type { MethodologyAssumptionRow } from "../../lib/methodology";
import { SectionHeader } from "../workbook";

export function MethodologyAssumptionsCard({
  rows,
}: {
  rows: MethodologyAssumptionRow[];
}) {
  return (
    <Card>
      <SectionHeader title="Model Assumptions" />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Parameter</TableHeaderCell>
            <TableHeaderCell className="text-right">Value</TableHeaderCell>
            <TableHeaderCell>Source</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={`${row.label}-${row.source}`}>
              <TableCell>{row.label}</TableCell>
              <TableCell className="text-right font-mono text-blue-600">{row.value}</TableCell>
              <TableCell className="text-slate-600">{row.source}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
