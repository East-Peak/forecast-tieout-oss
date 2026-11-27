import { Bound, useBindingContext } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { BuildYourOwnPlan } from "../../components/BuildYourOwnPlan";
import { Badge, Callout, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure, SectionHeader } from "../../components/workbook";
import { MetricCard } from "../../components/workbook/MetricCard";
import { STACK } from "../../components/workbook/stack";
import { B, FLOW_KEYS, NEW_PIPELINE_WIN_RATE, ROWS, STAGE_WIN_RATE } from "./bindings";
import { QuarterChart } from "./QuarterChart";
import { QuarterTable } from "./QuarterTable";

const FLOW_LABELS: Record<(typeof FLOW_KEYS)[number], string> = {
  "open at fiscal-year start": "Open at the start of the year",
  created: "Created in the year",
  won: "Won",
  lost: "Lost",
  "open at as-of": "Open now",
};

/**
 * Pipeline: what must be created, by when, and is it too late? The headline is the requirement and which
 * quarters can no longer be funded with new pipeline; the evidence is the year's flow, the requirement
 * against what is expected quarter by quarter, the lead time, and the stage win rates with their samples.
 */
export default function PipelineScreen() {
  const { files } = useBindingContext();
  const { required_pipeline: required, rates } = files.report;
  const winRates = rates.map((rate, i) => [rate, i] as const).filter(([rate]) => STAGE_WIN_RATE.test(rate.name) || rate.name === NEW_PIPELINE_WIN_RATE);

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <SectionHeader title="Pipeline" subtitle="What must be created, by when, and is it too late?" />
      <p className="-mt-3 text-xs text-slate-500">
        <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} />
      </p>

      {"unavailable" in required ? (
        <Callout color="amber" title="The requirement cannot be computed">
          <Bound binding={B.requiredUnavailable} />. The year's flow and the win rates are shown; nothing is solved.
        </Callout>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3" data-testid="pipeline-headline">
            <MetricCard
              label="Extra pipeline, every remaining quarter"
              value={<Bound binding={B.fySolvableTotal} />}
              note="Covers only the quarters that can be solved"
              className="p-4"
            />
            <MetricCard
              label="Extra pipeline, the year as one total"
              value={<Bound binding={B.spreadRequired} />}
              note="Spread evenly to the year's end"
              className="p-4"
            >
              <p className="mt-1 text-[11px] leading-tight text-slate-500" data-testid="spread-outcome">
                <Badge color="slate" size="xs"><Bound binding={B.spreadOutcome} /></Badge>
              </p>
            </MetricCard>
            <MetricCard
              label="Open pipeline now"
              value={<Bound binding={B.openArr} />}
              className="p-4"
            >
              <p className="mt-1 text-[11px] leading-tight text-slate-500">
                in <Bound binding={B.openCount} /> open deals
              </p>
            </MetricCard>
          </div>
          <Callout color="amber" title="Which quarters can still be funded" data-testid="pipeline-answer">
            <Bound binding={B.fyHeadline} />
            <p className="mt-1 text-xs text-amber-800"><Bound binding={B.fyWhyDiffer} /></p>
          </Callout>
        </>
      )}

      <Card>
        <SectionHeader title="The year's pipeline flow" subtitle="What was open at the start of the year, what came in, and where it went." />
        <Table className={STACK.table}>
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Stage of the flow</TableHeaderCell>
              <TableHeaderCell className="text-right">Deals</TableHeaderCell>
              <TableHeaderCell className="text-right">Dollars</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {FLOW_KEYS.map((key) => {
              const row = `${ROWS.flow}/${key}`;
              return (
                <TableRow key={key} className={STACK.row} data-testid="flow-row">
                  <TableCell className={STACK.title}>{FLOW_LABELS[key]}</TableCell>
                  <TableCell className={STACK.cell} data-label="Deals"><Bound binding={B.flowCount} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Dollars"><Bound binding={B.flowArr} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      {"unavailable" in required ? null : (
        <>
          <QuarterChart />
          <QuarterTable />

          <Card>
            <SectionHeader title="How long a created dollar takes to book" subtitle="The lead-time table: why pipeline created now mostly books after the quarter it is created in." />
            <p className="text-sm leading-6 text-slate-700">
              <Bound binding={B.ltQuestion} />, for pipeline created between <Bound binding={B.ltFrom} /> and <Bound binding={B.ltTo} />.
            </p>
            <Table className={`${STACK.table} mt-3`}>
              <TableHead className={STACK.head}>
                <TableRow>
                  <TableHeaderCell>Quarter</TableHeaderCell>
                  <TableHeaderCell className="text-right">Booked in the quarter</TableHeaderCell>
                  <TableHeaderCell className="text-right">Booked by the quarter's end</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody className={STACK.body}>
                {required.lead_time.quarters.map((_, i) => {
                  const row = `${ROWS.leadQuarters}/${i}`;
                  return (
                    <TableRow key={i} className={STACK.row} data-testid="lead-row">
                      <TableCell className={STACK.title}><Bound binding={B.ltQuarter} row={row} /></TableCell>
                      <TableCell className={STACK.cell} data-label="Booked in the quarter"><Bound binding={B.ltIn} row={row} /></TableCell>
                      <TableCell className={STACK.cell} data-label="Booked by the quarter's end"><Bound binding={B.ltBy} row={row} /></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <p className="mt-3 text-xs text-slate-600">
              Booked after the fourth quarter: <Bound binding={B.ltLater} /> per dollar. By deal count, <Bound binding={B.ltWin} /> of created deals are won
              within the horizon: <Bound binding={B.ltCountMeaning} />.
            </p>
            <p className="mt-1 text-xs text-slate-500"><Bound binding={B.ltBasis} /></p>
          </Card>

          <Card>
            <SectionHeader title="Against the team's own record" subtitle="A requirement is held against the most this team has ever created." />
            <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
              <Stat label="Best four-quarter average" binding={B.bestQuarter} note={B.historyUnit} />
              <Stat label="Best four-quarter average, per day" binding={B.bestPerDay} note={B.perDayUnit} />
              <Stat label="Median quarter" binding={B.median} note={B.historyUnit} />
            </dl>
            <p className="mt-3 text-xs text-slate-500">
              Observed over <Bound binding={B.historyQuarters} /> complete quarters. <Bound binding={B.historyNote} />
            </p>
          </Card>
        </>
      )}

      <Card>
        <SectionHeader title="Stage win rates" subtitle="The share of deals open in each stage that are won within the horizon, each with the sample behind it." />
        <Table className={STACK.table}>
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Rate</TableHeaderCell>
              <TableHeaderCell className="text-right">Value</TableHeaderCell>
              <TableHeaderCell className="text-right">95% range</TableHeaderCell>
              <TableHeaderCell className="text-right">Sample</TableHeaderCell>
              <TableHeaderCell>Source</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {winRates.map(([rate, i]) => {
              const row = `${ROWS.rates}/${i}`;
              return (
                <TableRow key={i} className={STACK.row} data-testid="win-rate-row">
                  <TableCell className={STACK.title}>
                    <Bound binding={B.rLabel} row={row} />
                    <div className="text-xs font-normal text-slate-600"><Bound binding={B.rDefinition} row={row} /></div>
                    <div className="text-xs font-normal text-slate-500">
                      <Bound binding={B.rNumerator} row={row} /> of <Bound binding={B.rDenominator} row={row} />
                    </div>
                  </TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="Value"><Bound binding={B.rValue} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="95% range">
                    <Bound binding={B.rLow} row={row} />
                    {rate.range95 !== null ? (
                      <>
                        {" to "}
                        <Bound binding={B.rHigh} row={row} />
                      </>
                    ) : null}
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="Sample"><Bound binding={B.rSample} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} sm:text-left`} data-label="Source"><Bound binding={B.rSource} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      {"unavailable" in required ? null : (
        <Disclosure title="How the requirement was reached" hint="The cap, the forward function, the method and the too-late rule, in the report's words.">
          <dl className="grid gap-x-6 gap-y-3 text-xs text-slate-600 sm:grid-cols-2">
            <Note label="The cap" binding={B.capRule}>
              {" "}
              (<Bound binding={B.cap} />)
            </Note>
            <Note label="Forward function" binding={B.forward} />
            <Note label="What is expected" binding={B.expectedBasis} />
            <Note label="Method" binding={B.method} />
            <Note label="Too late, as a rule" binding={B.lateRule} />
            <Note label="Per ramped AE-month" binding={B.perRepWhy} />
            <Note label="What 'required' means" binding={B.meaning} />
          </dl>
        </Disclosure>
      )}

      <BuildYourOwnPlan />
    </div>
  );
}

function Stat({ label, binding, note }: { label: string; binding: Binding; note: Binding }) {
  return (
    <div>
      <dt className="text-[11px] font-medium uppercase text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-slate-900"><Bound binding={binding} /></dd>
      <dd className="text-[11px] text-slate-500"><Bound binding={note} /></dd>
    </div>
  );
}

function Note({ label, binding, children }: { label: string; binding: Binding; children?: React.ReactNode }) {
  return (
    <div>
      <dt className="font-semibold text-ft-brand">{label}</dt>
      <dd><Bound binding={binding} />{children}</dd>
    </div>
  );
}
