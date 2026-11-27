import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { Badge, Callout, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure, SectionHeader } from "../../components/workbook";
import { MetricCard } from "../../components/workbook/MetricCard";
import { STACK, STACK_LG } from "../../components/workbook/stack";
import { StretchEvidence } from "../forecast/StretchEvidence";
import { Verdicts } from "../forecast/Verdicts";
import { B, HORIZON_WORDS, ROWS } from "./bindings";

const REPORT_FILES = `${import.meta.env.BASE_URL}data/reports/`;

/** A check's result in a plain badge: green for passed, red for failed, read from the report's own true or false. */
function Passed({ binding, row }: { binding: Binding; row: string }) {
  const ctx = useBindingContext();
  const ok = readBinding(ctx, binding, row) === true;
  return (
    <Badge color={ok ? "green" : "red"} size="xs" data-testid="check-result">
      <Bound binding={binding} row={row} />
    </Badge>
  );
}

/**
 * Trust: why should anyone believe any of this? The two verdicts lead, each with its reason; then the
 * reconciliation to the source files, the back-test against both baselines, what the history can and
 * cannot support, every rate once with its definition, sample and source, and the report files themselves.
 */
export default function TrustScreen() {
  const { files } = useBindingContext();
  const r = files.report;
  const checks = r.verdicts.software_correct.checks;
  const motions = Object.keys(r.reconciliation.excluded_motions);
  const folds = Object.keys(r.history.facts.backtest_folds);

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <SectionHeader title="Trust" subtitle="Why should anyone believe any of this?" />
      <p className="-mt-3 text-xs text-slate-500">
        <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} />
      </p>

      <Verdicts />

      <Card>
        <SectionHeader title="Does it tie to the source files?" subtitle="Every row of the deals file is either in the numbers or excluded with a reason." />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MetricCard label="Rows in the source" value={<Bound binding={B.sourceRows} />} className="p-4" />
          <MetricCard label="Rows included" value={<Bound binding={B.includedRows} />} className="p-4" />
          <MetricCard label="ARR in the source" value={<span className="text-xl"><Bound binding={B.sourceArr} /></span>} className="p-4" />
          <MetricCard label="Booked this year to date" value={<span className="text-xl"><Bound binding={B.bookingsFytd} /></span>} className="p-4" />
        </div>
        <Table className={`${STACK.table} mt-4`}>
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Reconciliation check</TableHeaderCell>
              <TableHeaderCell>What it compared</TableHeaderCell>
              <TableHeaderCell className="text-right">Result</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {r.reconciliation.checks.map((_, i) => {
              const row = `${ROWS.recChecks}/${i}`;
              return (
                <TableRow key={i} className={STACK.row} data-testid="reconciliation-check">
                  <TableCell className={STACK.title}><Bound binding={B.recName} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} sm:text-left`} data-label="What it compared"><Bound binding={B.recDetail} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Result"><Passed binding={B.recPassed} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {motions.length > 0 ? (
          <>
            <h3 className="mt-5 text-sm font-semibold text-ft-brand">Left out as another motion</h3>
            <p className="mb-2 text-xs text-slate-500">Expansion and renewal are not new business and are not in these numbers.</p>
            <Table className={STACK.table}>
              <TableHead className={STACK.head}>
                <TableRow>
                  <TableHeaderCell>Motion</TableHeaderCell>
                  <TableHeaderCell className="text-right">Rows</TableHeaderCell>
                  <TableHeaderCell className="text-right">ARR</TableHeaderCell>
                  <TableHeaderCell className="text-right">Won this year</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody className={STACK.body}>
                {motions.map((name) => {
                  const row = `${ROWS.motions}/${name}`;
                  return (
                    <TableRow key={name} className={STACK.row} data-testid="excluded-motion">
                      <TableCell className={`${STACK.title} capitalize`}>{name}</TableCell>
                      <TableCell className={STACK.cell} data-label="Rows"><Bound binding={B.motionRows} row={row} /></TableCell>
                      <TableCell className={STACK.cell} data-label="ARR"><Bound binding={B.motionArr} row={row} /></TableCell>
                      <TableCell className={STACK.cell} data-label="Won this year"><Bound binding={B.motionWon} row={row} /></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </>
        ) : null}
        {r.reconciliation.exclusions.length > 0 ? (
          <div className="mt-4">
            <Disclosure title="Every excluded row" hint="Each row left out, and why.">
              <div className="max-h-96 overflow-y-auto">
                <Table className={STACK.table}>
                  <TableHead className={STACK.head}>
                    <TableRow>
                      <TableHeaderCell className="text-right">Row</TableHeaderCell>
                      <TableHeaderCell>Deal</TableHeaderCell>
                      <TableHeaderCell>Why</TableHeaderCell>
                      <TableHeaderCell className="text-right">ARR</TableHeaderCell>
                    </TableRow>
                  </TableHead>
                  <TableBody className={STACK.body}>
                    {r.reconciliation.exclusions.map((_, i) => {
                      const row = `${ROWS.exclusions}/${i}`;
                      return (
                        <TableRow key={i} className={STACK.row} data-testid="exclusion-row">
                          <TableCell className={STACK.cell} data-label="Row"><Bound binding={B.exRow} row={row} /></TableCell>
                          <TableCell className={`${STACK.cell} sm:text-left`} data-label="Deal"><Bound binding={B.exDeal} row={row} /></TableCell>
                          <TableCell className={`${STACK.cell} sm:text-left`} data-label="Why"><Bound binding={B.exReason} row={row} /></TableCell>
                          <TableCell className={STACK.cell} data-label="ARR"><Bound binding={B.exArr} row={row} /></TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </Disclosure>
          </div>
        ) : null}
      </Card>

      <Card>
        <SectionHeader
          title="How the forecast did on the past"
          subtitle="Each past forecast date re-run on what was known then, against the two simple baselines: mean absolute error in dollars, lower is better."
        />
        <Table className={STACK_LG.table}>
          <TableHead className={STACK_LG.head}>
            <TableRow>
              <TableHeaderCell>Months ahead</TableHeaderCell>
              <TableHeaderCell className="text-right">Past dates scored</TableHeaderCell>
              <TableHeaderCell className="text-right">Fitted model</TableHeaderCell>
              <TableHeaderCell className="text-right">Stage-weighted pipeline</TableHeaderCell>
              <TableHeaderCell className="text-right">Last twelve months' pace</TableHeaderCell>
              <TableHeaderCell className="text-right">Fitted model's bias</TableHeaderCell>
              <TableHeaderCell className="text-right">Dates with a range</TableHeaderCell>
              <TableHeaderCell className="text-right">Inside the 80% range</TableHeaderCell>
              <TableHeaderCell className="text-right">Inside the 95% range</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK_LG.body}>
            {r.backtest.horizons.map((_, i) => {
              const row = `${ROWS.horizons}/${i}`;
              return (
                <TableRow key={i} className={STACK_LG.row} data-testid="backtest-row">
                  <TableCell className={STACK_LG.cell} data-label="Months ahead"><Bound binding={B.btMonths} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Past dates scored"><Bound binding={B.btFolds} row={row} /></TableCell>
                  <TableCell className={`${STACK_LG.cell} font-medium`} data-label="Fitted model"><Bound binding={B.btFitted} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Stage-weighted pipeline"><Bound binding={B.btStage} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Last twelve months' pace"><Bound binding={B.btRunRate} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Fitted model's bias"><Bound binding={B.btBias} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Dates with a range"><Bound binding={B.btRangeFolds} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Inside the 80% range"><Bound binding={B.btCover80} row={row} /></TableCell>
                  <TableCell className={STACK_LG.cell} data-label="Inside the 95% range"><Bound binding={B.btCover95} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <p className="mt-3 text-xs text-slate-600"><Bound binding={B.btScoring} /></p>
        {r.backtest.notes.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
            {r.backtest.notes.map((_, i) => (
              <li key={i}><Bound binding={B.btNote} row={`${ROWS.notes}/${i}`} /></li>
            ))}
          </ul>
        ) : null}
        <p className="mt-3 text-xs text-slate-600">
          <span className="font-semibold text-ft-brand">A fit tried and kept or dropped: </span>
          <Bound binding={B.recencyCandidate} /> against <Bound binding={B.recencyInUse} />; adopted: <Bound binding={B.recencyAdopted} />.{" "}
          <Bound binding={B.recencyReason} />
        </p>
      </Card>

      <Card>
        <SectionHeader
          title="Are the ranges stretched by past misses?"
          subtitle="Each past forecast date, stretched with only what had been learned by then: did the stretched range hold the actual more often than the simulated one?"
        />
        <StretchEvidence />
      </Card>

      <Card>
        <SectionHeader title="What the history can and cannot support" />
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
          <Fact label="Months of history" binding={B.monthsOfHistory} />
          <Fact label="New-business deals" binding={B.newBusinessDeals} />
          <Fact label="Closed outcomes" binding={B.closedOutcomes} />
          <Fact label="Monthly snapshots matured" binding={B.maturedSnapshots} />
          <Fact label="First deal created" binding={B.firstDeal} />
          <Fact label="Earliest close" binding={B.earliestClose} />
          <Fact label="Past amounts and dates recorded" binding={B.deals} />
          {folds.map((key) => (
            <div key={key}>
              <dt className="text-[11px] font-medium uppercase text-slate-500">{HORIZON_WORDS[key] ?? key}: past dates scored</dt>
              <dd className="mt-0.5 text-lg font-semibold text-slate-900"><Bound binding={B.foldCount} row={`${ROWS.folds}/${key}`} /></dd>
            </div>
          ))}
        </dl>
        <ul className="mt-4 list-disc space-y-1.5 pl-5 text-xs leading-5 text-slate-600" data-testid="history-limitations">
          {r.history.limitations.map((_, i) => (
            <li key={i}><Bound binding={B.limitation} row={`${ROWS.limitations}/${i}`} /></li>
          ))}
        </ul>
      </Card>

      <Disclosure title="Every rate, once" hint="Each with its definition, its sample and where it came from: fitted from the history, entered by the company, or left at a default.">
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
            {r.rates.map((rate, i) => {
              const row = `${ROWS.rates}/${i}`;
              const value = rate.unit === "share" ? B.rShare : rate.unit === "dollars" ? B.rDollars : B.rNumber;
              return (
                <TableRow key={i} className={STACK.row} data-testid="rate-row">
                  <TableCell className={STACK.title}>
                    <div className="break-words font-mono text-xs"><Bound binding={B.rName} row={row} /></div>
                    <div className="text-xs font-normal text-slate-600"><Bound binding={B.rDefinition} row={row} /></div>
                    {rate.numerator !== "" || rate.denominator !== "" ? (
                      <div className="text-xs font-normal text-slate-500">
                        {rate.numerator !== "" ? <Bound binding={B.rNumerator} row={row} /> : null}
                        {rate.numerator !== "" && rate.denominator !== "" ? " of " : null}
                        {rate.denominator !== "" ? <Bound binding={B.rDenominator} row={row} /> : null}
                      </div>
                    ) : null}
                  </TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="Value"><Bound binding={value} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="95% range">
                    {rate.range95 !== null ? (
                      <>
                        <Bound binding={B.rLow} row={row} /> to <Bound binding={B.rHigh} row={row} />
                      </>
                    ) : (
                      <Bound binding={B.rNoRange} row={row} />
                    )}
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="Sample"><Bound binding={B.rSample} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} sm:text-left`} data-label="Source"><Bound binding={B.rSource} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Disclosure>

      <Disclosure title="The software's own checks" hint="Run on this report's numbers each time it is built.">
        <p className="mb-3 text-xs text-slate-600"><Bound binding={B.softwareScope} /></p>
        <Table className={STACK.table}>
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Check</TableHeaderCell>
              <TableHeaderCell>What it compared</TableHeaderCell>
              <TableHeaderCell className="text-right">Result</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {checks.map((_, i) => {
              const row = `${ROWS.softwareChecks}/${i}`;
              return (
                <TableRow key={i} className={STACK.row} data-testid="software-check">
                  <TableCell className={STACK.title}><Bound binding={B.checkName} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} sm:text-left`} data-label="What it compared"><Bound binding={B.checkDetail} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Result"><Passed binding={B.checkPassed} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Disclosure>

      <Callout color="slate" title="The report itself" data-testid="report-files">
        <p className="text-sm">
          Every figure on every screen is in these files: <Bound binding={B.reportMd} linkBase={REPORT_FILES} className="font-medium text-ft-brand underline" /> to read, and{" "}
          <Bound binding={B.reportJson} linkBase={REPORT_FILES} className="font-medium text-ft-brand underline" /> to use.
        </p>
        <p className="mt-2 text-xs text-slate-600">
          Schema <Bound binding={B.schemaVersion} /> · data in <Bound binding={B.runData} />, profile in <Bound binding={B.runProfile} /> · fit: <Bound binding={B.runFit} /> · ranges:{" "}
          <Bound binding={B.runRanges} /> from <Bound binding={B.runDraws} /> draws at seed <Bound binding={B.runSeed} /> · measure: <Bound binding={B.runMeasure} />
        </p>
      </Callout>
    </div>
  );
}

function Fact({ label, binding }: { label: string; binding: Binding }) {
  return (
    <div>
      <dt className="text-[11px] font-medium uppercase text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-slate-900"><Bound binding={binding} /></dd>
    </div>
  );
}
