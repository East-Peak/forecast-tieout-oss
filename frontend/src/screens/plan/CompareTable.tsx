import { Bound, useBindingContext } from "../../binding/Bound";
import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { STACK_GRID as STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/** Every scenario of the company side by side, as the core's generator wrote them in comparison.json. */
export function CompareTable() {
  const { files } = useBindingContext();
  const { rows, baseline } = files.comparison;
  return (
    <div data-testid="compare-table">
      <p className="mb-3 text-xs text-slate-500">Differences are against the roster as signed, written by the core: the browser subtracts nothing.</p>
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Scenario</TableHeaderCell>
            <TableHeaderCell className="text-right">Expected year</TableHeaderCell>
            <TableHeaderCell className="text-right">Gap to target</TableHeaderCell>
            <TableHeaderCell className="text-right">Gap changes by</TableHeaderCell>
            <TableHeaderCell className="text-right">More booked, rest of year</TableHeaderCell>
            <TableHeaderCell className="text-right">More booked, next twelve months</TableHeaderCell>
            <TableHeaderCell className="text-right">Cash cost, next twelve months</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {rows.map((row, i) => {
            const path = `${ROWS.compare}/${i}`;
            return (
              <TableRow key={row.scenario} className={STACK.row} data-testid="compare-row">
                <TableCell className={STACK.title}>
                  <Bound binding={B.sLabel} row={path} />
                  {row.note !== null ? <div className="text-xs font-normal text-slate-500"><Bound binding={B.sNote} row={path} /></div> : null}
                </TableCell>
                <TableCell className={STACK.cell} data-label="Expected year"><Bound binding={B.sExpected} row={path} /></TableCell>
                <TableCell className={STACK.cell} data-label="Gap to target"><Bound binding={B.sGap} row={path} /></TableCell>
                <TableCell className={`${STACK.cell} font-medium`} data-label="Gap changes by"><Bound binding={row.scenario === baseline ? B.sGapChange : B.sGapChangeNv} row={path} /></TableCell>
                <TableCell className={STACK.cell} data-label="More booked, rest of year"><Bound binding={row.scenario === baseline ? B.sRest : B.sRestNv} row={path} /></TableCell>
                <TableCell className={STACK.cell} data-label="More booked, next twelve months"><Bound binding={row.scenario === baseline ? B.sNext : B.sNextNv} row={path} /></TableCell>
                <TableCell className={STACK.cell} data-label="Cash cost, next twelve months">
                  <Bound binding={row.scenario === baseline ? B.sCostNone : B.sCost} row={path} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
