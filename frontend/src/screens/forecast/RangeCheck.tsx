import { Bound, useBindingContext } from "../../binding/Bound";
import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure } from "../../components/workbook";
import { B, ROWS } from "./bindings";

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
          Rest of the year: <Bound binding={B.yearRangeStatus} />
        </p>
        <p>
          Next twelve months: <Bound binding={B.nextRangeStatus} />
        </p>
      </div>
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Months ahead</TableHeaderCell>
            <TableHeaderCell className="text-right">Past dates scored</TableHeaderCell>
            <TableHeaderCell className="text-right">Inside the 80% range</TableHeaderCell>
            <TableHeaderCell className="text-right">Inside the 95% range</TableHeaderCell>
            <TableHeaderCell>Label</TableHeaderCell>
            <TableHeaderCell>Coverage reads</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {cells.map((_, i) => {
            const row = `${ROWS.cell}/${i}`;
            return (
              <TableRow key={i} data-testid="range-cell-row">
                <TableCell><Bound binding={B.cHorizon} row={row} /></TableCell>
                <TableCell className="text-right"><Bound binding={B.cFolds} row={row} /></TableCell>
                <TableCell className="text-right"><Bound binding={B.cCoverage80} row={row} /></TableCell>
                <TableCell className="text-right"><Bound binding={B.cCoverage95} row={row} /></TableCell>
                <TableCell><Bound binding={B.cLabel} row={row} /></TableCell>
                <TableCell><Bound binding={B.cJudgement} row={row} /></TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Disclosure>
  );
}
