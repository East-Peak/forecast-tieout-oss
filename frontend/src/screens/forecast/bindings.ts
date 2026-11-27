import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";

/**
 * The Forecast screen's committed binding list: every business value the screen shows, with the
 * file, pointer, unit and format it is read through. A row binding (marked in ROWS) is read from
 * each row of a collection in the report. `{scenario}` and `{company}` in a pointer stand for the
 * visitor's current choice. The tests assert this list against independently written expectations.
 */
const REST = "rest of fiscal year";
const TWELVE = "next twelve months";
const FITTED_METHOD = "/forecasts/methods/{method=fitted model}";
const UNAVAILABLE_FITTED = { reason: `${FITTED_METHOD}/unavailable_reason`, absolute: true } as const;

const usd = (id: string, path: string, extra: Partial<Binding> = {}) =>
  bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const text = (id: string, path: string, extra: Partial<Binding> = {}) =>
  bind({ id, path, unit: "text", format: "text", ...extra });

export const B = {
  // header
  fiscalYear: text("fiscal-year", "/inputs/fiscal_year"),
  asOf: bind({ id: "as-of", path: "/inputs/as_of", unit: "date", format: "date" }),
  measure: text("measure", "/inputs/measure"),

  // the year at a glance
  yearTarget: usd("year.target", "/gap/fiscal_year/target"),
  yearActual: usd("year.actual", "/gap/fiscal_year/actual_to_date"),
  yearForecast: usd("year.forecast", "/gap/fiscal_year/forecast_rest_of_year", { unavailable: { words: "unavailable" } }),
  yearExpected: usd("year.expected", "/gap/fiscal_year/expected", { unavailable: UNAVAILABLE_FITTED }),
  yearGap: usd("year.gap", "/gap/fiscal_year/gap", { tint: "shortfall", unavailable: { words: "unavailable" } }),
  range80Low: usd("year.range80.low", "/gap/fiscal_year/expected_range80/0", { unavailable: { words: "unavailable" } }),
  range80High: usd("year.range80.high", "/gap/fiscal_year/expected_range80/1", { unavailable: { words: "unavailable" } }),
  range95Low: usd("year.range95.low", "/gap/fiscal_year/expected_range95/0", { unavailable: { words: "unavailable" } }),
  range95High: usd("year.range95.high", "/gap/fiscal_year/expected_range95/1", { unavailable: { words: "unavailable" } }),
  yearRangeStatus: text("year.range.status", `/forecasts/fitted_ranges/horizons/${REST}/status`),
  nextRangeStatus: text("next12.range.status", `/forecasts/fitted_ranges/horizons/${TWELVE}/status`),
  fittedUnavailable: text("fitted.unavailable-reason", `${FITTED_METHOD}/unavailable_reason`),
  stageUnavailable: text(
    "stage.unavailable-reason",
    "/forecasts/methods/{method=stage-weighted pipeline}/unavailable_reason",
  ),
  runRateUnavailable: text("run-rate.unavailable-reason", "/forecasts/methods/{method=trailing run-rate}/unavailable_reason"),

  // both verdicts, each with its reason
  softwareVerdict: text("verdict.software", "/verdicts/software_correct/verdict"),
  softwareSummary: text("verdict.software.summary", "/verdicts/software_correct/summary"),
  betterVerdict: text("verdict.better", "/verdicts/forecast_better_than_baselines/verdict"),
  betterReason: text("verdict.better.reason", "/verdicts/forecast_better_than_baselines/reason"),

  // the two windows
  nextTarget: usd("next12.target", "/gap/next_twelve_months/target", {
    unavailable: { reason: "/gap/next_twelve_months/untargeted/note", absolute: true },
  }),
  nextActual: usd("next12.actual", "/gap/next_twelve_months/actual", {
    unavailable: { reason: "/gap/next_twelve_months/untargeted/note", absolute: true },
  }),
  nextForecast: usd("next12.forecast", "/gap/next_twelve_months/forecast", {
    unavailable: { reason: "/gap/next_twelve_months/untargeted/note", absolute: true },
  }),
  nextGap: usd("next12.gap", "/gap/next_twelve_months/gap", {
    tint: "shortfall",
    unavailable: { reason: "/gap/next_twelve_months/untargeted/note", absolute: true },
  }),
  nextThrough: bind({
    id: "next12.through",
    path: "/gap/next_twelve_months/targets_through",
    unit: "date",
    format: "date",
    unavailable: { words: "no target in this window" },
  }),
  nextBookingsAlone: usd("next12.untargeted", "/gap/next_twelve_months/untargeted/forecast", {
    unavailable: { words: "unavailable" },
  }),
  nextNote: text("next12.note", "/gap/next_twelve_months/untargeted/note"),

  // a row of the quarter table (read from each of /gap/quarters)
  qName: text("quarter.name", "/quarter"),
  qStatus: text("quarter.status", "/status"),
  qTarget: usd("quarter.target", "/target"),
  qActual: usd("quarter.actual", "/actual"),
  qForecast: usd("quarter.forecast", "/forecast", { unavailable: { words: "unavailable" } }),
  qExpected: usd("quarter.expected", "/expected", { unavailable: { words: "unavailable" } }),
  qGap: usd("quarter.gap", "/gap", { tint: "shortfall", unavailable: { words: "unavailable" } }),
  qRange80Low: usd("quarter.range80.low", "/expected_range80/0", { unavailable: { words: "unavailable" } }),
  qRange80High: usd("quarter.range80.high", "/expected_range80/1", { unavailable: { words: "unavailable" } }),

  // a row of the range back-test (read from each of /forecasts/fitted_ranges/cells)
  cHorizon: bind({ id: "cell.horizon", path: "/horizon_months", unit: "count", format: "count" }),
  cFolds: bind({ id: "cell.folds", path: "/folds_with_a_range", unit: "count", format: "count" }),
  cCoverage80: bind({
    id: "cell.coverage80",
    path: "/coverage80",
    unit: "fraction",
    format: "percent1",
    unavailable: { words: "not scored" },
  }),
  cCoverage95: bind({
    id: "cell.coverage95",
    path: "/coverage95",
    unit: "fraction",
    format: "percent1",
    unavailable: { words: "not scored" },
  }),
  cLabel: text("cell.label", "/label"),
  cJudgement: text("cell.judgement", "/coverage_judgement"),

  // this scenario (from the index and the comparison file; a plan's items from the report)
  scenarioLabel: text("scenario.label", "/companies/{id={company}}/scenarios/{id={scenario}}/label", { source: "index" }),
  scenarioDescription: text("scenario.description", "/companies/{id={company}}/scenarios/{id={scenario}}/description", {
    source: "index",
  }),
  cmpExpected: usd("scenario.expected", "/rows/{scenario={scenario}}/expected_fiscal_year", {
    source: "comparison",
    unavailable: { words: "unavailable" },
  }),
  cmpGap: usd("scenario.gap", "/rows/{scenario={scenario}}/fiscal_year_gap", {
    source: "comparison",
    tint: "shortfall",
    unavailable: { words: "unavailable" },
  }),
  cmpGapChange: usd("scenario.gap-change", "/rows/{scenario={scenario}}/fiscal_year_gap_change", {
    source: "comparison",
    unavailable: { words: "unavailable" },
  }),
  cmpBookingsRest: usd("scenario.bookings.rest", `/rows/{scenario={scenario}}/bookings_change/${REST}`, {
    source: "comparison",
    unavailable: { words: "unavailable" },
  }),
  cmpBookingsNext: usd("scenario.bookings.next12", `/rows/{scenario={scenario}}/bookings_change/${TWELVE}`, {
    source: "comparison",
    unavailable: { words: "unavailable" },
  }),
  cmpCost: usd("scenario.cost", "/rows/{scenario={scenario}}/cash_cost_in_twelve_months", {
    source: "comparison",
    unavailable: { words: "cost not entered" },
  }),
  planUnavailable: text("plan.unavailable", "/plan/unavailable"),
  planDefinition: text("plan.baseline-definition", "/plan/baseline_definition"),
  pItemLabel: text("plan.item.label", "/label"),
  pItemDetail: text("plan.item.detail", "/detail"),
  pItemContribution: usd("plan.item.contribution", `/contribution/${REST}`, { unavailable: { reason: "/note" } }),
  pItemCost: usd("plan.item.cost", "/cash_cost_in_twelve_months", { unavailable: { words: "cost not entered" } }),
} as const satisfies Record<string, Binding>;

/** Where a row binding's collection lives in the report. */
export const ROWS = {
  quarter: "/gap/quarters",
  cell: "/forecasts/fitted_ranges/cells",
  planItem: "/plan/items",
} as const;

/** The row bindings, by collection. */
export const ROW_BINDINGS = {
  quarter: [B.qName, B.qStatus, B.qTarget, B.qActual, B.qForecast, B.qExpected, B.qGap, B.qRange80Low, B.qRange80High],
  cell: [B.cHorizon, B.cFolds, B.cCoverage80, B.cCoverage95, B.cLabel, B.cJudgement],
  planItem: [B.pItemLabel, B.pItemDetail, B.pItemContribution, B.pItemCost],
} as const;

export type ForecastBindings = typeof B;

// ---------------------------------------------------------------- charts

const METHOD = (name: string) => `/forecasts/methods/{method=${name}}/by_window/{period}`;
const WINDOWS = { arrayAt: "/forecasts/windows" } as const;

/** Each plotted series: where its points come from. Only methods the report says are available are drawn. */
export const MONTHLY_SERIES = {
  booked: {
    key: "booked",
    label: "Booked",
    kind: "decimal",
    path: "/reconciliation/bookings_by_month/{period}",
    periods: { keysAt: "/reconciliation/bookings_by_month" },
  },
  fitted: { key: "fitted", label: "Fitted model", kind: "decimal", path: METHOD("fitted model"), periods: WINDOWS },
  stage: {
    key: "stage",
    label: "Stage-weighted (point forecast, no range)",
    kind: "decimal",
    path: METHOD("stage-weighted pipeline"),
    periods: WINDOWS,
  },
  runRate: {
    key: "runRate",
    label: "Trailing run-rate (point forecast, no range)",
    kind: "decimal",
    path: METHOD("trailing run-rate"),
    periods: WINDOWS,
  },
  band80: {
    key: "band80",
    label: "80% range",
    kind: "range",
    path: "/forecasts/fitted_ranges/by_window/{period}/range80",
    periods: WINDOWS,
  },
  band95: {
    key: "band95",
    label: "95% range",
    kind: "range",
    path: "/forecasts/fitted_ranges/by_window/{period}/range95",
    periods: WINDOWS,
  },
} as const satisfies Record<string, SeriesSpec>;

export const MONTHLY_METHODS = {
  fitted: "fitted model",
  stage: "stage-weighted pipeline",
  runRate: "trailing run-rate",
} as const;

export const QUARTER_SERIES = {
  target: {
    key: "target",
    label: "Target",
    kind: "decimal",
    path: "/gap/quarters/{quarter={period}}/target",
    periods: { rowsAt: "/gap/quarters", property: "quarter" },
  },
  expected: {
    key: "expected",
    label: "Expected (booked plus forecast)",
    kind: "decimal",
    path: "/gap/quarters/{quarter={period}}/expected",
    periods: { rowsAt: "/gap/quarters", property: "quarter" },
  },
  range80: {
    key: "range80",
    label: "80% range",
    kind: "range",
    path: "/gap/quarters/{quarter={period}}/expected_range80",
    periods: { rowsAt: "/gap/quarters", property: "quarter" },
  },
} as const satisfies Record<string, SeriesSpec>;
