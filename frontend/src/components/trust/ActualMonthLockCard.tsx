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

import type { AuditMonthLockRow } from "../../lib/audit";
import { statusColor, statusLabel } from "../../lib/audit";
import { formatMoney, formatMonthLabel } from "../../lib/format";
import { SectionHeader } from "../workbook";

export function ActualMonthLockCard({ rows }: { rows: AuditMonthLockRow[] }) {
  return (
    <Card>
      <SectionHeader
        title="Actual Month Lock Check"
        subtitle="Confirmed months should show no projected future wins and total expected should match actual inventory wins."
      />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Month</TableHeaderCell>
            <TableHeaderCell className="text-right">Inventory Wins</TableHeaderCell>
            <TableHeaderCell className="text-right">Total Expected</TableHeaderCell>
            <TableHeaderCell className="text-right">Future Wins</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
            <TableHeaderCell>Message</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.month}>
              <TableCell>{formatMonthLabel(row.month)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.inventoryWins)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.totalExpected)}</TableCell>
              <TableCell className="text-right">{formatMoney(row.futureWins)}</TableCell>
              <TableCell>
                <Badge color={statusColor(row.status)}>{statusLabel(row.status)}</Badge>
              </TableCell>
              <TableCell className="text-xs text-slate-600">{row.message}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
