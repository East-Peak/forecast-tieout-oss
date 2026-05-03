import {
  Badge,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Text,
} from "../ui";

import type { AuditHealthRow } from "../../lib/audit";
import { statusColor, statusLabel } from "../../lib/audit";
import { SectionHeader } from "../workbook";
import { AuditStatusBadge } from "./AuditStatusBadge";

interface Props {
  title: string;
  subtitle: string;
  rows: AuditHealthRow[];
  overallStatus?: string;
  overallLabel?: string;
  overallMeta?: string | null;
  footnote?: string | null;
}

export function AuditHealthTableCard({
  title,
  subtitle,
  rows,
  overallStatus,
  overallLabel,
  overallMeta,
  footnote,
}: Props) {
  return (
    <Card>
      <SectionHeader title={title} subtitle={subtitle} />
      {overallStatus ? (
        <AuditStatusBadge status={overallStatus} label={overallLabel} meta={overallMeta} />
      ) : null}
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Check</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
            <TableHeaderCell>Message</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell>{row.label}</TableCell>
              <TableCell>
                <Badge color={statusColor(row.status)}>{statusLabel(row.status)}</Badge>
              </TableCell>
              <TableCell className="text-slate-600">{row.message}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {footnote ? <Text className="mt-4 text-xs text-slate-500">{footnote}</Text> : null}
    </Card>
  );
}
