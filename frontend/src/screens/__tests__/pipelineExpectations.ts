/**
 * Test-only. What the Pipeline screen must show for a company and scenario, written by hand as typed
 * accessors on the generated report types. Texts come from independent.ts, not from src/lib/format.ts.
 */
import type { TieoutReport } from "../../generated/report";
import { B, FLOW_KEYS, NEW_PIPELINE_WIN_RATE, STAGE_WIN_RATE } from "../pipeline/bindings";
import { kit, orWords } from "./expectKit";
import * as fmt from "./independent";
import type { Built, Case } from "./screenChecks";

type Required = Extract<TieoutReport["required_pipeline"], { cap: unknown }>;
const RP = "/required_pipeline";

export function build({ report: r }: Case): Built {
  const { expected, absent, one, many, when } = kit();
  const rp: Required | null = "unavailable" in r.required_pipeline ? null : r.required_pipeline;

  one(B.fiscalYear.id, r.inputs.fiscal_year);
  one(B.asOf.id, fmt.date(r.inputs.as_of));

  // the pipeline flow: five stages, a count and the dollars
  const flow = r.reconciliation.pipeline_flow;
  const rows = FLOW_KEYS.map((key) => [`/reconciliation/pipeline_flow/${key}`, flow[key]] as const);
  many(B.flowCount.id, rows.map(([, f]) => fmt.quantity(f.count)), rows.map(([row]) => row));
  many(B.flowArr.id, rows.map(([, f]) => fmt.usdShort(f.arr)), rows.map(([row]) => row));

  when(rp !== null, B.openArr.id, () => fmt.usdShort(flow["open at as-of"].arr));
  when(rp !== null, B.openCount.id, () => fmt.quantity(flow["open at as-of"].count));
  when(rp === null, B.requiredUnavailable.id, () => ("unavailable" in r.required_pipeline ? r.required_pipeline.unavailable : ""));
  if (rp !== null) {
    const fy = rp.fiscal_year;
    one(B.fyHeadline.id, fy.headline);
    one(B.fySolvableTotal.id, orWords(fy.solvable_total, fmt.usdShort, "no quarter can be solved"));
    one(B.fySpread.id, fy.single_spread.headline ?? "unavailable");
    one(B.fyWhyDiffer.id, fy.why_they_differ);

    // the quarters
    const q = rp.quarters;
    const qRow = (i: number) => `${RP}/quarters/${i}`;
    const rowsAll = q.map((_, i) => qRow(i));
    many(B.qName.id, q.map((x) => x.quarter), rowsAll);
    many(B.qStatus.id, q.map((x) => x.status), rowsAll);
    many(B.qTarget.id, q.map((x) => fmt.usdShort(x.target)), rowsAll);
    many(B.qActual.id, q.map((x) => fmt.usdShort(x.actual)), rowsAll);
    many(B.qWithout.id, q.map((x) => fmt.usdShort(x.bookings_without_own_pipeline)), rowsAll);
    many(B.qHeadline.id, q.map((x) => x.headline), rowsAll);
    const byOutcome = (outcome: "feasible" | "already covered" | "unreachable within bounds") =>
      q.map((x, i) => [x, i] as const).filter(([x]) => x.outcome === outcome);
    const feasible = byOutcome("feasible");
    many(B.qRequired.id, feasible.map(([x]) => fmt.usdShort(x.required_extra_pipeline!)), feasible.map(([, i]) => qRow(i)));
    const covered = byOutcome("already covered");
    many(B.qRequiredCovered.id, covered.map(() => "none needed: already covered"), covered.map(([, i]) => qRow(i)));
    const none = byOutcome("unreachable within bounds");
    many(B.qRequiredNone.id, none.map(() => "no amount helps within the cap"), none.map(([, i]) => qRow(i)));
    many(B.qExpected.id, q.map((x) => fmt.usdShort(x.expected_created_pipeline)), rowsAll);
    many(B.qYield.id, q.map((x) => fmt.cents(x.cents_booked_in_quarter_per_dollar)), rowsAll);
    many(B.qSurplus.id, q.map((x) => x.surplus_statement ?? "no completed schedule to compare"), rowsAll);

    // too late: the label, each reason as a sentence, each diagnostic, and what the open pipeline would have to do
    const late = q.map((x, i) => [x, i] as const).filter(([x]) => x.too_late.applies);
    many(B.lateLabel.id, late.map(([x]) => x.too_late.label!), late.map(([, i]) => qRow(i)));
    const reasons = late.flatMap(([x, i]) => x.too_late.reasons.map((t, j) => [t, `${qRow(i)}/too_late/reasons/${j}`] as const));
    many(B.lateReason.id, reasons.map(([t]) => t), reasons.map(([, row]) => row));
    const diagnostics = q.flatMap((x, i) => x.too_late.diagnostics.map((t, j) => [t, `${qRow(i)}/too_late/diagnostics/${j}`] as const));
    many(B.lateDiagnostic.id, diagnostics.map(([t]) => t), diagnostics.map(([, row]) => row));
    const open = late.filter(([x]) => x.too_late.open_pipeline !== null);
    many(B.lateOpen.id, open.map(([x]) => x.too_late.open_pipeline!.statement), open.map(([, i]) => qRow(i)));

    // each quarter opened: against the team's record
    many(B.qEarlier.id, q.map((x) => fmt.usdShort(x.earlier_assigned_in_span)), rowsAll);
    many(B.qTotal.id, q.map((x) => orWords(x.total_created_in_span, fmt.usdShort, "nothing to create")), rowsAll);
    many(B.qCapLeft.id, q.map((x) => fmt.usdShort(x.cap_left_before)), rowsAll);
    many(B.qPerDay.id, q.map((x) => orWords(x.per_day.required_total, fmt.usdShort, "not needed")), rowsAll);
    many(B.qPerDayVs.id, q.map((x) => orWords(x.per_day.required_against_team_best, fmt.multiple, "not needed")), rowsAll);
    many(B.qPerAe.id, q.map((x) => orWords(x.per_ramped_ae_month.required_total, fmt.usdShort, "not needed")), rowsAll);
    many(B.qPerAeVs.id, q.map((x) => orWords(x.per_ramped_ae_month.required_against_team_best, fmt.multiple, "not needed")), rowsAll);
    many(B.qRamped.id, q.map((x) => orWords(x.ramped_ae_months, fmt.quantity, "no ramp fitted")), rowsAll);

    const h = rp.team_history;
    one(B.bestQuarter.id, orWords(h.best_four_quarter_average, fmt.usdShort, "fewer than four complete quarters"));
    one(B.bestPerDay.id, orWords(h.best_four_quarter_average_per_day, fmt.usdShort, "fewer than four complete quarters"));
    one(B.median.id, orWords(h.median, fmt.usdShort, "no complete quarter"));
    one(B.historyQuarters.id, fmt.quantity(h.quarters));
    one(B.historyNote.id, h.note);
    one(B.historyUnit.id, h.unit, 2); // under the best four-quarter average and under the median
    one(B.perDayUnit.id, h.per_day_unit);

    const lt = rp.lead_time;
    one(B.ltQuestion.id, lt.question);
    one(B.ltBasis.id, lt.basis);
    one(B.ltFrom.id, fmt.date(lt.created_between[0]));
    one(B.ltTo.id, fmt.date(lt.created_between[1]));
    one(B.ltLater.id, fmt.cents(lt.cents_booked_later));
    one(B.ltWin.id, fmt.percent1(lt.count_outcome.win_within_horizon));
    one(B.ltCountMeaning.id, lt.count_outcome.meaning);
    const ltRows = lt.quarters.map((_, i) => `${RP}/lead_time/quarters/${i}`);
    many(B.ltQuarter.id, lt.quarters.map((x) => x.quarter), ltRows);
    many(B.ltIn.id, lt.quarters.map((x) => fmt.cents(x.cents_booked_in_quarter)), ltRows);
    many(B.ltBy.id, lt.quarters.map((x) => fmt.cents(x.cents_booked_by_quarter_end)), ltRows);

    one(B.cap.id, fmt.usdShort(rp.cap));
    one(B.capRule.id, rp.cap_rule);
    one(B.forward.id, rp.forward_function);
    one(B.expectedBasis.id, rp.expected_basis);
    one(B.method.id, rp.method);
    one(B.lateRule.id, rp.too_late_rule);
    one(B.perRepWhy.id, rp.per_rep_rule.why);
    one(B.meaning.id, rp.meaning);
  } else {
    for (const b of [B.fyHeadline, B.fySolvableTotal, B.fySpread, B.fyWhyDiffer, B.qName, B.ltLater, B.cap, B.bestQuarter]) absent.push({ id: b.id });
  }

  // the stage win rates and the new-pipeline win rate, with their samples
  const picked = r.rates.map((x, i) => [x, i] as const).filter(([x]) => STAGE_WIN_RATE.test(x.name) || x.name === NEW_PIPELINE_WIN_RATE);
  const rRows = picked.map(([, i]) => `/rates/${i}`);
  many(B.rDefinition.id, picked.map(([x]) => x.definition), rRows);
  many(B.rValue.id, picked.map(([x]) => fmt.percent1(x.value)), rRows);
  many(B.rLow.id, picked.map(([x]) => (x.range95 === null ? "no range" : fmt.percent1(x.range95[0]))), rRows);
  const ranged = picked.filter(([x]) => x.range95 !== null);
  many(B.rHigh.id, ranged.map(([x]) => fmt.percent1(x.range95![1])), ranged.map(([, i]) => `/rates/${i}`));
  many(B.rSample.id, picked.map(([x]) => fmt.quantity(x.sample_size)), rRows);
  many(B.rNumerator.id, picked.map(([x]) => x.numerator), rRows);
  many(B.rDenominator.id, picked.map(([x]) => x.denominator), rRows);
  many(B.rSource.id, picked.map(([x]) => x.source), rRows);

  const periodLabels = rp ? rp.quarters.map((x) => x.quarter) : [];
  return { expected, absent, periodLabels };
}
