import {
  Card,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from "../ui";
import { ProseNote, SectionHeader } from "../workbook";
import type {
  FunnelHealthConversionStreamSection,
  FunnelHealthRateRow,
} from "../../lib/funnelHealthViewModel";

interface FunnelConversionSectionsProps {
  rateRows: FunnelHealthRateRow[];
  streamSection: FunnelHealthConversionStreamSection;
}

export function FunnelConversionSections({
  rateRows,
  streamSection,
}: FunnelConversionSectionsProps) {
  return (
    <>
      <Card>
        <SectionHeader
          title="Conversion Rate Details"
          subtitle="Observed cohort rates use all-inclusive methodology: Won / (Won + Lost + Open). Rows without observed cohort coverage remain explicit config assumptions."
        />
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Transition</TableHeaderCell>
              <TableHeaderCell className="text-right">Rate</TableHeaderCell>
              <TableHeaderCell>Source</TableHeaderCell>
              <TableHeaderCell className="text-right">Sample Size</TableHeaderCell>
              <TableHeaderCell>Methodology</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rateRows.map((row) => (
              <TableRow key={row.transition}>
                <TableCell className="font-mono text-sm">
                  {row.transition}
                </TableCell>
                <TableCell className="text-right font-medium">
                  {row.rate}
                </TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sourceBadgeClass(row.sourceKey)}`}
                  >
                    {row.source}
                  </span>
                </TableCell>
                <TableCell className="text-right">{row.sampleSize}</TableCell>
                <TableCell className="text-xs text-slate-500">
                  {row.methodology}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <ProseNote>
        Cohort-based observed rates use all-inclusive methodology (Won / All
        including Open), which captures zombie pipeline. Early-funnel and PLG
        rows may still be registry or static assumptions when no compatible
        observed cohort methodology is available in the snapshot.
      </ProseNote>

      {streamSection.hasConversionRates ? (
        <Card>
          <SectionHeader
            title={streamSection.title}
            subtitle={streamSection.subtitle}
          />
          {streamSection.columns.length > 0 ? (
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Transition</TableHeaderCell>
                  {streamSection.columns.map((column) => (
                    <TableHeaderCell key={column.key} className="text-right">
                      {column.label}
                    </TableHeaderCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {streamSection.rows.map((row) => (
                  <TableRow key={row.transition}>
                    <TableCell className="font-mono text-sm">
                      {row.transition}
                    </TableCell>
                    {row.cells.map((cell) => (
                      <TableCell key={cell.columnKey} className="text-right">
                        <span className="font-medium">{cell.rate}</span>
                        {cell.sampleSize ? (
                          <span className="text-xs text-slate-400 ml-1">
                            {cell.sampleSize}
                          </span>
                        ) : null}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-sm text-slate-500">
                Stream-specific conversion rates are not available for this
                quarter. The model is using blended quarter rates instead.
              </p>
            </div>
          )}
        </Card>
      ) : null}
    </>
  );
}

function sourceBadgeClass(source: string): string {
  if (source === "blended_cohort") return "bg-blue-50 text-blue-700";
  if (source === "observed") return "bg-emerald-50 text-emerald-700";
  if (source === "warehouse" || source === "ProfileBackend") {
    return "bg-purple-50 text-purple-700";
  }
  if (source === "registry") return "bg-amber-50 text-amber-700";
  return "bg-slate-50 text-slate-600";
}
