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
import type { FunnelHealthPaceRow } from "../../lib/funnelHealthViewModel";

interface FunnelPaceTableProps {
  selectedQuarter: string;
  rows: FunnelHealthPaceRow[];
}

export function FunnelPaceTable({ selectedQuarter, rows }: FunnelPaceTableProps) {
  return (
    <Card>
      <SectionHeader
        title="Weekly Funnel Pace"
        subtitle={`${selectedQuarter}: Top-down plan vs actual/forecast for each funnel stage.`}
      />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Stage</TableHeaderCell>
            <TableHeaderCell className="text-right">Top-Down Plan</TableHeaderCell>
            <TableHeaderCell className="text-right">Actual / Forecast</TableHeaderCell>
            <TableHeaderCell className="text-right">Delta</TableHeaderCell>
            <TableHeaderCell className="text-right">Delta %</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.stage}>
              <TableCell className="font-medium text-sm">{row.stage}</TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.plan}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.actual}
              </TableCell>
              <TableCell
                className={`text-right font-mono text-sm ${deltaToneClass(row.deltaTone)}`}
              >
                {row.delta}
              </TableCell>
              <TableCell
                className={`text-right font-mono text-sm ${deltaToneClass(row.deltaTone)}`}
              >
                {row.deltaPct}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

function deltaToneClass(tone: FunnelHealthPaceRow["deltaTone"]): string {
  if (tone === "positive") return "text-emerald-600";
  if (tone === "negative") return "text-red-600";
  return "";
}
