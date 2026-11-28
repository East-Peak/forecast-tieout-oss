import { Bound, useBindingContext } from "../../binding/Bound";
import { COLUMN } from "../../components/workbook/column";
import { Callout } from "../../components/ui";
import { Disclosure, SectionHeader } from "../../components/workbook";
import { useYourPlan } from "../../editor/YourPlanContext";
import { YOUR_PLAN } from "../../editor/yourPlan";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { STACK_GRID as STACK } from "../../components/workbook/stack";
import LanesSection from "../../lanes/LanesSection";
import { B } from "./bindings";
import { CompareTable } from "./CompareTable";
import { ItemsCard } from "./ItemsCard";
import { Bridge } from "./Bridge";
import { QuarterTable } from "./QuarterTable";
import { Summary } from "./Summary";
import { Tornado } from "./Tornado";
import { WS } from "./worksheetBindings";
import { YourPlanForm } from "./YourPlanForm";
import { WindowTable } from "./WindowTable";

/**
 * Plan, the landing screen and the planning worksheet. Top to bottom: the summary row (target, as signed, working
 * plan, remaining gap), the editor in place when it is open, then the ledger of the plan in force: what each item
 * contributes and costs, the two unit actions compared, what closes the gap alone, and every scenario side by side.
 */
export default function PlanScreen() {
  const { files, scenario, company } = useBindingContext();
  const desktop = useYourPlan()?.desktop === true;
  const plan = files.report.plan;
  const full = plan !== undefined && !("unavailable" in plan) ? plan : null;
  const note = files.comparison.rows.find((r) => r.scenario === scenario)?.note != null;
  const sheet = files.report.worksheet;
  const worksheet = "unavailable" in sheet ? null : sheet;

  return (
    <div className="flex flex-col gap-6">
     <div className={COLUMN}>
      <SectionHeader title="Plan" subtitle="What moves the outcome, and which plan do we choose?" />
      <p className="-mt-3 text-xs text-slate-500">
        <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} />
      </p>
      <Summary planInForce={worksheet ? worksheet.plan_in_force : null} />
      {worksheet ? null : (
        <Callout color="amber" title="The worksheet cannot be built for this scenario" data-testid="worksheet-unavailable">
          <Bound binding={WS.unavailable} />
        </Callout>
      )}
      {scenario === YOUR_PLAN ? <YourPlanForm company={company} /> : null}
      {worksheet ? (
        <>
          <Tornado sheet={worksheet} />
          <Bridge sheet={worksheet} />
          <Disclosure title="Every scenario side by side" initiallyOpen={desktop}>
            <CompareTable />
          </Disclosure>
          <QuarterTable />
        </>
      ) : null}
     </div>

      {/* the lanes use the whole width the window gives; the rest of the screen keeps its measure */}
      <LanesSection />

     <div className={COLUMN}>
      {plan !== undefined && full === null ? (
        <Callout color="amber" title="This plan cannot be valued" data-testid="plan-unavailable">
          <Bound binding={B.planUnavailable} />
        </Callout>
      ) : null}

      {full ? (
        <Disclosure title="The plan's ledger" hint="Both windows with their ranges, the gap to target, and what each item contributes and costs" initiallyOpen={desktop}>
         <div className="flex flex-col gap-6">
          <WindowTable />
          <Card>
            <SectionHeader title="The gap to target, both windows" subtitle="Gap is target less expected: positive is a shortfall, negative is ahead." />
            <Table className={STACK.table}>
              <TableHead className={STACK.head}>
                <TableRow>
                  <TableHeaderCell>Window</TableHeaderCell>
                  <TableHeaderCell className="text-right">As signed</TableHeaderCell>
                  <TableHeaderCell className="text-right">With this scenario</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody className={STACK.body}>
                <TableRow className={STACK.row}>
                  <TableCell className={STACK.title}>The fiscal year</TableCell>
                  <TableCell className={STACK.cell} data-label="As signed"><Bound binding={B.gapFyBase} /></TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="With this scenario"><Bound binding={B.gapFyPlan} /></TableCell>
                </TableRow>
                <TableRow className={STACK.row}>
                  <TableCell className={STACK.title}>
                    Quarters with a target, within the next twelve months
                    <div className="text-xs font-normal text-slate-500"><Bound binding={B.gapNextNote} /></div>
                  </TableCell>
                  {full.gap.next_twelve_months === null ? (
                    <TableCell className={`${STACK.cell} sm:text-left`} colSpan={2}>&mdash;</TableCell>
                  ) : (
                    <>
                      <TableCell className={STACK.cell} data-label="As signed"><Bound binding={B.gapNextBase} /></TableCell>
                      <TableCell className={`${STACK.cell} font-medium`} data-label="With this scenario"><Bound binding={B.gapNextPlan} /></TableCell>
                    </>
                  )}
                </TableRow>
              </TableBody>
            </Table>
          </Card>
          <ItemsCard plan={full} note={note} />
         </div>
        </Disclosure>
      ) : null}
     </div>
    </div>
  );
}
