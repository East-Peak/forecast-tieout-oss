import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Text,
} from "../ui";

import type { AuditException } from "../../lib/audit";
import { SectionHeader } from "../workbook";

interface Props {
  title: string;
  subtitle: string;
  rows: AuditException[];
  emptyText: string;
  middleHeader: string;
  emptyTone?: "default" | "positive";
}

export function RegisterTableCard({
  title,
  subtitle,
  rows,
  emptyText,
  middleHeader,
  emptyTone = "default",
}: Props) {
  return (
    <Card>
      <SectionHeader title={title} subtitle={subtitle} />
      {rows.length === 0 ? (
        <Text className={emptyTone === "positive" ? "text-sm text-emerald-700" : "text-sm text-slate-600"}>
          {emptyText}
        </Text>
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Signal</TableHeaderCell>
              <TableHeaderCell>{middleHeader}</TableHeaderCell>
              <TableHeaderCell>Detail</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={`${row.label}-${row.source}`}>
                <TableCell>{row.label}</TableCell>
                <TableCell>{row.source}</TableCell>
                <TableCell className="text-xs text-slate-600">{row.detail}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
