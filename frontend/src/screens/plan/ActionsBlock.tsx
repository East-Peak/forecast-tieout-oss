import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure, SectionHeader } from "../../components/workbook";
import { STACK_GRID as STACK } from "../../components/workbook/stack";
import { BLOCK, DA_ROWS, DRIVER_CHOICE } from "./driverActionBindings";

/**
 * "Actions", after Apply: each action with the bookings the plan loses if it is removed, in the year and over the
 * next twelve months, the joint gain beside them, the reconciliation line only where the core calls it material, and the same plan
 * without its actions. The removal values are not shares of the joint gain and are labeled as the core labels them.
 * The report's section is the whole content: nothing is added, split or compared here.
 */
export function ActionsBlock() {
  const { files } = useBindingContext();
  const section = files.report.driver_actions;
  if (!("joint_gain" in section)) return null;
  // said only where the core calls the reconciliation material (it does not round to zero at the figure's precision)
  const rest = section.reconciliation.material["rest of fiscal year"];
  const next = section.reconciliation.material["next twelve months"];
  return (
    <Card data-testid="driver-actions">
      <SectionHeader
        title="Actions"
        subtitle="Changes to the win rate, the size of a win, or the creation of new pipeline, valued on top of the plan's hires and programs. Each value is what removing that action loses, not a share of the joint gain."
      />
      <Table className={STACK.table} data-testid="driver-actions-table">
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Action</TableHeaderCell>
            <TableHeaderCell className="text-right">
              <Bound binding={BLOCK.removalLabel} />
              <span className="block text-[10px] font-normal normal-case text-slate-500">rest of the year</span>
            </TableHeaderCell>
            <TableHeaderCell className="text-right">
              <Bound binding={BLOCK.removalLabel} />
              <span className="block text-[10px] font-normal normal-case text-slate-500">next twelve months</span>
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {section.items.map((item, i) => {
            const row = `${DA_ROWS.items}/${i}`;
            return (
              <TableRow key={item.id} className={STACK.row} data-testid="driver-action-row">
                <TableCell className={STACK.title}>
                  <div className="font-medium">
                    <Bound binding={BLOCK.name} row={row} />{" "}
                    <span className="text-[10px] font-semibold uppercase text-slate-500" data-testid="driver-action-driver">{DRIVER_CHOICE[item.driver]}</span>
                  </div>
                  <div className="text-xs font-normal text-slate-500"><Bound binding={BLOCK.affects} row={row} /></div>
                </TableCell>
                <TableCell className={STACK.cell} data-label="Lost if removed, rest of the year"><Bound binding={BLOCK.removedRest} row={row} /></TableCell>
                <TableCell className={STACK.cell} data-label="Lost if removed, next twelve months"><Bound binding={BLOCK.removedNext} row={row} /></TableCell>
              </TableRow>
            );
          })}
          <TableRow className={`${STACK.row} bg-slate-50 font-semibold`} data-testid="driver-actions-joint">
            <TableCell className={STACK.title}>All the actions together (the joint gain)</TableCell>
            <TableCell className={STACK.cell} data-label="Joint gain, rest of the year"><Bound binding={BLOCK.jointRest} /></TableCell>
            <TableCell className={STACK.cell} data-label="Joint gain, next twelve months"><Bound binding={BLOCK.jointNext} /></TableCell>
          </TableRow>
        </TableBody>
      </Table>

      {rest || next ? (
        <div className="mt-3 flex flex-col gap-1 text-xs text-slate-700" data-testid="driver-actions-reconciliation">
          {rest ? (
            <p>
              Rest of the year: the joint gain less the values above is <Bound binding={BLOCK.reconRest} className="font-semibold" />. <Bound binding={BLOCK.reconSentenceRest} />
            </p>
          ) : null}
          {next ? (
            <p>
              Next twelve months: the joint gain less the values above is <Bound binding={BLOCK.reconNext} className="font-semibold" />. <Bound binding={BLOCK.reconSentenceNext} />
            </p>
          ) : null}
        </div>
      ) : null}

      <h3 className="mt-5 font-display text-sm font-semibold text-ft-brand">This plan without its actions</h3>
      <Table className={`${STACK.table} mt-1`} data-testid="driver-actions-compare">
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Expected bookings</TableHeaderCell>
            <TableHeaderCell className="text-right">Fiscal year</TableHeaderCell>
            <TableHeaderCell className="text-right">Next twelve months</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          <TableRow className={STACK.row} data-testid="driver-actions-with">
            <TableCell className={STACK.title}>With its actions</TableCell>
            <TableCell className={STACK.cell} data-label="Fiscal year"><Bound binding={BLOCK.withYear} /></TableCell>
            <TableCell className={STACK.cell} data-label="Next twelve months"><Bound binding={BLOCK.withNext} /></TableCell>
          </TableRow>
          <TableRow className={STACK.row} data-testid="driver-actions-without">
            <TableCell className={STACK.title}>Without its actions</TableCell>
            <TableCell className={STACK.cell} data-label="Fiscal year"><Bound binding={BLOCK.withoutYear} /></TableCell>
            <TableCell className={STACK.cell} data-label="Next twelve months"><Bound binding={BLOCK.withoutNext} /></TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <div className="mt-4">
        <Disclosure title="How an action is valued">
          <div className="flex flex-col gap-2 text-xs text-slate-700">
            <p><Bound binding={BLOCK.definition} /></p>
            <p><Bound binding={BLOCK.removalNote} /></p>
            <p><Bound binding={BLOCK.rangeNote} /></p>
            <p><Bound binding={BLOCK.roundingNote} /></p>
          </div>
        </Disclosure>
      </div>
    </Card>
  );
}
