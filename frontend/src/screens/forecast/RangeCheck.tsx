import { Bound, useBindingContext } from "../../binding/Bound";
import { STACK } from "../../components/workbook/stack";
import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure } from "../../components/workbook";
import { B, ROWS } from "./bindings";
import { StretchEvidence } from "./StretchEvidence";

/** How often the fitted forecast's ranges held in the back-test, by horizon, and what the report concludes from it. */
export function RangeCheck() {
  const { files } = useBindingContext();
  const cells = files.report.forecasts.fitted_ranges.cells;
  return (
    <Disclosure
      title="How the ranges were checked"
      hint="Each past forecast date is re-run on what was known then; the share of actuals inside the range is the coverage."
    >
      <div className="mb-3 space-y-1 text-sm text-slate-700">
        <p>
          Rest of the year: <Bound binding={B.checkYearStatus} />
        </p>
        <p>
          Next twelve months: <Bound binding={B.checkNextStatus} />
        </p>
      </div>
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Months ahead</TableHeaderCell>
            <TableHeaderCell className="text-right">Past dates scored</TableHeaderCell>
            <TableHeaderCell className="text-right">Inside the 80% range</TableHeaderCell>
            <TableHeaderCell className="text-right">Inside the 95% range</TableHeaderCell>
            <TableHeaderCell>Label</TableHeaderCell>
            <TableHeaderCell>Coverage reads</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {cells.map((_, i) => {
            const row = `${ROWS.cell}/${i}`;
            return (
              <TableRow key={i} className={STACK.row} data-testid="range-cell-row">
                <TableCell className={STACK.cell} data-label="Months ahead"><Bound binding={B.cHorizon} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Past dates scored"><Bound binding={B.cFolds} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Inside the 80% range"><Bound binding={B.cCoverage80} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Inside the 95% range"><Bound binding={B.cCoverage95} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Label"><Bound binding={B.cLabel} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Coverage reads"><Bound binding={B.cJudgment} row={row} /></TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <h4 className="mb-2 mt-5 text-sm font-semibold text-ft-brand">Stretched by the model's own past misses</h4>
      <StretchEvidence />
    </Disclosure>
  );
}
