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
import { SectionHeader } from "../workbook";
import type { ExportPreviewRow } from "../../lib/exportPack";

interface Props {
  planNote: string | null;
  rows: ExportPreviewRow[];
}

export function ExportCsvPreviewCard({ planNote, rows }: Props) {
  return (
    <Card>
      <SectionHeader title="CSV Preview" caption="First 6 months of the live scenario export" />
      {planNote ? <Text className="mb-3 text-xs text-slate-500">{planNote}</Text> : null}
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Month</TableHeaderCell>
            <TableHeaderCell className="text-right">Inventory Wins</TableHeaderCell>
            <TableHeaderCell className="text-right">Scenario Future</TableHeaderCell>
            <TableHeaderCell className="text-right">Scenario Expected</TableHeaderCell>
            <TableHeaderCell className="text-right">Saved Capped</TableHeaderCell>
            <TableHeaderCell className="text-right">Scenario Capped</TableHeaderCell>
            <TableHeaderCell className="text-right">Plan Ref</TableHeaderCell>
            <TableHeaderCell className="text-right">Baseline AEs</TableHeaderCell>
            <TableHeaderCell className="text-right">Scenario AEs</TableHeaderCell>
            <TableHeaderCell className="text-right">Baseline Capacity</TableHeaderCell>
            <TableHeaderCell className="text-right">Scenario Capacity</TableHeaderCell>
            <TableHeaderCell>Actual</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.month}>
              <TableCell>{row.month}</TableCell>
              <TableCell className="text-right">{row.inventoryWins}</TableCell>
              <TableCell className="text-right">{row.scenarioFutureWins}</TableCell>
              <TableCell className="text-right">{row.scenarioExpected}</TableCell>
              <TableCell className="text-right">{row.baselineCapped}</TableCell>
              <TableCell className="text-right">{row.scenarioCapped}</TableCell>
              <TableCell className="text-right">{row.planReference}</TableCell>
              <TableCell className="text-right">{row.baselineAeCount}</TableCell>
              <TableCell className="text-right">{row.scenarioAeCount}</TableCell>
              <TableCell className="text-right">{row.baselineAeCapacity}</TableCell>
              <TableCell className="text-right">{row.scenarioAeCapacity}</TableCell>
              <TableCell>{row.isActual ? "Yes" : "No"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
