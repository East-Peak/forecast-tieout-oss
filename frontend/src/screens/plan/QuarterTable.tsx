import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { QUARTER, WS_ROWS } from "./worksheetBindings";

/**
 * Each quarter against its target: as signed, with the working plan, and what is left. The working plan's quarters come
 * from the plan in force; with no plan they are the as-signed quarters, which is what the working plan then is.
 */
export function QuarterTable() {
  const { files } = useBindingContext();
  const plan = files.report.plan;
  const planned = plan !== undefined && !("unavailable" in plan);
  const unvalued = plan !== undefined && "unavailable" in plan;
  const quarters = files.report.gap.quarters;
  return (
    <Card className="p-4 sm:p-5" data-testid="quarter-table">
      <SectionHeader title="Each quarter against its target" subtitle="Remaining gap is target less expected: positive is a shortfall, negative is ahead." />
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Quarter</TableHeaderCell>
            <TableHeaderCell className="text-right">Target</TableHeaderCell>
            <TableHeaderCell className="text-right">As signed</TableHeaderCell>
            <TableHeaderCell className="text-right">Working plan</TableHeaderCell>
            <TableHeaderCell className="text-right">Remaining gap</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {quarters.map((q, i) => {
            const signed = `${WS_ROWS.gapQuarters}/${i}`;
            const own = `${planned ? WS_ROWS.plannedQuarters : WS_ROWS.gapQuarters}/${i}`;
            return (
              <TableRow key={q.quarter} className={STACK.row} data-testid="worksheet-quarter-row">
                <TableCell className={STACK.title}><Bound binding={QUARTER.quarter} row={signed} /></TableCell>
                <TableCell className={STACK.cell} data-label="Target"><Bound binding={QUARTER.target} row={signed} /></TableCell>
                <TableCell className={STACK.cell} data-label="As signed"><Bound binding={QUARTER.asSigned} row={signed} /></TableCell>
                <TableCell className={STACK.cell} data-label="Working plan">{unvalued ? "not valued" : <Bound binding={QUARTER.planned} row={own} />}</TableCell>
                <TableCell className={`${STACK.cell} font-medium`} data-label="Remaining gap">{unvalued ? "not valued" : <Bound binding={QUARTER.remainingGap} row={own} />}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}
