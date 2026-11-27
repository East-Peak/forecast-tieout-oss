/**
 * Test-only. What the Forecast screen must show for a company and scenario, written by hand as
 * typed accessors on the generated report types (not by following the screen's pointers): a
 * mistyped field name fails tsc, and a swapped path shows the wrong figure here. Texts come from
 * independent.ts, not from src/lib/format.ts. The selected scenario governs the screen: for a plan
 * the headline, charts and tables are the with-plan figures.
 */
import type { Absent, Expectation, ExpectedChart } from "../../binding/__tests__/harness";
import type { Binding } from "../../binding/Bound";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { B, PLANNED, SIGNED, STRETCH } from "../forecast/bindings";
import { betterVerdictExpectations } from "./expectKit";
import * as fmt from "./independent";

type Row = ScenarioComparison["rows"][number];
type FullPlan = Extract<NonNullable<TieoutReport["plan"]>, { items: unknown }>;
type PlanItem = FullPlan["items"][number];

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
const methodOf = (r: TieoutReport, name: string) => r.forecasts.methods.find((m) => m.method === name)!;
const fullPlan = (r: TieoutReport): FullPlan | null => (r.plan && !("unavailable" in r.plan) ? r.plan : null);

/** The committed bindings in force for this case (the list the provenance of every element is checked against). */
export function listFor(r: TieoutReport): readonly Binding[] {
  return [...Object.values(B), ...Object.values(STRETCH), ...Object.values(fullPlan(r) ? PLANNED : SIGNED)];
}

export function expectations({ company, scenario, report: r, index, comparison }: Case): {
  expected: Expectation[];
  absent: Absent[];
  badge: { text: string; sign: string } | null;
  periodLabels: string[];
} {
  const expected: Expectation[] = [];
  const absent: Absent[] = [];
  // `times`: how many places the screen deliberately shows the same bound value
  const one = (id: string, text: string, times = 1) => expected.push({ id, texts: Array(times).fill(text) as string[] });
  const many = (id: string, texts: string[], rows?: string[]) => expected.push({ id, texts, rows });
  const when = (condition: boolean, id: string, text: () => string, times = 1) =>
    condition ? one(id, text(), times) : absent.push({ id });
  const whenMany = (condition: boolean, id: string, texts: () => string[], rows?: () => string[]) =>
    condition ? many(id, texts(), rows?.()) : absent.push({ id });

  const fitted = methodOf(r, "fitted model");
  const fa = fitted.available;
  const fy = r.gap.fiscal_year;
  const nx = r.gap.next_twelve_months;
  const plan = fullPlan(r);
  const planned = plan !== null;
  const planUnavailable = r.plan && "unavailable" in r.plan ? r.plan.unavailable : null;
  const baseline = comparison.baseline === scenario;
  const row: Row = comparison.rows.find((x) => x.scenario === scenario)!;
  const company_ = index.companies.find((c) => c.id === company)!;
  const scenario_ = company_.scenarios.find((s) => s.id === scenario)!;
  const horizons = r.forecasts.fitted_ranges.horizons as Record<string, { status: string }>;
  const unavailableFitted = (v: string | null, shown: (s: string) => string) =>
    v === null ? `unavailable: ${fitted.unavailable_reason}` : shown(v);
  const noTarget = `unavailable: ${nx.untargeted.note}`;

  one(B.fiscalYear.id, r.inputs.fiscal_year, 2); // the caption, and the window table
  one(B.asOf.id, fmt.date(r.inputs.as_of));
  one(B.measure.id, r.inputs.measure);
  one(B.yearTarget.id, fmt.usdShort(fy.target), 2); // the card, and the window table
  one(B.yearActual.id, fmt.usdShort(fy.actual_to_date));

  // the headline: the selected scenario's figures
  const head = planned
    ? {
        forecast: plan.with_plan[REST],
        expected: plan.expected_fiscal_year,
        gap: plan.gap.fiscal_year.gap_with_plan,
        r80: plan.ranges.fiscal_year_expected_range80,
        r95: plan.ranges.fiscal_year_expected_range95,
        status: plan.ranges.status,
      }
    : {
        forecast: fy.forecast_rest_of_year,
        expected: fy.expected,
        gap: fy.gap,
        r80: fy.expected_range80,
        r95: fy.expected_range95,
        status: fa ? horizons[REST].status : "",
      };
  one(SIGNED.yearForecast.id, orWords(head.forecast, fmt.usdShort));
  one(SIGNED.yearExpected.id, unavailableFitted(head.expected, fmt.usdShort));
  one(SIGNED.yearGap.id, orWords(head.gap, fmt.usdShort), 2); // the card, and the window table
  one(SIGNED.range80Low.id, orWords(head.r80?.[0] ?? null, fmt.usdShort));
  one(SIGNED.range80High.id, orWords(head.r80?.[1] ?? null, fmt.usdShort));
  one(SIGNED.range95Low.id, orWords(head.r95?.[0] ?? null, fmt.usdShort));
  one(SIGNED.range95High.id, orWords(head.r95?.[1] ?? null, fmt.usdShort));
  when(fa, SIGNED.yearRangeStatus.id, () => head.status);

  when(planned, B.signedExpected.id, () => orWords(fy.expected, fmt.usdShort));
  when(planned, B.signedGap.id, () => orWords(fy.gap, fmt.usdShort));
  const gapSign = head.gap === null ? null : Number(head.gap);
  const badge =
    gapSign === null
      ? null
      : gapSign > 0
        ? { text: "Shortfall", sign: "1" }
        : gapSign < 0
          ? { text: "Ahead", sign: "-1" }
          : { text: "On target", sign: "0" };

  // the label beside each range: a plan's ranges carry the plan's status; the others, the report's own labels
  const fr = r.forecasts.fitted_ranges;
  when(fa, SIGNED.bandsLabel.id, () => (planned ? plan.ranges.status : fr.by_window_label));
  when(fa && !planned, B.rangeLabel80.id, () => ("range80_label" in fy ? fy.range80_label : ""));
  when(fa && !planned, B.rangeLabel95.id, () => ("range95_label" in fy ? fy.range95_label : ""));

  when(fa, B.checkYearStatus.id, () => horizons[REST].status);
  when(fa, B.checkNextStatus.id, () => horizons[TWELVE].status);
  when(!fa, B.fittedUnavailable.id, () => fitted.unavailable_reason);
  when(!methodOf(r, "stage-weighted pipeline").available, B.stageUnavailable.id, () => methodOf(r, "stage-weighted pipeline").unavailable_reason);
  when(!methodOf(r, "trailing run-rate").available, B.runRateUnavailable.id, () => methodOf(r, "trailing run-rate").unavailable_reason);

  one(B.softwareVerdict.id, r.verdicts.software_correct.verdict);
  one(B.softwareSummary.id, r.verdicts.software_correct.summary);
  betterVerdictExpectations(r, {
    one,
    many: (id, texts, rows) => (texts.length > 0 ? many(id, texts, rows) : absent.push({ id })),
  });

  // the two windows, each row for what it covers
  one(B.nextTarget.id, orWords(nx.target, fmt.usdShort, noTarget));
  one(B.nextActual.id, orWords(nx.actual, fmt.usdShort, noTarget));
  one(B.nextThrough.id, nx.targets_through === null ? "no target in this window" : fmt.date(nx.targets_through));
  one(B.nextNote.id, nx.untargeted.note);
  const next12 = planned
    ? { forecast: plan.gap.next_twelve_months?.forecast_with_plan ?? null, gap: plan.gap.next_twelve_months?.gap_with_plan ?? null }
    : { forecast: nx.forecast, gap: nx.gap };
  one(SIGNED.nextForecast.id, orWords(next12.forecast, fmt.usdShort, noTarget));
  one(SIGNED.nextGap.id, orWords(next12.gap, fmt.usdShort, noTarget));
  const total = planned ? plan.with_plan[TWELVE] : fa ? (fitted.horizons as Record<string, string>)[TWELVE] : null;
  when(fa, SIGNED.twelveTotal.id, () => fmt.usdShort(total!));

  // the quarter table: the selected scenario's quarters; a closed quarter says "closed", has no forecast or range
  const quarters = planned ? plan.with_plan_quarters : r.gap.quarters;
  const base = planned ? "/plan/with_plan_quarters" : "/gap/quarters";
  const at = (i: number) => `${base}/${i}`;
  const open = quarters.map((q, i) => [q, i] as const).filter(([q]) => q.status !== "closed");
  many(B.qName.id, quarters.map((x) => x.quarter), quarters.map((_, i) => at(i)));
  many(B.qStatus.id, quarters.map((x) => x.status), quarters.map((_, i) => at(i)));
  many(B.qTarget.id, quarters.map((x) => fmt.usdShort(x.target)), quarters.map((_, i) => at(i)));
  many(B.qActual.id, quarters.map((x) => fmt.usdShort(x.actual)), quarters.map((_, i) => at(i)));
  many(B.qForecast.id, open.map(([x]) => orWords(x.forecast, fmt.usdShort)), open.map(([, i]) => at(i)));
  many(B.qExpected.id, quarters.map((x) => orWords(x.expected, fmt.usdShort)), quarters.map((_, i) => at(i)));
  many(B.qGap.id, quarters.map((x) => orWords(x.gap, fmt.usdShort)), quarters.map((_, i) => at(i)));
  many(B.qRange80Low.id, open.map(([x]) => orWords(x.expected_range80?.[0] ?? null, fmt.usdShort)), open.map(([, i]) => at(i)));
  many(B.qRange80High.id, open.map(([x]) => orWords(x.expected_range80?.[1] ?? null, fmt.usdShort)), open.map(([, i]) => at(i)));
  whenMany(fa && !planned, B.qRangeLabel.id, () => open.map(([x]) => ("range80_label" in x ? x.range80_label : "")), () => open.map(([, i]) => at(i)));
  whenMany(planned, B.qSignedGap.id, () => r.gap.quarters.map((x) => orWords(x.gap, fmt.usdShort)), () => r.gap.quarters.map((_, i) => `/gap/quarters/${i}`));

  const cells = r.forecasts.fitted_ranges.cells;
  const cellRows = () => cells.map((_, i) => `/forecasts/fitted_ranges/cells/${i}`);
  whenMany(fa, B.cHorizon.id, () => cells.map((c) => fmt.count(c.horizon_months)), cellRows);
  whenMany(fa, B.cFolds.id, () => cells.map((c) => fmt.count(c.folds_with_a_range)), cellRows);
  whenMany(fa, B.cCoverage80.id, () => cells.map((c) => (c.coverage80 === null ? "not scored" : fmt.percent1(c.coverage80))), cellRows);
  whenMany(fa, B.cCoverage95.id, () => cells.map((c) => (c.coverage95 === null ? "not scored" : fmt.percent1(c.coverage95))), cellRows);
  whenMany(fa, B.cLabel.id, () => cells.map((c) => c.label), cellRows);
  whenMany(fa, B.cJudgment.id, () => cells.map((c) => c.coverage_judgment), cellRows);

  // the stretch's decision and its evidence, in "how the ranges were checked" (shown whenever the fitted forecast is)
  const st = r.backtest.candidates.ranges;
  const stRows = () => st.horizons.map((_, i) => `/backtest/candidates/ranges/horizons/${i}`);
  const stMany = (id: string, texts: () => string[]) => whenMany(fa, id, texts, stRows);
  when(fa, STRETCH.decision.id, () => st.decision);
  when(fa, STRETCH.reason.id, () => st.reason);
  when(fa, STRETCH.rule.id, () => st.rule);
  when(fa, STRETCH.pooledScored.id, () => (st.pooled === null ? "not compared" : fmt.count(st.pooled.scored_folds)));
  when(fa, STRETCH.pooledSimulated.id, () => (st.pooled === null ? "not compared" : fmt.percent1(st.pooled.coverage_simulated)));
  when(fa, STRETCH.pooledStretched.id, () => (st.pooled === null ? "not compared" : fmt.percent1(st.pooled.coverage_stretched)));
  stMany(STRETCH.months.id, () => st.horizons.map((h) => fmt.count(h.horizon_months)));
  stMany(STRETCH.eligible.id, () => st.horizons.map((h) => fmt.count(h.eligible_folds)));
  stMany(STRETCH.scored.id, () => st.horizons.map((h) => fmt.count(h.scored_folds)));
  stMany(STRETCH.coverageSimulated.id, () => st.horizons.map((h) => (h.coverage_simulated === null ? "not scored" : fmt.percent1(h.coverage_simulated))));
  stMany(STRETCH.coverageStretched.id, () => st.horizons.map((h) => (h.coverage_stretched === null ? "not scored" : fmt.percent1(h.coverage_stretched))));
  stMany(STRETCH.widthSimulated.id, () => st.horizons.map((h) => orWords(h.median_width80_simulated, fmt.usdShort, "not scored")));
  stMany(STRETCH.widthStretched.id, () => st.horizons.map((h) => orWords(h.median_width80_stretched, fmt.usdShort, "not scored")));
  stMany(STRETCH.lower.id, () => st.horizons.map((h) => orWords(h.lower_factor, fmt.multiple, "no width to stretch")));
  stMany(STRETCH.upper.id, () => st.horizons.map((h) => orWords(h.upper_factor, fmt.multiple, "no width to stretch")));

  one(B.scenarioLabel.id, scenario_.label);
  one(B.scenarioDescription.id, scenario_.description);
  const cmp = !baseline;
  when(cmp, B.cmpExpected.id, () => orWords(row.expected_fiscal_year, fmt.usdShort));
  when(cmp, B.cmpGap.id, () => orWords(row.fiscal_year_gap, fmt.usdShort));
  when(cmp, B.cmpGapChange.id, () => orWords(row.fiscal_year_gap_change, fmt.usdShort));
  when(cmp, B.cmpBookingsRest.id, () => orWords(row.bookings_change?.[REST] ?? null, fmt.usdShort));
  when(cmp, B.cmpBookingsNext.id, () => orWords(row.bookings_change?.[TWELVE] ?? null, fmt.usdShort));
  when(cmp, B.cmpCost.id, () => orWords(row.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered"));
  when(planUnavailable !== null, B.planUnavailable.id, () => planUnavailable ?? "");
  when(cmp && planned, B.planDefinition.id, () => plan!.baseline_definition);
  const items: PlanItem[] = cmp && plan ? plan.items : [];
  const itemRows = () => items.map((_, i) => `/plan/items/${i}`);
  const itemsShown = cmp && planned;
  whenMany(itemsShown, B.pItemLabel.id, () => items.map((i) => i.label), itemRows);
  whenMany(itemsShown, B.pItemDetail.id, () => items.map((i) => i.detail), itemRows);
  whenMany(itemsShown, B.pItemContribution.id, () => items.map((i) => (i.contribution === null ? `unavailable: ${"note" in i ? i.note : ""}` : fmt.usdShort(i.contribution[REST]))), itemRows);
  whenMany(itemsShown, B.pItemCost.id, () => items.map((i) => orWords(i.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered")), itemRows);

  const periodLabels = [
    ...new Set([...Object.keys(r.reconciliation.bookings_by_month), ...r.forecasts.windows]),
  ].map(fmt.month);
  periodLabels.push(...quarters.map((q) => q.quarter));
  return { expected, absent, badge, periodLabels };
}

/** What each chart must have been given, from typed accessors (not from the screen's declared paths). */
export function expectedCharts(r: TieoutReport): { monthly: ExpectedChart; quarters: ExpectedChart } {
  const fitted = methodOf(r, "fitted model");
  const stage = methodOf(r, "stage-weighted pipeline");
  const runRate = methodOf(r, "trailing run-rate");
  const plan = fullPlan(r);
  const booked = r.reconciliation.bookings_by_month;
  const windows = r.forecasts.windows;
  const months = [...new Set([...Object.keys(booked), ...windows])].sort();
  const num = (v: string | undefined | null) => (v === undefined || v === null ? null : Number(v));
  const pair = (v: readonly [string, string] | undefined | null) => (v ? [Number(v[0]), Number(v[1])] : null);
  type Spread = { range80: [string, string]; range95: [string, string] };
  const ranges = (plan ? plan.ranges.by_window : r.forecasts.fitted_ranges.by_window) as Record<string, Spread>;
  const signedMonths = fitted.by_window as Record<string, string>;
  const fittedMonths = (plan ? plan.with_plan_by_window : signedMonths) as Record<string, string>;

  const monthly = months.map((period) => {
    const row: Record<string, unknown> = { period, booked: num(booked[period]) };
    if (fitted.available) {
      row.band95 = pair(ranges[period]?.range95);
      row.band80 = pair(ranges[period]?.range80);
      if (plan) row.signed = num(signedMonths[period]);
      row.fitted = num(fittedMonths[period]);
    }
    if (stage.available) row.stage = num((stage.by_window as Record<string, string>)[period]);
    if (runRate.available) row.runRate = num((runRate.by_window as Record<string, string>)[period]);
    return row;
  });
  const series = [{ type: "Bar", dataKey: "booked" }];
  if (fitted.available) {
    series.push({ type: "Area", dataKey: "band95" }, { type: "Area", dataKey: "band80" });
    if (plan) series.push({ type: "Line", dataKey: "signed" });
    series.push({ type: "Line", dataKey: "fitted" });
  }
  if (stage.available) series.push({ type: "Line", dataKey: "stage" });
  if (runRate.available) series.push({ type: "Line", dataKey: "runRate" });

  const quarterRows = (plan ? plan.with_plan_quarters : r.gap.quarters).map((x) => {
    const row: Record<string, unknown> = { period: x.quarter, target: Number(x.target) };
    if (fitted.available) {
      row.expected = num(x.expected);
      row.range80 = x.status === "closed" ? null : pair(x.expected_range80);
    }
    return row;
  });
  const quarterSeries = fitted.available
    ? [{ type: "Bar", dataKey: "expected" }, { type: "Bar", dataKey: "range80" }, { type: "Line", dataKey: "target" }]
    : [{ type: "Line", dataKey: "target" }];
  return {
    monthly: { data: monthly, xKey: "period", series, referenceX: [r.inputs.as_of.slice(0, 7)] },
    quarters: {
      data: [...quarterRows].sort((a, b) => String(a.period).localeCompare(String(b.period))),
      xKey: "period",
      series: quarterSeries,
    },
  };
}
