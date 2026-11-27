/**
 * Test-only. What the Forecast screen must show for a company and scenario, written by hand as
 * typed accessors on the generated report types (not by following the screen's pointers): a
 * mistyped field name fails tsc, and a swapped path shows the wrong figure here. Texts come from
 * independent.ts, not from src/lib/format.ts.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { B } from "../forecast/bindings";
import * as fmt from "./independent";

type Row = ScenarioComparison["rows"][number];
type PlanItem = Extract<TieoutReport["plan"], { items: unknown }>["items"][number];

const REST = "rest of fiscal year";
const TWELVE = "next twelve months";

export interface Case {
  company: string;
  scenario: string;
  report: TieoutReport;
  index: ReportIndex;
  comparison: ScenarioComparison;
}

const orWords = (value: string | null, shown: (v: string) => string, words = "unavailable") =>
  value === null ? words : shown(value);
const fittedOf = (r: TieoutReport) => r.forecasts.methods.find((m) => m.method === "fitted model")!;
const methodOf = (r: TieoutReport, name: string) => r.forecasts.methods.find((m) => m.method === name)!;
const planOf = (r: TieoutReport) => (r.plan && !("unavailable" in r.plan) ? r.plan : null);

/** The list the screen's binding list must match: one entry per binding id, with how many times and what it reads. */
export function expectations({ company, scenario, report: r, index, comparison }: Case): {
  expected: Expectation[];
  absent: Absent[];
} {
  const expected: Expectation[] = [];
  const absent: Absent[] = [];
  // `times`: how many places the screen deliberately shows the same bound value
  const one = (id: string, text: string, times = 1) => expected.push({ id, texts: Array(times).fill(text) as string[] });
  const many = (id: string, texts: string[]) => expected.push({ id, texts });
  const when = (condition: boolean, id: string, text: () => string, times = 1) =>
    condition ? one(id, text(), times) : absent.push({ id });
  const whenMany = (condition: boolean, id: string, texts: () => string[]) =>
    condition ? many(id, texts()) : absent.push({ id });

  const fitted = fittedOf(r);
  const fy = r.gap.fiscal_year;
  const nx = r.gap.next_twelve_months;
  const unavailableFitted = (v: string | null, shown: (s: string) => string) =>
    v === null ? `unavailable: ${fitted.unavailable_reason}` : shown(v);
  const plan = planOf(r);
  const planUnavailable = r.plan && "unavailable" in r.plan ? r.plan.unavailable : null;
  const baseline = comparison.baseline === scenario;
  const row: Row = comparison.rows.find((x) => x.scenario === scenario)!;
  const company_ = index.companies.find((c) => c.id === company)!;
  const scenario_ = company_.scenarios.find((s) => s.id === scenario)!;

  one(B.fiscalYear.id, r.inputs.fiscal_year, 2); // the caption, and the window table
  one(B.asOf.id, fmt.date(r.inputs.as_of));
  one(B.measure.id, r.inputs.measure);

  one(B.yearTarget.id, fmt.usdShort(fy.target), 2); // the card, and the window table
  one(B.yearActual.id, fmt.usdShort(fy.actual_to_date));
  one(B.yearForecast.id, orWords(fy.forecast_rest_of_year, fmt.usdShort));
  one(B.yearExpected.id, unavailableFitted(fy.expected, fmt.usdShort));
  one(B.yearGap.id, orWords(fy.gap, fmt.usdShort), 2); // the card, and the window table
  one(B.range80Low.id, orWords(fy.expected_range80?.[0] ?? null, fmt.usdShort));
  one(B.range80High.id, orWords(fy.expected_range80?.[1] ?? null, fmt.usdShort));
  one(B.range95Low.id, orWords(fy.expected_range95?.[0] ?? null, fmt.usdShort));
  one(B.range95High.id, orWords(fy.expected_range95?.[1] ?? null, fmt.usdShort));
  const horizons = r.forecasts.fitted_ranges.horizons as Record<string, { status: string }>;
  when(fitted.available, B.yearRangeStatus.id, () => horizons[REST].status, 2); // the note, and the range check
  when(fitted.available, B.nextRangeStatus.id, () => horizons[TWELVE].status);
  when(!fitted.available, B.fittedUnavailable.id, () => fitted.unavailable_reason);
  when(!methodOf(r, "stage-weighted pipeline").available, B.stageUnavailable.id, () => methodOf(r, "stage-weighted pipeline").unavailable_reason);
  when(!methodOf(r, "trailing run-rate").available, B.runRateUnavailable.id, () => methodOf(r, "trailing run-rate").unavailable_reason);

  one(B.softwareVerdict.id, r.verdicts.software_correct.verdict);
  one(B.softwareSummary.id, r.verdicts.software_correct.summary);
  one(B.betterVerdict.id, r.verdicts.forecast_better_than_baselines.verdict);
  one(B.betterReason.id, r.verdicts.forecast_better_than_baselines.reason);

  const noTarget = `unavailable: ${nx.untargeted.note}`;
  one(B.nextTarget.id, orWords(nx.target, fmt.usdShort, noTarget));
  one(B.nextActual.id, orWords(nx.actual, fmt.usdShort, noTarget));
  one(B.nextForecast.id, orWords(nx.forecast, fmt.usdShort, noTarget));
  one(B.nextGap.id, orWords(nx.gap, fmt.usdShort, noTarget));
  one(B.nextThrough.id, nx.targets_through === null ? "no target in this window" : fmt.date(nx.targets_through));
  one(B.nextBookingsAlone.id, orWords(nx.untargeted.forecast, fmt.usdShort));
  one(B.nextNote.id, nx.untargeted.note);

  const q = r.gap.quarters;
  many(B.qName.id, q.map((x) => x.quarter));
  many(B.qStatus.id, q.map((x) => x.status));
  many(B.qTarget.id, q.map((x) => fmt.usdShort(x.target)));
  many(B.qActual.id, q.map((x) => fmt.usdShort(x.actual)));
  many(B.qForecast.id, q.map((x) => orWords(x.forecast, fmt.usdShort)));
  many(B.qExpected.id, q.map((x) => orWords(x.expected, fmt.usdShort)));
  many(B.qGap.id, q.map((x) => orWords(x.gap, fmt.usdShort)));
  many(B.qRange80Low.id, q.map((x) => orWords(x.expected_range80?.[0] ?? null, fmt.usdShort)));
  many(B.qRange80High.id, q.map((x) => orWords(x.expected_range80?.[1] ?? null, fmt.usdShort)));

  const cells = r.forecasts.fitted_ranges.cells;
  whenMany(fitted.available, B.cHorizon.id, () => cells.map((c) => fmt.count(c.horizon_months)));
  whenMany(fitted.available, B.cFolds.id, () => cells.map((c) => fmt.count(c.folds_with_a_range)));
  whenMany(fitted.available, B.cCoverage80.id, () => cells.map((c) => (c.coverage80 === null ? "not scored" : fmt.percent1(c.coverage80))));
  whenMany(fitted.available, B.cCoverage95.id, () => cells.map((c) => (c.coverage95 === null ? "not scored" : fmt.percent1(c.coverage95))));
  whenMany(fitted.available, B.cLabel.id, () => cells.map((c) => c.label));
  whenMany(fitted.available, B.cJudgement.id, () => cells.map((c) => c.coverage_judgement));

  one(B.scenarioLabel.id, scenario_.label);
  one(B.scenarioDescription.id, scenario_.description);
  const cmp = !baseline;
  when(cmp, B.cmpExpected.id, () => orWords(row.expected_fiscal_year, fmt.usdShort));
  when(cmp, B.cmpGap.id, () => orWords(row.fiscal_year_gap, fmt.usdShort));
  when(cmp, B.cmpGapChange.id, () => orWords(row.fiscal_year_gap_change, fmt.usdShort));
  when(cmp, B.cmpBookingsRest.id, () => orWords(row.bookings_change?.[REST] ?? null, fmt.usdShort));
  when(cmp, B.cmpBookingsNext.id, () => orWords(row.bookings_change?.[TWELVE] ?? null, fmt.usdShort));
  when(cmp, B.cmpCost.id, () => orWords(row.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered"));
  when(cmp && planUnavailable !== null, B.planUnavailable.id, () => planUnavailable ?? "");
  when(cmp && plan !== null, B.planDefinition.id, () => plan!.baseline_definition);
  const items: PlanItem[] = cmp && plan ? plan.items : [];
  const itemsShown = cmp && plan !== null;
  whenMany(itemsShown, B.pItemLabel.id, () => items.map((i) => i.label));
  whenMany(itemsShown, B.pItemDetail.id, () => items.map((i) => i.detail));
  whenMany(itemsShown, B.pItemContribution.id, () =>
    items.map((i) => (i.contribution === null ? `unavailable: ${"note" in i ? i.note : ""}` : fmt.usdShort(i.contribution[REST]))),
  );
  whenMany(itemsShown, B.pItemCost.id, () =>
    items.map((i) => orWords(i.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered")),
  );
  return { expected, absent };
}

/** The data each chart must have been given: built from typed accessors, not from the screen's declared paths. */
export function plotted(r: TieoutReport): Record<string, unknown> {
  const fitted = fittedOf(r);
  const stage = methodOf(r, "stage-weighted pipeline");
  const runRate = methodOf(r, "trailing run-rate");
  const booked = r.reconciliation.bookings_by_month;
  const windows = r.forecasts.windows;
  const months = [...new Set([...Object.keys(booked), ...windows])].sort();
  const num = (v: string | undefined | null) => (v === undefined || v === null ? null : Number(v));
  const pair = (v: [string, string] | undefined | null) => (v ? [Number(v[0]), Number(v[1])] : null);
  const ranges = r.forecasts.fitted_ranges.by_window as Record<string, { range80: [string, string]; range95: [string, string] }>;
  const monthly = months.map((period) => {
    const row: Record<string, unknown> = { period, booked: num(booked[period]) };
    if (fitted.available) {
      row.band95 = pair(ranges[period]?.range95);
      row.band80 = pair(ranges[period]?.range80);
      row.fitted = num((fitted.by_window as Record<string, string>)[period]);
    }
    if (stage.available) row.stage = num((stage.by_window as Record<string, string>)[period]);
    if (runRate.available) row.runRate = num((runRate.by_window as Record<string, string>)[period]);
    return row;
  });
  const quarters = r.gap.quarters.map((x) => {
    const row: Record<string, unknown> = { period: x.quarter, target: Number(x.target) };
    if (fitted.available) {
      row.expected = num(x.expected);
      row.range80 = pair(x.expected_range80);
    }
    return row;
  });
  return { monthly, quarters: [...quarters].sort((a, b) => String(a.period).localeCompare(String(b.period))) };
}
