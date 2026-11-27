import { Bound } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, PLANNED, SIGNED } from "./bindings";

const dash = <span className="text-slate-400">&mdash;</span>;

/**
 * The gap for both windows, each row named for what it covers: the whole fiscal year, the quarters
 * with a target that end within the next twelve months, and all twelve months' forecast on its own.
 */
export function WindowTable({ planned, fittedAvailable }: { planned: boolean; fittedAvailable: boolean }) {
  const V = planned ? PLANNED : SIGNED;
  return (
    <Card>
      <SectionHeader
        title="The gap, both windows"
        subtitle="Targets cover whole quarters, so the twelve months are shown two ways: the quarters with a target, and every month."
      />
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Covers</TableHeaderCell>
            <TableHeaderCell className="text-right">Target</TableHeaderCell>
            <TableHeaderCell className="text-right">Booked</TableHeaderCell>
            <TableHeaderCell className="text-right">Forecast</TableHeaderCell>
            <TableHeaderCell className="text-right">Gap</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          <TableRow className={STACK.row}>
            <TableCell className={STACK.title}>
              <Bound binding={B.fiscalYear} />, the whole year
              <div className="text-xs font-normal text-slate-500">booked to date, forecast for the rest</div>
            </TableCell>
            <TableCell className={STACK.cell} data-label="Target"><Bound binding={B.yearTarget} /></TableCell>
            <TableCell className={STACK.cell} data-label="Booked"><Bound binding={B.yearActual} /></TableCell>
            <TableCell className={STACK.cell} data-label="Forecast"><Bound binding={V.yearForecast} /></TableCell>
            <TableCell className={`${STACK.cell} font-medium`} data-label="Gap"><Bound binding={V.yearGap} /></TableCell>
          </TableRow>
          <TableRow className={STACK.row}>
            <TableCell className={STACK.title}>
              Quarters with a target, through <Bound binding={B.nextThrough} />
              <div className="text-xs font-normal text-slate-500">inside the next twelve months</div>
            </TableCell>
            <TableCell className={STACK.cell} data-label="Target"><Bound binding={B.nextTarget} /></TableCell>
            <TableCell className={STACK.cell} data-label="Booked"><Bound binding={B.nextActual} /></TableCell>
            <TableCell className={STACK.cell} data-label="Forecast"><Bound binding={V.nextForecast} /></TableCell>
            <TableCell className={`${STACK.cell} font-medium`} data-label="Gap"><Bound binding={V.nextGap} /></TableCell>
          </TableRow>
          <TableRow className={STACK.row}>
            <TableCell className={STACK.title}>
              The next twelve months, every month
              <div className="text-xs font-normal text-slate-500">no target for the months after the last one</div>
            </TableCell>
            <TableCell className={STACK.cell} data-label="Target">{dash}</TableCell>
            <TableCell className={STACK.cell} data-label="Booked">{dash}</TableCell>
            <TableCell className={STACK.cell} data-label="Forecast">
              {fittedAvailable ? <Bound binding={V.twelveTotal} /> : <span>unavailable</span>}
            </TableCell>
            <TableCell className={STACK.cell} data-label="Gap">{dash}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <p className="mt-3 text-xs text-slate-500">
        <Bound binding={B.nextNote} />.
      </p>
    </Card>
  );
}
