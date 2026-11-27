import { Bound } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { B } from "./bindings";

/** The gap for both windows: the rest of the fiscal year, and the next twelve months. */
export function WindowTable() {
  return (
    <Card>
      <SectionHeader
        title="The gap, both windows"
        subtitle="The fiscal year, and the twelve months after the as-of date, which run past year end. Months outside a quarter with a target are bookings alone."
      />
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Window</TableHeaderCell>
            <TableHeaderCell className="text-right">Target</TableHeaderCell>
            <TableHeaderCell className="text-right">Booked</TableHeaderCell>
            <TableHeaderCell className="text-right">Forecast</TableHeaderCell>
            <TableHeaderCell className="text-right">Gap</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow>
            <TableCell className="whitespace-nowrap font-medium">
              Rest of <Bound binding={B.fiscalYear} />
            </TableCell>
            <TableCell className="text-right"><Bound binding={B.yearTarget} /></TableCell>
            <TableCell className="text-right"><Bound binding={B.yearActual} /></TableCell>
            <TableCell className="text-right"><Bound binding={B.yearForecast} /></TableCell>
            <TableCell className="text-right font-medium"><Bound binding={B.yearGap} /></TableCell>
          </TableRow>
          <TableRow>
            <TableCell className="whitespace-nowrap font-medium">Next twelve months</TableCell>
            <TableCell className="text-right"><Bound binding={B.nextTarget} /></TableCell>
            <TableCell className="text-right"><Bound binding={B.nextActual} /></TableCell>
            <TableCell className="text-right"><Bound binding={B.nextForecast} /></TableCell>
            <TableCell className="text-right font-medium"><Bound binding={B.nextGap} /></TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <p className="mt-3 text-xs text-slate-500">
        Last target ends: <Bound binding={B.nextThrough} />. <Bound binding={B.nextNote} />, forecast{" "}
        <Bound binding={B.nextBookingsAlone} />.
      </p>
    </Card>
  );
}
