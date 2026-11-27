import { Fragment } from "react";
import { Bound } from "../../binding/Bound";
import { Badge, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import type { TieoutReport } from "../../generated/report";
import { CHAIN, WS, WS_ROWS } from "./worksheetBindings";

type Sheet = Exclude<TieoutReport["worksheet"], { unavailable: string }>;

/**
 * Top-down against bottom-up, as signed: for each remaining quarter, what the target needs against what the roster as
 * signed is expected to give, in bookings, in created pipeline and in created pipeline per ramped AE-month, with the
 * timing constraint in words. It reads the roster as signed whatever plan is in force, and says so at its head.
 */
export function Chain({ sheet }: { sheet: Sheet }) {
  const { chain } = sheet;
  return (
    <Card className="p-4 sm:p-5" data-testid="chain">
      <SectionHeader title="Top-down against bottom-up, as signed" subtitle={undefined} />
      <p className="-mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-700" data-testid="chain-basis">
        <Badge color="amber" size="xs">as signed</Badge>
        <span><Bound binding={WS.chainNote} /></span>
      </p>
      {chain.unavailable !== null ? (
        <p className="mt-3 text-xs text-slate-700"><Bound binding={WS.chainUnavailable} /></p>
      ) : (
        <Table className={`${STACK.table} mt-3`} data-testid="chain-table">
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Quarter and measure</TableHeaderCell>
              <TableHeaderCell className="text-right">Required</TableHeaderCell>
              <TableHeaderCell className="text-right">Expected</TableHeaderCell>
              <TableHeaderCell>What it says</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {chain.quarters.map((q, i) => {
              const path = `${WS_ROWS.chain}/${i}`;
              return (
                <Fragment key={q.quarter}>
                  <TableRow className={`${STACK.row} bg-slate-50`} data-testid="chain-quarter">
                    <TableCell colSpan={4} className="block px-3 py-2 text-sm font-semibold text-ft-brand sm:table-cell">
                      <Bound binding={CHAIN.quarter} row={path} /> <span className="font-normal text-slate-500">(<Bound binding={CHAIN.status} row={path} />)</span>
                    </TableCell>
                  </TableRow>
                  <TableRow className={STACK.row} data-testid="chain-row" data-measure="bookings">
                    <TableCell className={STACK.title}>Bookings</TableCell>
                    <TableCell className={STACK.cell} data-label="Required"><Bound binding={CHAIN.bookingsTarget} row={path} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Expected"><Bound binding={CHAIN.bookingsExpected} row={path} /></TableCell>
                    <TableCell className={`${STACK.cell} text-xs sm:text-left`} data-label="What it says">
                      Gap to target <Bound binding={CHAIN.bookingsGap} row={path} />
                    </TableCell>
                  </TableRow>
                  <TableRow className={STACK.row} data-testid="chain-row" data-measure="created-pipeline">
                    <TableCell className={STACK.title}>Created pipeline</TableCell>
                    <TableCell className={STACK.cell} data-label="Required"><Bound binding={CHAIN.pipelineRequired} row={path} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Expected"><Bound binding={CHAIN.pipelineExpected} row={path} /></TableCell>
                    <TableCell className={`${STACK.cell} text-xs sm:text-left`} data-label="What it says"><Bound binding={CHAIN.pipelineHeadline} row={path} /></TableCell>
                  </TableRow>
                  <TableRow className={STACK.row} data-testid="chain-row" data-measure="per-ramped-ae-month">
                    <TableCell className={STACK.title}>Created pipeline per ramped AE-month</TableCell>
                    <TableCell className={STACK.cell} data-label="Required"><Bound binding={CHAIN.perRequired} row={path} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Expected"><Bound binding={CHAIN.perExpected} row={path} /></TableCell>
                    <TableCell className={`${STACK.cell} text-xs sm:text-left`} data-label="What it says">
                      {q.per_ramped_ae_month.decides.value ? "Decides the timing check." : "Shown as a diagnostic: it does not decide the timing check for this company."}
                    </TableCell>
                  </TableRow>
                  <TableRow className={STACK.row} data-testid="chain-timing">
                    <TableCell colSpan={4} className="block px-3 py-2 text-xs text-slate-700 sm:table-cell">
                      <span className="font-semibold text-slate-800">Timing: </span>
                      {q.timing.applies.value ? (
                        <>
                          <Bound binding={CHAIN.timingLabel} row={path} />
                          <ul className="mt-1 list-disc pl-5">
                            {q.timing.reasons.value.map((_, j) => (
                              <li key={j}><Bound binding={CHAIN.timingReason} row={`${path}/timing/reasons/value/${j}`} /></li>
                            ))}
                          </ul>
                        </>
                      ) : (
                        "no timing constraint applies."
                      )}
                    </TableCell>
                  </TableRow>
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
