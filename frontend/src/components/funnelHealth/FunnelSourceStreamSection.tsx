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
import type { FunnelHealthSourceStreams } from "../../lib/funnelHealthViewModel";

interface FunnelSourceStreamSectionProps {
  streams: FunnelHealthSourceStreams;
}

export function FunnelSourceStreamSection({
  streams,
}: FunnelSourceStreamSectionProps) {
  return (
    <Card>
      <SectionHeader
        title={streams.title}
        subtitle={`Pipeline creation by source. Mode: ${streams.mode}.`}
      />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Stream</TableHeaderCell>
            <TableHeaderCell className="text-right">Input / wk</TableHeaderCell>
            <TableHeaderCell className="text-right">S0 / wk</TableHeaderCell>
            <TableHeaderCell className="text-right">S1 / wk</TableHeaderCell>
            <TableHeaderCell className="text-right">S2 / wk</TableHeaderCell>
            <TableHeaderCell className="text-right">Qtr Pipeline</TableHeaderCell>
            {streams.showActualColumns ? (
              <>
                <TableHeaderCell className="text-right">Actual Opps</TableHeaderCell>
                <TableHeaderCell className="text-right">Actual Pipeline</TableHeaderCell>
              </>
            ) : null}
          </TableRow>
        </TableHead>
        <TableBody>
          {streams.rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell className="font-medium text-sm">{row.displayName}</TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.weeklyInput}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.weeklyS0}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.weeklyS1}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.weeklyS2}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.quarterPipeline}
              </TableCell>
              {streams.showActualColumns ? (
                <>
                  <TableCell className="text-right font-mono text-sm">
                    {row.actualOpps}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {row.actualPipeline}
                  </TableCell>
                </>
              ) : null}
            </TableRow>
          ))}
          <TableRow className="border-t-2 border-slate-300">
            <TableCell className="font-semibold text-sm">Total</TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              {streams.total.weeklyInput}
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              {streams.total.weeklyS0}
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              {streams.total.weeklyS1}
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              {streams.total.weeklyS2}
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              {streams.total.quarterPipeline}
            </TableCell>
            {streams.showActualColumns ? (
              <>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {streams.total.actualOpps}
                </TableCell>
                <TableCell className="text-right font-mono text-sm font-semibold">
                  {streams.total.actualPipeline}
                </TableCell>
              </>
            ) : null}
          </TableRow>
        </TableBody>
      </Table>
    </Card>
  );
}
