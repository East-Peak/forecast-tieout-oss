/**
 * Test-only. What the Trust screen must show for a company and scenario, written by hand as typed
 * accessors on the generated report types. Texts come from independent.ts, not from src/lib/format.ts.
 */
import { B, VERDICTS } from "../trust/bindings";
import { betterVerdictExpectations, kit, orWords } from "./expectKit";
import * as fmt from "./independent";
import type { Built, Case } from "./screenChecks";

const REC = "/reconciliation";
const passedWord = (ok: boolean) => (ok ? "passed" : "failed");
const yesno = (v: boolean) => (v ? "yes" : "no");

export function build({ report: r, index, company, scenario }: Case): Built {
  const { expected, absent, one, many } = kit();
  const rows = (path: string, n: number) => Array.from({ length: n }, (_, i) => `${path}/${i}`);

  one(B.fiscalYear.id, r.inputs.fiscal_year);
  one(B.asOf.id, fmt.date(r.inputs.as_of));

  // the two verdicts, each with its reason (the Forecast screen's own bindings)
  one(VERDICTS.software.id, r.verdicts.software_correct.verdict);
  one(VERDICTS.softwareSummary.id, r.verdicts.software_correct.summary);
  betterVerdictExpectations(r, { one, many });

  const checks = r.verdicts.software_correct.checks;
  one(B.softwareScope.id, r.verdicts.software_correct.scope);
  many(B.checkName.id, checks.map((c) => c.name), rows("/verdicts/software_correct/checks", checks.length));
  many(B.checkDetail.id, checks.map((c) => c.detail), rows("/verdicts/software_correct/checks", checks.length));
  many(B.checkPassed.id, checks.map((c) => passedWord(c.passed)), rows("/verdicts/software_correct/checks", checks.length));

  // reconciliation
  const rec = r.reconciliation;
  one(B.sourceRows.id, fmt.quantity(rec.source_rows));
  one(B.includedRows.id, fmt.quantity(rec.included_rows));
  one(B.sourceArr.id, fmt.usdFull(rec.source_arr_total));
  one(B.bookingsFytd.id, fmt.usdFull(rec.bookings_fytd));
  const recRows = rows(`${REC}/checks`, rec.checks.length);
  many(B.recName.id, rec.checks.map((c) => c.name), recRows);
  many(B.recDetail.id, rec.checks.map((c) => c.detail), recRows);
  many(B.recPassed.id, rec.checks.map((c) => passedWord(c.passed)), recRows);
  const motions = Object.entries(rec.excluded_motions).map(([name, m]) => [`${REC}/excluded_motions/${name}`, m!] as const);
  many(B.motionRows.id, motions.map(([, m]) => fmt.quantity(m.rows)), motions.map(([row]) => row));
  many(B.motionArr.id, motions.map(([, m]) => fmt.usdShort(m.arr)), motions.map(([row]) => row));
  many(B.motionWon.id, motions.map(([, m]) => fmt.usdShort(m.won_fytd_arr)), motions.map(([row]) => row));
  const exRows = rows(`${REC}/exclusions`, rec.exclusions.length);
  many(B.exRow.id, rec.exclusions.map((e) => fmt.quantity(e.row)), exRows);
  many(B.exDeal.id, rec.exclusions.map((e) => e.deal_id), exRows);
  many(B.exReason.id, rec.exclusions.map((e) => e.reason), exRows);
  many(B.exArr.id, rec.exclusions.map((e) => orWords(e.arr, fmt.usdFull, "no readable ARR")), exRows);

  // history
  const f = r.history.facts;
  one(B.monthsOfHistory.id, fmt.quantity(f.months_of_history));
  one(B.newBusinessDeals.id, fmt.quantity(f.new_business_deals));
  one(B.closedOutcomes.id, fmt.quantity(f.closed_outcomes));
  one(B.maturedSnapshots.id, fmt.quantity(f.matured_snapshots));
  one(B.firstDeal.id, f.first_deal_created === null ? "no deals" : fmt.date(f.first_deal_created));
  one(B.earliestClose.id, f.earliest_close === null ? "no closed deals" : fmt.date(f.earliest_close));
  one(B.deals.id, yesno(f.deal_observations));
  const folds = Object.entries(f.backtest_folds).map(([key, n]) => [`/history/facts/backtest_folds/${key}`, n!] as const);
  many(B.foldCount.id, folds.map(([, n]) => fmt.quantity(n)), folds.map(([row]) => row));
  many(B.limitation.id, r.history.limitations, rows("/history/limitations", r.history.limitations.length));

  // the back-test
  const hz = r.backtest.horizons;
  const hRows = rows("/backtest/horizons", hz.length);
  many(B.btMonths.id, hz.map((h) => fmt.quantity(h.horizon_months)), hRows);
  many(B.btFolds.id, hz.map((h) => fmt.quantity(h.folds)), hRows);
  const err = (h: (typeof hz)[number], method: string) => orWords(h.mean_absolute_error[method] ?? null, fmt.usdShort);
  many(B.btFitted.id, hz.map((h) => err(h, "fitted model")), hRows);
  many(B.btStage.id, hz.map((h) => err(h, "stage-weighted pipeline")), hRows);
  many(B.btRunRate.id, hz.map((h) => err(h, "trailing run-rate")), hRows);
  many(B.btBias.id, hz.map((h) => orWords(h.signed_bias["fitted model"] ?? null, fmt.usdShort)), hRows);
  many(B.btRangeFolds.id, hz.map((h) => fmt.quantity(h.range_coverage.folds_with_a_range)), hRows);
  many(B.btCover80.id, hz.map((h) => (h.range_coverage["80%"] === null ? "not scored" : fmt.percent1(h.range_coverage["80%"]))), hRows);
  many(B.btCover95.id, hz.map((h) => (h.range_coverage["95%"] === null ? "not scored" : fmt.percent1(h.range_coverage["95%"]))), hRows);
  one(B.btScoring.id, r.backtest.scoring);
  many(B.btNote.id, r.backtest.notes, rows("/backtest/notes", r.backtest.notes.length));
  const rc = r.backtest.candidates.recency;
  one(B.recencyCandidate.id, rc.candidate);
  one(B.recencyInUse.id, rc.fit_in_use);
  one(B.recencyAdopted.id, yesno(rc.adopted));
  one(B.recencyReason.id, rc.reason);

  // every rate, once, with its definition, sample and source; the value as its own unit says
  const rates = r.rates;
  const rRows = rows("/rates", rates.length);
  many(B.rName.id, rates.map((x) => x.name), rRows);
  many(B.rDefinition.id, rates.map((x) => x.definition), rRows);
  const byUnit = (unit: string) => rates.map((x, i) => [x, i] as const).filter(([x]) => x.unit === unit);
  const shares = byUnit("share");
  many(B.rShare.id, shares.map(([x]) => fmt.percent1(x.value)), shares.map(([, i]) => `/rates/${i}`));
  const dollars = byUnit("dollars");
  many(B.rDollars.id, dollars.map(([x]) => fmt.usdFull(x.value)), dollars.map(([, i]) => `/rates/${i}`));
  const numbers = byUnit("number");
  many(B.rNumber.id, numbers.map(([x]) => fmt.quantity(x.value)), numbers.map(([, i]) => `/rates/${i}`));
  const ranged = rates.map((x, i) => [x, i] as const).filter(([x]) => x.range95 !== null);
  many(B.rLow.id, ranged.map(([x]) => fmt.percent1(x.range95![0])), ranged.map(([, i]) => `/rates/${i}`));
  many(B.rHigh.id, ranged.map(([x]) => fmt.percent1(x.range95![1])), ranged.map(([, i]) => `/rates/${i}`));
  const unranged = rates.map((x, i) => [x, i] as const).filter(([x]) => x.range95 === null);
  many(B.rNoRange.id, unranged.map(() => "no range reported"), unranged.map(([, i]) => `/rates/${i}`));
  many(B.rSample.id, rates.map((x) => fmt.quantity(x.sample_size)), rRows);
  const withText = (pick: (x: (typeof rates)[number]) => string) => rates.map((x, i) => [pick(x), i] as const).filter(([t]) => t !== "");
  many(B.rNumerator.id, withText((x) => x.numerator).map(([t]) => t), withText((x) => x.numerator).map(([, i]) => `/rates/${i}`));
  many(B.rDenominator.id, withText((x) => x.denominator).map(([t]) => t), withText((x) => x.denominator).map(([, i]) => `/rates/${i}`));
  many(B.rSource.id, rates.map((x) => x.source), rRows);

  // the files and what was run
  const entry = index.companies.find((c) => c.id === company)!.scenarios.find((s) => s.id === scenario)!;
  one(B.reportJson.id, entry.report);
  one(B.reportMd.id, entry.report_markdown);
  one(B.schemaVersion.id, r.schema_version);
  one(B.runData.id, r.inputs.data);
  one(B.runProfile.id, r.inputs.profile);
  one(B.runFit.id, r.inputs.fit);
  one(B.runRanges.id, r.inputs.ranges);
  one(B.runMeasure.id, r.inputs.measure);
  one(B.runDraws.id, fmt.quantity(r.inputs.simulation.draws));
  one(B.runSeed.id, fmt.quantity(r.inputs.simulation.seed));

  return { expected, absent, periodLabels: [] };
}
