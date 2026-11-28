import { Bound, useBindingContext } from "../../binding/Bound";
import { COLUMN } from "../../components/workbook/column";
import { BuildYourOwnPlan } from "../../components/BuildYourOwnPlan";
import { Callout, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure, ScreenHeading } from "../../components/workbook";
import { MetricCard } from "../../components/workbook/MetricCard";
import { STACK } from "../../components/workbook/stack";

import { B, ROWS } from "./bindings";
import { DecisionCard } from "./DecisionCard";
import { MonthChart } from "./MonthChart";
import { QuotaCard } from "./QuotaCard";
import { RampAttrition } from "./RampAttrition";

/**
 * Capacity: can this team carry the number? The headline is the roster today and the quota over the
 * target; the evidence follows: the months, the decision on whether headcount explains pipeline, the
 * ramp and attrition with their sources, quota against observed attainment, and the stated limits.
 * Where capacity is not adopted the screen says so in the report's words and shows nothing invented.
 */
export default function CapacityScreen() {
  const { files } = useBindingContext();
  const { roster_capacity: rc, quota_productivity: quota } = files.report;
  const roster = rc.roster;
  const notUsed = rc.decision.outcome !== "adopted";
  const months = rc.months ?? [];

  return (
    <div className={COLUMN}>
      <ScreenHeading
        title="Capacity"
        subtitle="Can this team carry the number?"
        caption={
          <>
            <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} />
          </>
        }
      />

      {notUsed ? (
        <Callout color="amber" title="Capacity is not used for this forecast" data-testid="capacity-not-used">
          {rc.diagnostic ? (
            <>
              Hiring is <Bound binding={B.hiringAction} />.{" "}
            </>
          ) : null}
          Why: <Bound binding={B.decisionReason} />
          {rc.diagnostic ? (
            <p className="mt-1 text-xs text-amber-800">
              <Bound binding={B.diagnosticLabel} />
            </p>
          ) : null}
        </Callout>
      ) : null}

      {"unavailable" in roster ? (
        <Callout color="amber" title="The roster could not be read">
          <Bound binding={B.rosterUnavailable} />
        </Callout>
      ) : null}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5" data-testid="capacity-headline">
        {"unavailable" in roster ? null : (
          <>
            <MetricCard label="Heads today" value={<Bound binding={B.heads} />} note="Quota-carrying AEs employed on the as-of date" className="p-4" />
            <MetricCard label="Ramped equivalents" value={<Bound binding={B.ramped} />} note="Heads, weighted by how far each has ramped" className="p-4" />
            <MetricCard label="Headcount target this month" value={<span className="text-xl"><Bound binding={B.target} /></span>} className="p-4">
              <p className="mt-1 text-[11px] leading-tight text-slate-400"><Bound binding={B.targetNote} /></p>
            </MetricCard>
          </>
        )}
        {"unavailable" in quota ? null : (
          <>
            <MetricCard label="Quota over target" value={<Bound binding={B.quotaOverTarget} />} note="Full-ramp annual quota, over the year's target" className="p-4" />
            <MetricCard label="Attainment, trailing year" value={<Bound binding={B.attainmentAll} />} note="Wins credited over prorated quota" className="p-4" />
          </>
        )}
      </div>

      {months.length > 0 ? <MonthChart /> : null}
      {months.length > 0 ? (
        <Disclosure title="The months behind the chart" hint="Heads, ramped equivalents, departures and the headcount target, month by month.">
          <Table className={STACK.table}>
            <TableHead className={STACK.head}>
              <TableRow>
                <TableHeaderCell>Month</TableHeaderCell>
                <TableHeaderCell>Past or forward</TableHeaderCell>
                <TableHeaderCell className="text-right">Heads</TableHeaderCell>
                <TableHeaderCell className="text-right">Ramped equivalents</TableHeaderCell>
                <TableHeaderCell className="text-right">Departures</TableHeaderCell>
                <TableHeaderCell className="text-right">Headcount target</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody className={STACK.body}>
              {months.map((_, i) => {
                const row = `${ROWS.months}/${i}`;
                return (
                  <TableRow key={i} className={STACK.row} data-testid="month-row">
                    <TableCell className={STACK.title}><Bound binding={B.mMonth} row={row} /></TableCell>
                    <TableCell className={`${STACK.cell} sm:text-left`} data-label="Past or forward"><Bound binding={B.mKind} row={row} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Heads"><Bound binding={B.mHeads} row={row} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Ramped equivalents"><Bound binding={B.mRamped} row={row} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Departures"><Bound binding={B.mDepartures} row={row} /></TableCell>
                    <TableCell className={STACK.cell} data-label="Headcount target"><Bound binding={B.mTarget} row={row} /></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <p className="mt-3 text-xs text-slate-500">
            Forward heads follow today's roster and attrition only: hires in a plan are valued on the Plan screen, not counted here.
          </p>
        </Disclosure>
      ) : null}

      <DecisionCard />
      <RampAttrition />
      <QuotaCard />

      <section className="rounded-ft border border-slate-200 bg-white p-5 shadow-ft" data-testid="limits">
        <h3 className="text-sm font-semibold text-ft-brand">What this screen cannot tell you</h3>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-xs leading-5 text-slate-600">
          {rc.limitations.map((_, i) => (
            <li key={`roster-${i}`}><Bound binding={B.limit} row={`${ROWS.limitations}/${i}`} /></li>
          ))}
          {quota.limits.map((_, i) => (
            <li key={`quota-${i}`}><Bound binding={B.limit} row={`${ROWS.quotaLimits}/${i}`} /></li>
          ))}
        </ul>
      </section>

      <BuildYourOwnPlan />
    </div>
  );
}
