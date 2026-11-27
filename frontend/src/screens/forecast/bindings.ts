import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";

/**
 * The Forecast screen's committed binding list: every business value the screen shows, with the
 * file, pointer, unit and format it is read through. The selected scenario governs the screen: for
 * a plan, the headline, ranges, charts and both tables read the plan's with-plan figures (SIGNED and
 * PLANNED hold the bindings whose pointer differs, under the same ids), and the as-signed figure sits
 * beside the headline as a labeled comparison. A row binding is read from each row of a collection
 * (ROWS). `{scenario}` and `{company}` in a pointer stand for the visitor's current choice.
 * The tests assert this list against independently written expectations.
 */
const REST = "rest of fiscal year";
const TWELVE = "next twelve months";
const FITTED_METHOD = "/forecasts/methods/{method=fitted model}";
const UNAVAILABLE_FITTED = { reason: `${FITTED_METHOD}/unavailable_reason`, absolute: true } as const;
const WORDS = { words: "unavailable" } as const;
const NO_TARGET = { reason: "/gap/next_twelve_months/untargeted/note", absolute: true } as const;

const usd = (id: string, path: string, extra: Partial<Binding> = {}) =>
  bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const text = (id: string, path: string, extra: Partial<Binding> = {}) =>
  bind({ id, path, unit: "text", format: "text", ...extra });
const count = (id: string, path: string, extra: Partial<Binding> = {}) =>
  bind({ id, path, unit: "count", format: "count", ...extra });
const share = (id: string, path: string, extra: Partial<Binding> = {}) =>
  bind({ id, path, unit: "fraction", format: "percent1", ...extra });

/** Bindings that read the same place whatever the scenario. */
export const B = {
  // header
  fiscalYear: text("fiscal-year", "/inputs/fiscal_year"),
  asOf: bind({ id: "as-of", path: "/inputs/as_of", unit: "date", format: "date" }),
  measure: text("measure", "/inputs/measure"),

  // the year at a glance
  yearTarget: usd("year.target", "/gap/fiscal_year/target"),
  yearActual: usd("year.actual", "/gap/fiscal_year/actual_to_date"),
  fittedUnavailable: text("fitted.unavailable-reason", `${FITTED_METHOD}/unavailable_reason`),
  stageUnavailable: text("stage.unavailable-reason", "/forecasts/methods/{method=stage-weighted pipeline}/unavailable_reason"),
  runRateUnavailable: text("run-rate.unavailable-reason", "/forecasts/methods/{method=trailing run-rate}/unavailable_reason"),

  // both verdicts, each with its reason (the report's own words; the better-than-baselines reason has no figures)
  softwareVerdict: text("verdict.software", "/verdicts/software_correct/verdict"),
  softwareSummary: text("verdict.software.summary", "/verdicts/software_correct/summary"),
  betterVerdict: text("verdict.better", "/verdicts/forecast_better_than_baselines/verdict"),
  betterReason: text("verdict.better.reason", "/verdicts/forecast_better_than_baselines/in_words"),
  // a row per verdict horizon (ROWS.betterComparisons): the model's error, each baseline's, which is lower
  cmpMonths: bind({ id: "verdict.better.months", path: "/horizon_months", unit: "count", format: "count" }),
  cmpModel: usd("verdict.better.model", "/model_error"),
  cmpStage: usd("verdict.better.stage", "/against/stage-weighted pipeline/baseline_error"),
  cmpStageOutcome: text("verdict.better.stage.outcome", "/against/stage-weighted pipeline/outcome"),
  cmpRunRate: usd("verdict.better.run-rate", "/against/trailing run-rate/baseline_error"),
  cmpRunRateOutcome: text("verdict.better.run-rate.outcome", "/against/trailing run-rate/outcome"),

  // the quarters with a target, and the twelve months
  nextTarget: usd("next12.target", "/gap/next_twelve_months/target", { unavailable: NO_TARGET }),
  nextActual: usd("next12.actual", "/gap/next_twelve_months/actual", { unavailable: NO_TARGET }),
  nextThrough: bind({
    id: "next12.through",
    path: "/gap/next_twelve_months/targets_through",
    unit: "date",
    format: "date",
    unavailable: { words: "no target in this window" },
  }),
  nextNote: text("next12.note", "/gap/next_twelve_months/untargeted/note"),
  // how the fitted forecast's ranges fared in the back-test (the model's own record, whatever the scenario)
  checkYearStatus: text("check.year.status", `/forecasts/fitted_ranges/horizons/${REST}/status`),
  checkNextStatus: text("check.next12.status", `/forecasts/fitted_ranges/horizons/${TWELVE}/status`),

  // the label beside each range of a scenario with no plan (a plan's ranges carry the plan's own status)
  rangeLabel80: text("year.range80.label", "/gap/fiscal_year/range80_label"),
  rangeLabel95: text("year.range95.label", "/gap/fiscal_year/range95_label"),
  qRangeLabel: text("quarter.range80.label", "/range80_label"),

  // a row of the quarter table (the rows are SIGNED's or PLANNED's, see ROWS)
  qName: text("quarter.name", "/quarter"),
  qStatus: text("quarter.status", "/status"),
  qTarget: usd("quarter.target", "/target"),
  qActual: usd("quarter.actual", "/actual"),
  qForecast: usd("quarter.forecast", "/forecast", { unavailable: WORDS }),
  qExpected: usd("quarter.expected", "/expected", { unavailable: WORDS }),
  qGap: usd("quarter.gap", "/gap", { tint: "shortfall", unavailable: WORDS }),
  qRange80Low: usd("quarter.range80.low", "/expected_range80/0", { unavailable: WORDS }),
  qRange80High: usd("quarter.range80.high", "/expected_range80/1", { unavailable: WORDS }),

  // a row of the range back-test (each of /forecasts/fitted_ranges/cells)
  cHorizon: bind({ id: "cell.horizon", path: "/horizon_months", unit: "count", format: "count" }),
  cFolds: bind({ id: "cell.folds", path: "/folds_with_a_range", unit: "count", format: "count" }),
  cCoverage80: bind({ id: "cell.coverage80", path: "/coverage80", unit: "fraction", format: "percent1", unavailable: { words: "not scored" } }),
  cCoverage95: bind({ id: "cell.coverage95", path: "/coverage95", unit: "fraction", format: "percent1", unavailable: { words: "not scored" } }),
  cLabel: text("cell.label", "/label"),
  cJudgment: text("cell.judgment", "/coverage_judgment"),

  // this scenario (index, comparison; a plan's items from the report)
  scenarioLabel: text("scenario.label", "/companies/{id={company}}/scenarios/{id={scenario}}/label", { source: "index" }),
  scenarioDescription: text("scenario.description", "/companies/{id={company}}/scenarios/{id={scenario}}/description", { source: "index" }),
  cmpExpected: usd("scenario.expected", "/rows/{scenario={scenario}}/expected_fiscal_year", { source: "comparison", unavailable: WORDS }),
  cmpGap: usd("scenario.gap", "/rows/{scenario={scenario}}/fiscal_year_gap", { source: "comparison", tint: "shortfall", unavailable: WORDS }),
  cmpGapChange: usd("scenario.gap-change", "/rows/{scenario={scenario}}/fiscal_year_gap_change", { source: "comparison", unavailable: WORDS }),
  cmpBookingsRest: usd("scenario.bookings.rest", `/rows/{scenario={scenario}}/bookings_change/${REST}`, { source: "comparison", unavailable: WORDS }),
  cmpBookingsNext: usd("scenario.bookings.next12", `/rows/{scenario={scenario}}/bookings_change/${TWELVE}`, { source: "comparison", unavailable: WORDS }),
  cmpCost: usd("scenario.cost", "/rows/{scenario={scenario}}/cash_cost_in_twelve_months", { source: "comparison", unavailable: { words: "cost not entered" } }),
  planUnavailable: text("plan.unavailable", "/plan/unavailable"),
  planDefinition: text("plan.baseline-definition", "/plan/baseline_definition"),
  pItemLabel: text("plan.item.label", "/label"),
  pItemDetail: text("plan.item.detail", "/detail"),
  pItemContribution: usd("plan.item.contribution", `/contribution/${REST}`, { unavailable: { reason: "/note" } }),
  pItemCost: usd("plan.item.cost", "/cash_cost_in_twelve_months", { unavailable: { words: "cost not entered" } }),

  // beside a plan's headline: the same figure as signed, a labeled comparison
  signedExpected: usd("year.expected.signed", "/gap/fiscal_year/expected"),
  signedGap: usd("year.gap.signed", "/gap/fiscal_year/gap", { tint: "shortfall" }),
  qSignedGap: usd("quarter.gap.signed", "/gap", { tint: "shortfall", unavailable: WORDS }),
} as const satisfies Record<string, Binding>;

const NEXT12_PLAN = "/plan/gap/next_twelve_months";
const STRETCH_PATH = "/backtest/candidates/ranges";
const NOT_COMPARED = { words: "not compared" } as const;
const NOT_SCORED = { words: "not scored" } as const;

/**
 * Goal 2D: were the simulated ranges stretched by the model's own past misses, and what did the back-test
 * say? The Forecast screen's "how the ranges were checked" and the Trust screen show the same bindings, so
 * the two cannot say different things.
 */
export const STRETCH = {
  decision: text("stretch.decision", `${STRETCH_PATH}/decision`),
  reason: text("stretch.reason", `${STRETCH_PATH}/reason`),
  rule: text("stretch.rule", `${STRETCH_PATH}/rule`),
  pooledScored: count("stretch.pooled.scored", `${STRETCH_PATH}/pooled/scored_folds`, { unavailable: NOT_COMPARED }),
  pooledSimulated: share("stretch.pooled.simulated", `${STRETCH_PATH}/pooled/coverage_simulated`, { unavailable: NOT_COMPARED }),
  pooledStretched: share("stretch.pooled.stretched", `${STRETCH_PATH}/pooled/coverage_stretched`, { unavailable: NOT_COMPARED }),
  // a row of the three tested horizons (ROWS.stretch)
  months: count("stretch.months", "/horizon_months"),
  eligible: count("stretch.eligible", "/eligible_folds"),
  scored: count("stretch.scored", "/scored_folds"),
  coverageSimulated: share("stretch.coverage.simulated", "/coverage_simulated", { unavailable: NOT_SCORED }),
  coverageStretched: share("stretch.coverage.stretched", "/coverage_stretched", { unavailable: NOT_SCORED }),
  widthSimulated: usd("stretch.width.simulated", "/median_width80_simulated", { unavailable: NOT_SCORED }),
  widthStretched: usd("stretch.width.stretched", "/median_width80_stretched", { unavailable: NOT_SCORED }),
  lower: bind({ id: "stretch.factor.lower", path: "/lower_factor", unit: "quantity", format: "multiple", unavailable: { words: "no width to stretch" } }),
  upper: bind({ id: "stretch.factor.upper", path: "/upper_factor", unit: "quantity", format: "multiple", unavailable: { words: "no width to stretch" } }),
} as const satisfies Record<string, Binding>;

/** What the headline, ranges and tables read for a scenario with no plan. */
export const SIGNED = {
  yearForecast: usd("year.forecast", "/gap/fiscal_year/forecast_rest_of_year", { unavailable: WORDS }),
  yearExpected: usd("year.expected", "/gap/fiscal_year/expected", { unavailable: UNAVAILABLE_FITTED }),
  yearGap: usd("year.gap", "/gap/fiscal_year/gap", { tint: "shortfall", unavailable: WORDS }),
  range80Low: usd("year.range80.low", "/gap/fiscal_year/expected_range80/0", { unavailable: WORDS }),
  range80High: usd("year.range80.high", "/gap/fiscal_year/expected_range80/1", { unavailable: WORDS }),
  range95Low: usd("year.range95.low", "/gap/fiscal_year/expected_range95/0", { unavailable: WORDS }),
  range95High: usd("year.range95.high", "/gap/fiscal_year/expected_range95/1", { unavailable: WORDS }),
  yearRangeStatus: text("year.range.status", `/forecasts/fitted_ranges/horizons/${REST}/status`),
  nextForecast: usd("next12.forecast", "/gap/next_twelve_months/forecast", { unavailable: NO_TARGET }),
  nextGap: usd("next12.gap", "/gap/next_twelve_months/gap", { tint: "shortfall", unavailable: NO_TARGET }),
  twelveTotal: usd("next12.total", `${FITTED_METHOD}/horizons/${TWELVE}`, { unavailable: WORDS }),
  bandsLabel: text("bands.label", "/forecasts/fitted_ranges/by_window_label"),
} as const satisfies Record<string, Binding>;

/** The same, for a scenario with a plan: the core's with-plan figures. */
export const PLANNED = {
  yearForecast: usd("year.forecast", `/plan/with_plan/${REST}`),
  yearExpected: usd("year.expected", "/plan/expected_fiscal_year"),
  yearGap: usd("year.gap", "/plan/gap/fiscal_year/gap_with_plan", { tint: "shortfall" }),
  range80Low: usd("year.range80.low", "/plan/ranges/fiscal_year_expected_range80/0"),
  range80High: usd("year.range80.high", "/plan/ranges/fiscal_year_expected_range80/1"),
  range95Low: usd("year.range95.low", "/plan/ranges/fiscal_year_expected_range95/0"),
  range95High: usd("year.range95.high", "/plan/ranges/fiscal_year_expected_range95/1"),
  yearRangeStatus: text("year.range.status", "/plan/ranges/status"),
  nextForecast: usd("next12.forecast", `${NEXT12_PLAN}/forecast_with_plan`, { unavailable: NO_TARGET }),
  nextGap: usd("next12.gap", `${NEXT12_PLAN}/gap_with_plan`, { tint: "shortfall", unavailable: NO_TARGET }),
  twelveTotal: usd("next12.total", `/plan/with_plan/${TWELVE}`),
  bandsLabel: text("bands.label", "/plan/ranges/status"),
} as const satisfies Record<string, Binding>;

export const ROWS = {
  quarterSigned: "/gap/quarters",
  quarterPlanned: "/plan/with_plan_quarters",
  signedQuarters: "/gap/quarters",
  cell: "/forecasts/fitted_ranges/cells",
  planItem: "/plan/items",
  betterComparisons: "/verdicts/forecast_better_than_baselines/comparisons",
  stretch: `${STRETCH_PATH}/horizons`,
} as const;

/** Every binding on the screen, once per id and place it can read (for the committed list the tests check). */
export const LISTED_BINDINGS: readonly Binding[] = [...Object.values(B), ...Object.values(STRETCH), ...Object.values(SIGNED), ...Object.values(PLANNED)];

// ---------------------------------------------------------------- charts

const METHOD = (name: string) => `/forecasts/methods/{method=${name}}/by_window/{period}`;
const WINDOWS = { arrayAt: "/forecasts/windows" } as const;

export const MONTHLY_METHODS = {
  fitted: "fitted model",
  stage: "stage-weighted pipeline",
  runRate: "trailing run-rate",
} as const;

/** Each plotted series: where its points come from. A plan's fitted line and bands are the with-plan ones. */
export function monthlySeries(planned: boolean) {
  const fitted: SeriesSpec = planned
    ? { key: "fitted", label: "Fitted model, with this scenario", kind: "decimal", path: "/plan/with_plan_by_window/{period}", periods: WINDOWS }
    : { key: "fitted", label: "Fitted model", kind: "decimal", path: METHOD("fitted model"), periods: WINDOWS };
  const range = (key: "range80" | "range95"): string =>
    planned ? `/plan/ranges/by_window/{period}/${key}` : `/forecasts/fitted_ranges/by_window/{period}/${key}`;
  return {
    booked: { key: "booked", label: "Booked", kind: "decimal", path: "/reconciliation/bookings_by_month/{period}", periods: { keysAt: "/reconciliation/bookings_by_month" } },
    signed: { key: "signed", label: "Fitted model, as signed", kind: "decimal", path: METHOD("fitted model"), periods: WINDOWS },
    fitted,
    stage: { key: "stage", label: "Stage-weighted pipeline (no range)", kind: "decimal", path: METHOD("stage-weighted pipeline"), periods: WINDOWS },
    runRate: { key: "runRate", label: "Last twelve months' pace (no range)", kind: "decimal", path: METHOD("trailing run-rate"), periods: WINDOWS },
    band80: { key: "band80", label: "80% range", kind: "range", path: range("range80"), periods: WINDOWS },
    band95: { key: "band95", label: "95% range", kind: "range", path: range("range95"), periods: WINDOWS },
  } as const satisfies Record<string, SeriesSpec>;
}

/** The quarter chart: a with-plan scenario reads the plan's quarters; a closed quarter has no range to draw. */
export function quarterSeries(planned: boolean) {
  const base = planned ? ROWS.quarterPlanned : ROWS.quarterSigned;
  const everyQuarter = { rowsAt: base, property: "quarter" } as const;
  const openQuarters = { rowsAt: base, property: "quarter", unless: ["status", "closed"] } as const;
  return {
    target: { key: "target", label: "Target", kind: "decimal", path: `${base}/{quarter={period}}/target`, periods: everyQuarter },
    expected: { key: "expected", label: "Expected (booked plus forecast)", kind: "decimal", path: `${base}/{quarter={period}}/expected`, periods: everyQuarter },
    range80: { key: "range80", label: "80% range", kind: "range", path: `${base}/{quarter={period}}/expected_range80`, periods: openQuarters },
  } as const satisfies Record<string, SeriesSpec>;
}
