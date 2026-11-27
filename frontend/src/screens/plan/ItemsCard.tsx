import { Bound } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/** Each item of the plan: what it adds to bookings and what it costs, in the order the plan file lists them. */
export function ItemsCard({ plan, note }: { plan: { items: ReadonlyArray<{ kind: string }> }; note: boolean }) {
  return (
    <Card>
      <SectionHeader title="What each item contributes, and costs" subtitle="Each contribution is the extra bookings from adding that item to everything above it." />
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Item</TableHeaderCell>
            <TableHeaderCell className="text-right">More booked, rest of year</TableHeaderCell>
            <TableHeaderCell className="text-right">More booked, next twelve months</TableHeaderCell>
            <TableHeaderCell className="text-right">Cash cost, next twelve months</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {plan.items.map((item, i) => {
            const row = `${ROWS.items}/${i}`;
            return (
              <TableRow key={i} className={STACK.row} data-testid="plan-item-row">
                <TableCell className={STACK.title}>
                  <div className="font-medium"><Bound binding={B.iLabel} row={row} /></div>
                  <div className="text-xs font-normal text-slate-500"><Bound binding={B.iDetail} row={row} /></div>
                  {item.kind === "program" ? (
                    <div className="text-xs font-normal text-slate-500"><Bound binding={B.iSchedule} row={row} /></div>
                  ) : null}
                </TableCell>
                <TableCell className={STACK.cell} data-label="More booked, rest of year"><Bound binding={B.iRest} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="More booked, next twelve months"><Bound binding={B.iNext} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Cash cost, next twelve months"><Bound binding={B.iCost} row={row} /></TableCell>
              </TableRow>
            );
          })}
          <TableRow className={`${STACK.row} bg-slate-50 font-semibold`} data-testid="plan-total-row">
            <TableCell className={STACK.title}>All items together</TableCell>
            <TableCell className={STACK.cell} data-label="More booked, rest of year"><Bound binding={B.itemsRest} /></TableCell>
            <TableCell className={STACK.cell} data-label="More booked, next twelve months"><Bound binding={B.itemsNext} /></TableCell>
            <TableCell className={STACK.cell} data-label="Cash cost, next twelve months"><Bound binding={B.itemsCost} /></TableCell>
          </TableRow>
        </TableBody>
      </Table>
      {note ? (
        <p className="mt-3 text-xs text-slate-700" data-testid="unvalued-note">
          <Bound binding={B.cmpNote} />
        </p>
      ) : null}
      <p className="mt-3 text-xs text-slate-500"><Bound binding={B.itemsOrder} /></p>
      <p className="mt-1 text-xs text-slate-500"><Bound binding={B.itemsCostNote} /></p>
    </Card>
  );
}
