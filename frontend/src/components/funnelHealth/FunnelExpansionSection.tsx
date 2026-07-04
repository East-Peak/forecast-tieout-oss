import {
  Card,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from "../ui";
import { MetricCard, SectionHeader } from "../workbook";
import type { FunnelHealthExpansion } from "../../lib/funnelHealthViewModel";

interface FunnelExpansionSectionProps {
  expansion: FunnelHealthExpansion;
}

export function FunnelExpansionSection({
  expansion,
}: FunnelExpansionSectionProps) {
  return (
    <Card>
      <SectionHeader title={expansion.title} subtitle={expansion.subtitle} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        {expansion.metrics.map((metric) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            value={metric.value}
            note={metric.note}
            className={`p-3 ${metric.tone === "emerald" ? "bg-green-50" : "bg-slate-50"}`}
            valueClassName={metric.tone === "emerald" ? "text-green-700" : undefined}
          />
        ))}
      </div>
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Expansion Source</TableHeaderCell>
            <TableHeaderCell className="text-right">ARR</TableHeaderCell>
            <TableHeaderCell className="text-right">% of Total</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {expansion.rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell className="font-medium text-sm">{row.label}</TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.arr}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {row.share}
              </TableCell>
            </TableRow>
          ))}
          <TableRow className="border-t-2 border-slate-300">
            <TableCell className="font-semibold text-sm">Total</TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              {expansion.totalArr}
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold">
              100%
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Card>
  );
}
