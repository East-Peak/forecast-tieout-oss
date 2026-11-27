import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";

/**
 * The planning worksheet's committed binding list: every figure and sentence of the landing screen's worksheet,
 * with the file, pointer, unit and format it is read through. The worksheet is one section of the report
 * (`/worksheet`), written by the core; the browser draws and says it, and adds, sorts and ranks nothing.
 * A row binding is read from each row of a collection (WS_ROWS), by its position in the report. A driver's
 * figures come in three display kinds (a share, dollars, a plain quantity), chosen by the report's own `display`.
 * The tests assert this list against independently written expectations.
 */
const SHEET = "/worksheet";
export const WINDOWS = ["rest of fiscal year", "next twelve months"] as const;
export type Window = (typeof WINDOWS)[number];
const DISPLAYS = ["percent", "money", "decimal"] as const;
export type Display = (typeof DISPLAYS)[number];

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const count = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "count", format: "count", ...extra });
const words = (w: string) => ({ words: w }) as const;

/** The same figure in the three ways a driver can be displayed: its ids end in the display kind. */
function byDisplay(id: string, path: string, extra: Partial<Binding> = {}): Record<Display, Binding> {
  return {
    percent: bind({ id: `${id}.percent`, path, unit: "fraction", format: "percent1", ...extra }),
    money: bind({ id: `${id}.money`, path, unit: "usd", format: "usd-short", ...extra }),
    decimal: bind({ id: `${id}.decimal`, path, unit: "quantity", format: "decimal2", ...extra }),
  };
}

export const WS = {
  unavailable: text("worksheet.unavailable", `${SHEET}/unavailable`),

  // the summary row
  target: usd("worksheet.summary.target", `${SHEET}/summary/fiscal_year_target/value`),
  asSigned: usd("worksheet.summary.as-signed", `${SHEET}/summary/as_signed/value`),
  workingPlan: usd("worksheet.summary.working-plan", `${SHEET}/summary/working_plan/value`),
  remainingGap: usd("worksheet.summary.remaining-gap", `${SHEET}/summary/remaining_gap/value`, { tint: "shortfall" }),
  gain: usd("worksheet.summary.twelve-month-gain", `${SHEET}/summary/twelve_month_gain/value`, { unavailable: words("not valued") }),
  /** a plan with nothing valued has a gain of zero in the worksheet's summary; the comparison file says "not valued", and the screen says that */
  gainNotValued: usd("worksheet.summary.twelve-month-gain.not-valued", "/rows/{scenario={scenario}}/bookings_change/next twelve months", { source: "comparison", unavailable: words("not valued") }),
  cost: usd("worksheet.summary.cash-cost", `${SHEET}/summary/cash_cost_in_twelve_months/value`, { unavailable: words("cost not entered") }),
  noPlanNote: text("worksheet.summary.no-plan-note", `${SHEET}/summary/no_plan_note`),

  // the sentences that go with the chart
  definition: text("worksheet.definition", `${SHEET}/definition`),
  measuredAround: text("worksheet.measured-around", `${SHEET}/measured_around`),
  historyNote: text("worksheet.history-note", `${SHEET}/history_note`),
  sensitivityNote: text("worksheet.sensitivity-note", `${SHEET}/sensitivity_note`),
  expectationNote: text("worksheet.expectation-note", `${SHEET}/expectation_note`),

  // the bridge
  bridgeMeasure: text("worksheet.bridge.measure", `${SHEET}/bridge/measure`),
  bridgeOrder: text("worksheet.bridge.order", `${SHEET}/bridge/order`),
  bridgeTarget: usd("worksheet.bridge.target", `${SHEET}/bridge/target/value`),

  // the as-signed chain
  chainNote: text("worksheet.chain.note", `${SHEET}/chain/note`),
  chainUnavailable: text("worksheet.chain.unavailable", `${SHEET}/chain/unavailable`),



} as const satisfies Record<string, Binding>;

/** A driver, read from `/worksheet/drivers/{i}`. */
export const DRIVER = {
  label: text("driver.label", "/label"),
  unitLabel: text("driver.unit-label", "/unit_label"),
  current: byDisplay("driver.current", "/current/value", { unavailable: { reason: "/cannot_scale_because", sentence: true, words: "no figure" } }),
  lowSetting: byDisplay("driver.low.setting", "/historical/low/setting"),
  highSetting: byDisplay("driver.high.setting", "/historical/high/setting"),
  lowChange: {
    "rest of fiscal year": usd("driver.low.change.rest", "/historical/low/change/rest of fiscal year"),
    "next twelve months": usd("driver.low.change.next12", "/historical/low/change/next twelve months"),
  },
  highChange: {
    "rest of fiscal year": usd("driver.high.change.rest", "/historical/high/change/rest of fiscal year"),
    "next twelve months": usd("driver.high.change.next12", "/historical/high/change/next twelve months"),
  },
  unavailable: text("driver.history-unavailable", "/historical_unavailable_because"),
  minimum: byDisplay("driver.minimum", "/historical/minimum"),
  maximum: byDisplay("driver.maximum", "/historical/maximum"),
  rule: text("driver.rule", "/historical/rule"),
  appliesTo: text("driver.applies-to", "/applies_to"),
  limitation: text("driver.limitation", "/limitation"),
  gate: text("driver.gate", "/evidence/gate"),
  eligible: count("driver.eligible-quarters", "/evidence/eligible_quarters"),
  required: count("driver.required-quarters", "/evidence/required_quarters"),
  neededValue: byDisplay("driver.needed.value", "/needed_alone/value"),
  /** a driver the history cannot scale has no "needed alone"; the report says why */
  neededNone: text("driver.needed.none", "/needed_alone/outcome_label", { unavailable: { reason: "/cannot_scale_because", sentence: true, words: "no figure" } }),
  precision: text("driver.needed.precision", "/needed_alone/precision_note"),
  neededLabel: text("driver.needed.label", "/needed_alone/outcome_label"),
  neededReason: text("driver.needed.reason", "/needed_alone/reason_label"),
  overshoot: usd("driver.needed.overshoot", "/needed_alone/overshoot"),
  history: text("driver.inside-history", "/needed_alone/history_label", { unavailable: words("not compared with history") }),
} as const;

/** One past quarter of a driver's evidence, read from `/worksheet/drivers/{i}/evidence/quarters/{j}`. */
export const OBSERVATION = {
  quarter: text("observation.quarter", "/quarter"),
  created: count("observation.created", "/created"),
  wins: count("observation.wins", "/wins"),
  value: byDisplay("observation.value", "/value", { unavailable: { reason: "/not_eligible_because", sentence: true, words: "not counted" } }),
} as const;

/** One of the two actions, read from `/worksheet/actions/rows/{i}`. */
export const ACTION = {
  name: text("action.worksheet.name", "/action/value"),
  gain: {
    "rest of fiscal year": usd("action.worksheet.gain.rest", "/bookings_gained/value/rest of fiscal year", { unavailable: { reason: "/status/value", sentence: true, words: "unsupported by this history" } }),
    "next twelve months": usd("action.worksheet.gain.next12", "/bookings_gained/value/next twelve months", { unavailable: { reason: "/status/value", sentence: true, words: "unsupported by this history" } }),
  },
  closes: text("action.worksheet.closes", "/closes_alone_label"),
  outcome: text("action.worksheet.outcome", "/closes_alone_outcome/value"),
} as const;

/** One step of the bridge, read from `/worksheet/bridge/steps/{i}`. */
export const STEP = {
  label: text("step.label", "/label"),
  level: usd("step.level", "/to"),
  change: usd("step.change", "/change", { unavailable: words("not valued") }),
  note: text("step.note", "/note"),
} as const;

/** Where the quarter table reads: the as-signed quarter, and the working plan's. */
export const QUARTER = {
  quarter: text("quarter.name", "/quarter"),
  target: usd("quarter.target", "/target"),
  asSigned: usd("quarter.as-signed", "/expected", { unavailable: words("unavailable") }),
  /** the working plan's quarter: read from the plan's own quarters, or from the as-signed ones where no plan is in force */
  planned: usd("quarter.planned", "/expected", { unavailable: words("unavailable") }),
  remainingGap: usd("quarter.remaining-gap", "/gap", { tint: "shortfall", unavailable: words("unavailable") }),
} as const;

/** One remaining quarter of the as-signed chain, read from `/worksheet/chain/quarters/{i}`. */
export const CHAIN = {
  quarter: text("chain.quarter", "/quarter"),
  status: text("chain.status", "/status/value"),
  bookingsTarget: usd("chain.bookings.target", "/bookings/target/value"),
  bookingsExpected: usd("chain.bookings.expected", "/bookings/expected/value", { unavailable: words("unavailable") }),
  bookingsGap: usd("chain.bookings.gap", "/bookings/gap/value", { tint: "shortfall", unavailable: words("unavailable") }),
  pipelineRequired: usd("chain.pipeline.required", "/created_pipeline/required/value", { unavailable: { reason: "/created_pipeline/required_note/value", sentence: true, words: "no figure" } }),
  pipelineExpected: usd("chain.pipeline.expected", "/created_pipeline/expected/value"),
  pipelineHeadline: text("chain.pipeline.headline", "/created_pipeline/headline/value"),
  perRequired: usd("chain.per-ae.required", "/per_ramped_ae_month/required/value", { unavailable: { reason: "/per_ramped_ae_month/note/value", sentence: true, words: "no figure" } }),
  perExpected: usd("chain.per-ae.expected", "/per_ramped_ae_month/expected/value", { unavailable: { reason: "/per_ramped_ae_month/note/value", sentence: true, words: "no figure" } }),
  timingLabel: text("chain.timing.label", "/timing/label/value"),
  timingReason: text("chain.timing.reason", ""),
} as const;

export const WS_ROWS = {
  drivers: `${SHEET}/drivers`,
  actions: `${SHEET}/actions/rows`,
  steps: `${SHEET}/bridge/steps`,
  chain: `${SHEET}/chain/quarters`,
  gapQuarters: "/gap/quarters",
  plannedQuarters: "/plan/with_plan_quarters",
} as const;

/** The two bars of a driver, in a window: the change at its historical low and high settings. */
export function driverSeries(window: Window): { low: SeriesSpec; high: SeriesSpec } {
  const periods = { indexesAt: `${SHEET}/drivers` } as const;
  return {
    low: { key: "low", label: "At its historical low", kind: "bar", path: `${SHEET}/drivers/{period}/historical/low/change/${window}`, periods, nullable: true },
    high: { key: "high", label: "At its historical high", kind: "bar", path: `${SHEET}/drivers/{period}/historical/high/change/${window}`, periods, nullable: true },
  };
}

/** The one bar of each action, in a window; an action the history does not support has none. */
export function actionSeries(window: Window): { gain: SeriesSpec } {
  return {
    gain: { key: "gain", label: "One unit", kind: "bar", path: `${SHEET}/actions/rows/{period}/bookings_gained/value/${window}`, periods: { indexesAt: `${SHEET}/actions/rows` }, nullable: true },
  };
}

/**
 * The bridge's bars: the two totals stand on the scale's floor, each item floats from where the one above it
 * ended to where it ends (the file's own `from` and `to`), and the remaining gap floats from the working plan to the target.
 */
export const BRIDGE_SERIES = {
  total: { key: "total", label: "Total", kind: "decimal", path: `${SHEET}/bridge/steps/{period}/to`, periods: { indexesAt: `${SHEET}/bridge/steps`, where: ["kind", ["as_signed", "working_plan"]] } },
  move: {
    key: "move",
    label: "Plan item",
    kind: "span",
    path: `${SHEET}/bridge/steps/{period}/to`,
    from: `${SHEET}/bridge/steps/{period}/from`,
    periods: { indexesAt: `${SHEET}/bridge/steps`, where: ["kind", ["hires", "program"]] },
  },
  gap: {
    key: "gap",
    label: "Remaining gap",
    kind: "span",
    path: `${SHEET}/bridge/target/value`,
    from: `${SHEET}/bridge/steps/{kind=working_plan}/to`,
    periods: { indexesAt: `${SHEET}/bridge/steps`, where: ["kind", ["remaining_gap"]] },
  },
} as const satisfies Record<string, SeriesSpec>;

function everyBinding(): Binding[] {
  const flat = (o: Record<string, unknown>): Binding[] =>
    Object.values(o).flatMap((v) => (v && typeof v === "object" && "id" in v ? [v as Binding] : flat(v as Record<string, unknown>)));
  return [...flat(WS), ...flat(DRIVER), ...flat(OBSERVATION), ...flat(ACTION), ...flat(STEP), ...flat(QUARTER), ...flat(CHAIN)];
}

export const WORKSHEET_BINDINGS: readonly Binding[] = everyBinding();
