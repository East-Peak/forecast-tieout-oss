import {
  Badge,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../ui";

import type { AuditQuarterTieoutRow } from "../../lib/audit";
import { statusColor, statusLabel } from "../../lib/audit";
import { formatMoney } from "../../lib/format";
import { SectionHeader } from "../workbook";

export function QuarterTieoutCard({ rows }: { rows: AuditQuarterTieoutRow[] }) {
  return (
    <Card>
      <SectionHeader
        title="Quarter Tie-Out"
        subtitle="Quarterly sales-led trajectory should reconcile across Bookings Bridge, Funnel Health, and Capacity & Headcount."
      />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Quarter</TableHeaderCell>
            <TableHeaderCell className="text-right">Bookings</TableHeaderCell>
            <TableHeaderCell className="text-right">Funnel</TableHeaderCell>
            <TableHeaderCell className="text-right">Capacity</TableHeaderCell>
            <TableHeaderCell className="text-right">Actuals</TableHeaderCell>
            <TableHeaderCell className="text-right">Max Delta</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.quarter}>
              <TableCell>{row.quarter}</TableCell>
              <TableCell className="text-right">{formatMoney(row.bookings)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.funnel)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.capacity)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.actuals)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.maxDelta)}</TableCell>
              <TableCell>
                <Badge color={statusColor(row.status)}>{statusLabel(row.status)}</Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
