import { Fragment, useState } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK_LG } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/**
 * The gap, quarter by quarter, for the selected scenario. A closed quarter says "closed" where a
 * forecast would be (nothing is left to forecast) and has no range; an open quarter opens to show its range.
 */
export function QuarterTable({ planned }: { planned: boolean }) {
  const { files } = useBindingContext();
  const base = planned ? ROWS.quarterPlanned : ROWS.quarterSigned;
  const quarters = planned && files.report.plan && "items" in files.report.plan ? files.report.plan.with_plan_quarters : files.report.gap.quarters;
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
        subtitle="Gap is target less expected: positive is a shortfall, negative is ahead. Open a quarter for its range."
      />
      <Table className={STACK_LG.table}>
        <TableHead className={STACK_LG.head}>
          <TableRow>
            <TableHeaderCell>Quarter</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
            <TableHeaderCell className="text-right">Target</TableHeaderCell>
            <TableHeaderCell className="text-right">Booked</TableHeaderCell>
            <TableHeaderCell className="text-right">Forecast</TableHeaderCell>
            <TableHeaderCell className="text-right">Expected</TableHeaderCell>
            <TableHeaderCell className="text-right">Gap</TableHeaderCell>
            {planned ? <TableHeaderCell className="text-right">Gap as signed</TableHeaderCell> : null}
          </TableRow>
        </TableHead>
        <TableBody className={STACK_LG.body}>
          {quarters.map((q, i) => {
            const row = `${base}/${i}`;
            const closed = q.status === "closed";
            const expanded = open.has(i);
            return (
              <Fragment key={i}>
                <TableRow className={STACK_LG.row} data-testid="quarter-row">
                  <TableCell className={`${STACK_LG.title} whitespace-nowrap`}>
                    {closed ? (
                      <span className="mr-2 inline-block h-5 w-5" aria-hidden="true" />
                    ) : (
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-label="Show the range of this quarter"
                        onClick={() => toggle(i)}
                        className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      >
                        <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                      </button>
                    )}
                    <Bound binding={B.qName} row={row} />
                  </TableCell>
                  <TableCell className={`${STACK_LG.cell} whitespace-nowrap lg:text-left`} data-label="Status"><Bound binding={B.qStatus} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Target"><Bound binding={B.qTarget} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Booked"><Bound binding={B.qActual} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Forecast">
                    {closed ? <span data-state="closed" className="text-slate-500">closed</span> : <Bound binding={B.qForecast} row={row} />}
                  </TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Expected"><Bound binding={B.qExpected} row={row} /></TableCell>
                  <TableCell className={`${STACK_LG.cell} font-medium`} data-label="Gap"><Bound binding={B.qGap} row={row} /></TableCell>
                  {planned ? (
                    <TableCell className={STACK_LG.cell} data-label="Gap as signed">
                      <Bound binding={B.qSignedGap} row={`${ROWS.signedQuarters}/${i}`} />
                    </TableCell>
                  ) : null}
                </TableRow>
                {expanded && !closed ? (
                  <TableRow className="block bg-slate-50 lg:table-row" data-testid="quarter-detail">
                    <TableCell colSpan={planned ? 8 : 7} className="block px-3 py-2 text-xs text-slate-600 lg:table-cell">
                      80% range of the expected figure: <Bound binding={B.qRange80Low} row={row} /> to{" "}
                      <Bound binding={B.qRange80High} row={row} />
                      {planned || !("range80_label" in q) ? null : (
                        <>
                          {" "}
                          &middot; <Bound binding={B.qRangeLabel} row={row} />
                        </>
                      )}
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
