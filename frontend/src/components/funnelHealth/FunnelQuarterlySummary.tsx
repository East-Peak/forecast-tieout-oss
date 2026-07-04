import {
  Card,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from "../ui";
import { SectionHeader } from "../workbook";
import type { FunnelHealthQuarterlySummary } from "../../lib/funnelHealthViewModel";

interface FunnelQuarterlySummaryProps {
  summary: FunnelHealthQuarterlySummary;
}

export function FunnelQuarterlySummary({
  summary,
}: FunnelQuarterlySummaryProps) {
  return (
    <Card>
      <SectionHeader
        title="Quarterly Funnel Summary"
        subtitle="Projected bookings across all quarters."
      />
      <Table>
        <TableHead>
          <TableRow>
            {summary.headers.map((header, index) => (
              <TableHeaderCell
                key={header}
                className={index === 0 ? undefined : "text-right"}
              >
                {header}
              </TableHeaderCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {summary.rows.map((row) => (
            <TableRow
              key={row.quarter}
              className={row.selected ? "bg-blue-50/50" : ""}
            >
              <TableCell className={row.selected ? "font-semibold" : ""}>
                {row.quarter}
              </TableCell>
              <TableCell className="text-right">{row.bookings}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
