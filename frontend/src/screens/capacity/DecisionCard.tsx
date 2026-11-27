import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import { Badge, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/** Does headcount explain pipeline in this history? The decision, its rule and its evidence, in the report's own words. */
export function DecisionCard() {
  const ctx = useBindingContext();
  const decision = ctx.files.report.roster_capacity.decision;
  const outcome = String(readBinding(ctx, B.decisionOutcome));
  const color = outcome === "adopted" ? "green" : outcome === "not shown" ? "amber" : "slate";
  return (
    <Card>
      <SectionHeader
        title="Does headcount explain pipeline?"
        subtitle="Scored on the back-test's past dates: would the created pipeline have been closer with realized staffing than with a flat rate?"
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge color={color} className="text-sm">
          <Bound binding={B.decisionOutcome} />
        </Badge>
        <span className="text-xs text-slate-500">
          The forecast uses <Bound binding={B.decisionUses} />
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-700">
        <Bound binding={B.decisionReason} />
      </p>
      <p className="mt-2 text-xs text-slate-500">
        <Bound binding={B.decisionLabel} />.{" "}
        <Bound binding={B.decisionAssociation} />
      </p>

      {decision.horizons.length > 0 ? (
        <Table className={`${STACK.table} mt-4`}>
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Months ahead</TableHeaderCell>
              <TableHeaderCell className="text-right">Past dates scored</TableHeaderCell>
              <TableHeaderCell className="text-right">Error with realized staffing</TableHeaderCell>
              <TableHeaderCell className="text-right">Error with a flat rate</TableHeaderCell>
              <TableHeaderCell className="text-right">Staffing's improvement</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {decision.horizons.map((_, i) => {
              const row = `${ROWS.horizons}/${i}`;
              return (
                <TableRow key={i} className={STACK.row} data-testid="horizon-row">
                  <TableCell className={STACK.cell} data-label="Months ahead"><Bound binding={B.hMonths} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Past dates scored"><Bound binding={B.hFolds} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Error with realized staffing"><Bound binding={B.hCapacity} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Error with a flat rate"><Bound binding={B.hFlat} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="Staffing's improvement"><Bound binding={B.hImprovement} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      ) : null}
      <dl className="mt-4 grid gap-x-6 gap-y-2 text-xs text-slate-600 sm:grid-cols-2">
        <div>
          <dt className="font-semibold text-ft-brand">The rule, declared before the scoring</dt>
          <dd><Bound binding={B.decisionRule} /></dd>
        </div>
        <div>
          <dt className="font-semibold text-ft-brand">Scored on</dt>
          <dd><Bound binding={B.decisionScoredOn} /></dd>
        </div>
        <div>
          <dt className="font-semibold text-ft-brand">How much staffing varied over the scored period</dt>
          <dd><Bound binding={B.decisionVariation} /></dd>
        </div>
        <div>
          <dt className="font-semibold text-ft-brand">Scored period</dt>
          <dd>
            <Bound binding={B.periodFrom} />
            {decision.scored_period !== null ? (
              <>
                {" to "}
                <Bound binding={B.periodTo} />
              </>
            ) : null}
          </dd>
        </div>
      </dl>
    </Card>
  );
}
