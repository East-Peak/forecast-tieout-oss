import { Fragment, useState } from "react";
import { Bound } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, W } from "./bindings";

const WINDOWS = [
  { key: "rest", title: "Rest of the fiscal year", note: "from the as-of date to the year's end", ids: W.rest },
  { key: "next12", title: "Next twelve months", note: "from the as-of date, whatever the fiscal year", ids: W.next12 },
] as const;

/** As signed against this scenario, in both windows, each with its 80% range; a window opens to its 95% ranges. */
export function WindowTable() {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return (
    <Card>
      <SectionHeader
        title="As signed, and with this scenario"
        subtitle="Bookings in each window. The ranges draw the plan's own uncertainty and leave out the uncertainty in the rates."
      />
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Window</TableHeaderCell>
            <TableHeaderCell className="text-right">As signed</TableHeaderCell>
            <TableHeaderCell className="text-right">80% range, as signed</TableHeaderCell>
            <TableHeaderCell className="text-right">With this scenario</TableHeaderCell>
            <TableHeaderCell className="text-right">80% range, with it</TableHeaderCell>
            <TableHeaderCell className="text-right">More booked</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {WINDOWS.map(({ key, title, note, ids }) => {
            const expanded = open.has(key);
            return (
              <Fragment key={key}>
                <TableRow className={STACK.row} data-testid="window-row">
                  <TableCell className={STACK.title}>
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-label={`Show the 95% ranges for ${title.toLowerCase()}`}
                      onClick={() => toggle(key)}
                      className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                    </button>
                    {title}
                    <div className="text-xs font-normal text-slate-500">{note}</div>
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="As signed"><Bound binding={ids.asSigned} /></TableCell>
                  <TableCell className={STACK.cell} data-label="80% range, as signed">
                    <Bound binding={ids.base80Low} /> to <Bound binding={ids.base80High} />
                  </TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="With this scenario"><Bound binding={ids.withPlan} /></TableCell>
                  <TableCell className={STACK.cell} data-label="80% range, with it">
                    <Bound binding={ids.plan80Low} /> to <Bound binding={ids.plan80High} />
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="More booked"><Bound binding={ids.gain} /></TableCell>
                </TableRow>
                {expanded ? (
                  <TableRow className="block bg-slate-50 sm:table-row" data-testid="window-detail">
                    <TableCell colSpan={6} className="block px-3 py-2 text-xs text-slate-600 sm:table-cell">
                      95% range, as signed: <Bound binding={ids.base95Low} /> to <Bound binding={ids.base95High} />. With this scenario:{" "}
                      <Bound binding={ids.plan95Low} /> to <Bound binding={ids.plan95High} />.
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
      <p className="mt-3 text-xs text-slate-600">
        <span className="font-semibold text-ft-brand">How far to trust these ranges: </span>
        <Bound binding={B.rangeStatus} />
      </p>
      <p className="mt-1 text-xs text-slate-500"><Bound binding={B.rangeDrawn} /></p>
    </Card>
  );
}
