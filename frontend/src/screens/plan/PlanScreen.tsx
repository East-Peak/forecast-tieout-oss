import { Bound, useBindingContext } from "../../binding/Bound";
import { Callout } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { MetricCard } from "../../components/workbook/MetricCard";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { STACK } from "../../components/workbook/stack";
import { ActionsCard } from "./ActionsCard";
import { B } from "./bindings";
import { CompareTable } from "./CompareTable";
import { ItemsCard } from "./ItemsCard";
import { ScenarioPicker } from "./ScenarioPicker";
import { WindowTable } from "./WindowTable";

/**
 * Plan: what do the actions buy, and which is cheaper? A scenario is picked; as signed there is no plan and
 * the screen says so and invites a pick, rather than showing zeros. With a plan the headline is its effect on
 * the year, then both windows with ranges, each item, the two unit actions compared, and what closes the gap alone.
 */
export default function PlanScreen() {
  const { files } = useBindingContext();
  const plan = files.report.plan;
  const full = plan !== undefined && !("unavailable" in plan) ? plan : null;

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <SectionHeader title="Plan" subtitle="What do the actions buy, and which is cheaper?" />
      <p className="-mt-3 text-xs text-slate-500">
        <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} />
      </p>
      <ScenarioPicker />

      {plan === undefined ? (
        <Callout color="blue" title="There is no plan in this scenario" data-testid="no-plan">
          As signed, nothing is planned, so there is nothing to value and no figure to show. Pick a scenario above to see what a plan buys. The
          two actions below are compared on the roster as signed.
        </Callout>
      ) : null}
      {plan !== undefined && full === null ? (
        <Callout color="amber" title="This plan cannot be valued" data-testid="plan-unavailable">
          <Bound binding={B.planUnavailable} />
        </Callout>
      ) : null}

      {full ? (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" data-testid="plan-headline">
            <MetricCard label="Expected year, with this scenario" value={<Bound binding={B.planExpected} />} className="p-4" />
            <MetricCard label="Gap to target, with it" value={<Bound binding={B.planGap} />} className="p-4" />
            <MetricCard label="The gap changes by" value={<Bound binding={B.cmpGapChange} />} note="Against the roster as signed" className="p-4" />
            <MetricCard label="More booked, next twelve months" value={<Bound binding={B.cmpMoreNext} />} className="p-4">
              <p className="mt-1 text-[11px] leading-tight text-slate-500">
                Cash cost in the same months: <Bound binding={B.cmpCost} />
              </p>
            </MetricCard>
          </div>
          <p className="-mt-2 text-xs text-slate-500">
            <Bound binding={B.planDefinition} /> The plan is <Bound binding={B.planFile} />.
          </p>
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
          <ItemsCard plan={full} />
        </>
      ) : null}

      <ActionsCard />
      <CompareTable />
    </div>
  );
}
