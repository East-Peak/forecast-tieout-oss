import { Fragment, useState } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { B, ROWS } from "./bindings";

/** The gap by quarter, a row per quarter that has a target; a row opens to show its 80% range. */
export function QuarterTable() {
  const { files } = useBindingContext();
  const quarters = files.report.gap.quarters;
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const toggle = (i: number) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <Card>
      <SectionHeader
        title="The gap, quarter by quarter"
        subtitle="Gap is target less expected: a positive gap is a shortfall, a negative one is ahead. Open a row for the range of the expected figure."
      />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Quarter</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
            <TableHeaderCell className="text-right">Target</TableHeaderCell>
            <TableHeaderCell className="text-right">Booked</TableHeaderCell>
            <TableHeaderCell className="text-right">Forecast</TableHeaderCell>
            <TableHeaderCell className="text-right">Expected</TableHeaderCell>
            <TableHeaderCell className="text-right">Gap</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {quarters.map((_, i) => {
            const row = `${ROWS.quarter}/${i}`;
            const expanded = open.has(i);
            return (
              <Fragment key={i}>
                <TableRow data-testid="quarter-row">
                  <TableCell className="whitespace-nowrap font-medium">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-label="Show the range of this quarter"
                      onClick={() => toggle(i)}
                      className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                    </button>
                    <Bound binding={B.qName} row={row} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    <Bound binding={B.qStatus} row={row} />
                  </TableCell>
                  <TableCell className="text-right"><Bound binding={B.qTarget} row={row} /></TableCell>
                  <TableCell className="text-right"><Bound binding={B.qActual} row={row} /></TableCell>
                  <TableCell className="text-right"><Bound binding={B.qForecast} row={row} /></TableCell>
                  <TableCell className="text-right"><Bound binding={B.qExpected} row={row} /></TableCell>
                  <TableCell className="text-right font-medium"><Bound binding={B.qGap} row={row} /></TableCell>
                </TableRow>
                {expanded ? (
                  <TableRow className="bg-slate-50" data-testid="quarter-detail">
                    <TableCell colSpan={7} className="text-xs text-slate-600">
                      80% range of the expected figure: <Bound binding={B.qRange80Low} row={row} /> to{" "}
                      <Bound binding={B.qRange80High} row={row} />
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}
