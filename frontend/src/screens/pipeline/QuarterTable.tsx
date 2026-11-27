import { Fragment, useState } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { Badge, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/** The requirement, quarter by quarter, and the plain sentences for why a quarter is too late. A quarter opens to the team's record. */
export function QuarterTable() {
  const ctx = useBindingContext();
  const required = ctx.files.report.required_pipeline;
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  if ("unavailable" in required) return null;
  const toggle = (i: number) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  const requiredBinding = (outcome: string): Binding =>
    outcome === "feasible" ? B.qRequired : outcome === "already covered" ? B.qRequiredCovered : B.qRequiredNone;

  return (
    <Card>
      <SectionHeader
        title="Required against expected, quarter by quarter"
        subtitle="The extra pipeline that must be created, spread evenly from tomorrow to the quarter's end, so that the quarter meets its target. Yield is the cents of each created dollar that book inside the quarter."
      />
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Quarter</TableHeaderCell>
            <TableHeaderCell className="text-right">Target</TableHeaderCell>
            <TableHeaderCell className="text-right">Booked so far</TableHeaderCell>
            <TableHeaderCell className="text-right">Without new pipeline</TableHeaderCell>
            <TableHeaderCell className="text-right">Extra required</TableHeaderCell>
            <TableHeaderCell className="text-right">Expected to be created</TableHeaderCell>
            <TableHeaderCell className="text-right">Yield per dollar</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {required.quarters.map((q, i) => {
            const row = `${ROWS.quarters}/${i}`;
            const expanded = open.has(i);
            return (
              <Fragment key={i}>
                <TableRow className={STACK.row} data-testid="requirement-row">
                  <TableCell className={`${STACK.title} sm:whitespace-nowrap`}>
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-label="Show the team's record for this quarter"
                      onClick={() => toggle(i)}
                      className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                    </button>
                    <Bound binding={B.qName} row={row} />
                    {q.in_fiscal_year ? null : <span className="ml-1 text-xs font-normal text-slate-500">(next fiscal year)</span>}
                    <Badge size="xs" color="slate" className="ml-2 align-middle"><Bound binding={B.qStatus} row={row} /></Badge>
                    <div className="mt-0.5 text-xs font-normal text-slate-600 sm:whitespace-normal"><Bound binding={B.qHeadline} row={row} /></div>
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="Target"><Bound binding={B.qTarget} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Booked so far"><Bound binding={B.qActual} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Without new pipeline"><Bound binding={B.qWithout} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="Extra required"><Bound binding={requiredBinding(q.outcome)} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Expected to be created"><Bound binding={B.qExpected} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Yield per dollar"><Bound binding={B.qYield} row={row} /></TableCell>
                </TableRow>
                <TableRow className="block border-b border-slate-100 pb-2 sm:table-row" data-testid="requirement-note">
                  <TableCell colSpan={7} className="block px-0 pb-2 pt-0 text-xs text-slate-600 sm:table-cell sm:px-3">
                    <Bound binding={B.qSurplus} row={row} />
                    {q.too_late.applies ? (
                      <div className="mt-2 rounded-ft border border-amber-200 bg-amber-50/70 px-3 py-2 text-amber-900" data-testid="too-late">
                        <div className="font-semibold"><Bound binding={B.lateLabel} row={row} /></div>
                        <ul className="mt-1 list-disc space-y-0.5 pl-5">
                          {q.too_late.reasons.map((_, j) => (
                            <li key={j}><Bound binding={B.lateReason} row={`${row}/too_late/reasons/${j}`} /></li>
                          ))}
                          {q.too_late.diagnostics.map((_, j) => (
                            <li key={`d${j}`} className="text-amber-800"><Bound binding={B.lateDiagnostic} row={`${row}/too_late/diagnostics/${j}`} /></li>
                          ))}
                        </ul>
                        {q.too_late.open_pipeline !== null ? (
                          <p className="mt-1 text-amber-800"><Bound binding={B.lateOpen} row={row} /></p>
                        ) : null}
                      </div>
                    ) : null}
                  </TableCell>
                </TableRow>
                {expanded ? (
                  <TableRow className="block bg-slate-50 sm:table-row" data-testid="requirement-detail">
                    <TableCell colSpan={7} className="block px-3 py-2 text-xs leading-5 text-slate-600 sm:table-cell">
                      Everything created in the span: <Bound binding={B.qTotal} row={row} />: what the model expects, what earlier quarters were
                      assigned (<Bound binding={B.qEarlier} row={row} />) and this quarter's own requirement. The cap left before this
                      quarter: <Bound binding={B.qCapLeft} row={row} />.
                      <br />
                      Per day: <Bound binding={B.qPerDay} row={row} />, <Bound binding={B.qPerDayVs} row={row} /> the team's best. Per ramped AE-month (
                      <Bound binding={B.qRamped} row={row} /> in the span): <Bound binding={B.qPerAe} row={row} />, <Bound binding={B.qPerAeVs} row={row} /> the
                      team's best{q.per_ramped_ae_month.decides ? " (this comparison decides)" : " (shown as a diagnostic only)"}.
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
