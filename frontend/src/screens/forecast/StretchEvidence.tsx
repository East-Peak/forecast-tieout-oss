import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import { Badge, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { STACK_LG } from "../../components/workbook/stack";
import { ROWS, STRETCH } from "./bindings";

/** The decision's tone is read from the report's own word for it; nothing is computed. */
function toneOf(decision: string): "green" | "amber" | "slate" {
  if (decision === "adopted") return "green";
  if (decision === "not adopted") return "amber";
  return "slate";
}

/**
 * Were the simulated ranges stretched by the model's own past misses? The decision and its reason in
 * the report's words, then, for each tested horizon, how many past forecasts could be scored, how often
 * the simulated and the stretched 80% range held the actual, how wide each was, and the two factors.
 */
export function StretchEvidence() {
  const ctx = useBindingContext();
  const decision = String(readBinding(ctx, STRETCH.decision));
  const evidence = ctx.files.report.backtest.candidates.ranges;
  return (
    <div data-testid="stretch-evidence">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge color={toneOf(decision)} className="text-sm" data-testid="stretch-decision">
          <Bound binding={STRETCH.decision} />
        </Badge>
        <span className="text-xs text-slate-500">
          Pooled over one and three months: <Bound binding={STRETCH.pooledScored} /> past dates scored, <Bound binding={STRETCH.pooledSimulated} /> held by the
          simulated range, <Bound binding={STRETCH.pooledStretched} /> by the stretched range
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-700">
        <Bound binding={STRETCH.reason} />
      </p>
      <Table className={`${STACK_LG.table} mt-3`}>
        <TableHead className={STACK_LG.head}>
          <TableRow>
            <TableHeaderCell>Months ahead</TableHeaderCell>
            <TableHeaderCell className="text-right">Past dates to learn from</TableHeaderCell>
            <TableHeaderCell className="text-right">Past dates scored</TableHeaderCell>
            <TableHeaderCell className="text-right">Simulated range held</TableHeaderCell>
            <TableHeaderCell className="text-right">Stretched range held</TableHeaderCell>
            <TableHeaderCell className="text-right">Median width, simulated</TableHeaderCell>
            <TableHeaderCell className="text-right">Median width, stretched</TableHeaderCell>
            <TableHeaderCell className="text-right">Lower factor</TableHeaderCell>
            <TableHeaderCell className="text-right">Upper factor</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK_LG.body}>
          {evidence.horizons.map((_, i) => {
            const row = `${ROWS.stretch}/${i}`;
            return (
              <TableRow key={i} className={STACK_LG.row} data-testid="stretch-row">
                <TableCell className={STACK_LG.cell} data-label="Months ahead"><Bound binding={STRETCH.months} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Past dates to learn from"><Bound binding={STRETCH.eligible} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Past dates scored"><Bound binding={STRETCH.scored} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Simulated range held"><Bound binding={STRETCH.coverageSimulated} row={row} /></TableCell>
                <TableCell className={`${STACK_LG.cell} font-medium`} data-label="Stretched range held"><Bound binding={STRETCH.coverageStretched} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Median width, simulated"><Bound binding={STRETCH.widthSimulated} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Median width, stretched"><Bound binding={STRETCH.widthStretched} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Lower factor"><Bound binding={STRETCH.lower} row={row} /></TableCell>
                <TableCell className={STACK_LG.cell} data-label="Upper factor"><Bound binding={STRETCH.upper} row={row} /></TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <p className="mt-3 text-xs text-slate-600">
        <span className="font-semibold text-ft-brand">The rule, declared before the scoring: </span>
        <Bound binding={STRETCH.rule} />
      </p>
    </div>
  );
}
