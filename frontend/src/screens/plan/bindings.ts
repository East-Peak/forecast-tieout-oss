import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { DRIVER_ACTION_BINDINGS } from "./driverActionBindings";

/**
 * The Plan screen's committed binding list: every business value the screen shows, with the file,
 * pointer, unit and format it is read through. A row binding is read from each row of a collection (ROWS);
 * `{company}` and `{scenario}` in a pointer stand for the visitor's current choice. The differences between
 * scenarios are read from comparison.json, which the core's generator writes: the browser subtracts nothing.
 * The tests assert this list against independently written expectations.
 */
const REST = "rest of fiscal year";
const TWELVE = "next twelve months";
const PLAN = "/plan";
const CLOSE = "/actions/close_the_fiscal_year_gap";
const ME = "/rows/{scenario={scenario}}";
const SCENARIO = "/companies/{id={company}}/scenarios/{id={scenario}}";

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const count = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "count", format: "count", ...extra });
const multiple = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "quantity", format: "multiple", ...extra });
const words = (w: string) => ({ words: w }) as const;
const cmp = { source: "comparison" } as const;
/** A missing figure says why in the report's own sentence for it, or in these words where it gives none. */
const why = (reason: string, fallback: string) => ({ reason, sentence: true, words: fallback }) as const;

export const B = {
  fiscalYear: text("fiscal-year", "/inputs/fiscal_year"),
  asOf: bind({ id: "as-of", path: "/inputs/as_of", unit: "date", format: "date" }),

  // the scenarios to pick from, and the one picked (index.json)
  pickLabel: text("pick.label", "/label", { source: "index" }),
  scenarioDescription: text("scenario.description", `${SCENARIO}/description`, { source: "index" }),

  // the plan, in one line: this scenario against as signed (comparison.json)
  planUnavailable: text("plan.unavailable", `${PLAN}/unavailable`),
  cmpNote: text("plan.note", `${ME}/note`, cmp),

  rangeStatus: text("plan.ranges.status", `${PLAN}/ranges/status`),
  rangeDrawn: text("plan.ranges.drawn", `${PLAN}/ranges/what_is_drawn`),

  // the gap to target, as signed and with this scenario
  gapFyBase: usd("gap.year.as-signed", `${PLAN}/gap/fiscal_year/baseline_gap`, { tint: "shortfall" }),
  gapFyPlan: usd("gap.year.with-plan", `${PLAN}/gap/fiscal_year/gap_with_plan`, { tint: "shortfall" }),
  gapNextBase: usd("gap.next12.as-signed", `${PLAN}/gap/next_twelve_months/baseline_gap`, { tint: "shortfall", unavailable: words("no target in this window") }),
  gapNextPlan: usd("gap.next12.with-plan", `${PLAN}/gap/next_twelve_months/gap_with_plan`, { tint: "shortfall", unavailable: words("no target in this window") }),
  gapNextNote: text("gap.next12.note", `${PLAN}/gap/next_twelve_months/note`, { unavailable: words("no target in this window") }),

  // a row of the plan's items
  iLabel: text("item.label", "/label"),
  iDetail: text("item.detail", "/detail"),
  iRest: usd("item.contribution.rest", `/contribution/${REST}`, { unavailable: { reason: "/note" } }),
  iNext: usd("item.contribution.next12", `/contribution/${TWELVE}`, { unavailable: words("not valued") }),
  iCost: usd("item.cost", "/cash_cost_in_twelve_months", { unavailable: words("cost not entered") }),
  iSchedule: text("item.schedule", "/payment_schedule"),
  itemsCost: usd("items.cost", `${PLAN}/cash_cost_in_twelve_months`, { unavailable: words("cost not entered") }),
  itemsRest: usd("items.total.rest", `${ME}/bookings_change/${REST}`, { ...cmp, unavailable: words("not valued") }),
  itemsNext: usd("items.total.next12", `${ME}/bookings_change/${TWELVE}`, { ...cmp, unavailable: words("not valued") }),
  itemsOrder: text("items.order", `${PLAN}/order`),
  itemsCostNote: text("items.cost-note", `${PLAN}/cost_note`),

  // the two unit actions, compared (a row of the comparison)
  actionsUnavailable: text("actions.unavailable", "/actions/unavailable"),
  actionsDefinition: text("actions.definition", "/actions/definition"),
  actionsMeaning: text("actions.meaning", "/actions/meaning"),
  actionsShape: text("actions.program-shape", "/actions/program_shape"),
  aStatus: text("action.status", "/status"),
  aRank: count("action.rank", "/rank", { unavailable: words("not ranked") }),
  aNext: usd("action.gain.next12", `/bookings_gained/${TWELVE}`, { unavailable: { reason: "/not_ranked_because", words: "unavailable" } }),
  aRest: usd("action.gain.rest", `/bookings_gained/${REST}`, { unavailable: { reason: "/not_ranked_because", words: "unavailable" } }),
  aCost: usd("action.cost", "/cash_cost_in_twelve_months", { unavailable: { reason: "/not_ranked_because", words: "unavailable" } }),
  aPerDollar: multiple("action.per-dollar", "/gain_per_dollar", { unavailable: { reason: "/not_ranked_because", words: "unavailable" } }),
  aStarts: bind({ id: "action.starts-paying", path: "/starts_paying", unit: "month", format: "month", unavailable: { reason: "/not_ranked_because", words: "not within the window" } }),

  // what closes the gap alone
  closeBasis: text("close.basis", `${CLOSE}/basis`),
  closeGap: usd("close.gap", `${CLOSE}/fiscal_year_gap`, { tint: "shortfall" }),
  hiresOutcome: text("close.hires.outcome", `${CLOSE}/hires/outcome`),
  hiresNote: text("close.hires.note", `${CLOSE}/hires/note`),
  hiresCount: count("close.hires.count", `${CLOSE}/hires/count`, { unavailable: words("no number of hires closes it") }),
  hiresBound: count("close.hires.bound", `${CLOSE}/hires/bound`),
  hiresBoundBasis: text("close.hires.bound-basis", `${CLOSE}/hires/bound_basis`),
  hiresCost: usd("close.hires.cost", `${CLOSE}/hires/cash_cost_in_twelve_months`, { unavailable: why(`${CLOSE}/hires/cash_cost_note`, "unavailable") }),
  programOutcome: text("close.program.outcome", `${CLOSE}/program/outcome`),
  programDollars: usd("close.program.dollars", `${CLOSE}/program/dollars`, { unavailable: words("no amount closes it within the cap") }),
  programCap: usd("close.program.cap", `${CLOSE}/program/cap`),
  programOver: usd("close.program.over-cap", `${CLOSE}/program/needed_but_over_the_cap`),
  programCost: usd("close.program.cost", `${CLOSE}/program/cash_cost_in_twelve_months`, { unavailable: why(`${CLOSE}/program/cash_cost_note`, "unavailable") }),

  // every scenario side by side (a row of comparison.json)
  sLabel: text("compare.label", "/label", cmp),
  sExpected: usd("compare.expected", "/expected_fiscal_year", { ...cmp, unavailable: words("unavailable") }),
  sGap: usd("compare.gap", "/fiscal_year_gap", { ...cmp, tint: "shortfall", unavailable: words("unavailable") }),
  sGapChange: usd("compare.gap-change", "/fiscal_year_gap_change", { ...cmp, tint: "shortfall", unavailable: words("no plan") }),
  sRest: usd("compare.more.rest", `/bookings_change/${REST}`, { ...cmp, unavailable: words("no plan") }),
  sNext: usd("compare.more.next12", `/bookings_change/${TWELVE}`, { ...cmp, unavailable: words("no plan") }),
  sGapChangeNv: usd("compare.gap-change.not-valued", "/fiscal_year_gap_change", { ...cmp, tint: "shortfall", unavailable: words("not valued") }),
  sRestNv: usd("compare.more.rest.not-valued", `/bookings_change/${REST}`, { ...cmp, unavailable: words("not valued") }),
  sNextNv: usd("compare.more.next12.not-valued", `/bookings_change/${TWELVE}`, { ...cmp, unavailable: words("not valued") }),
  sNote: text("compare.note", "/note", cmp),
  sCost: usd("compare.cost", "/cash_cost_in_twelve_months", { ...cmp, unavailable: words("cost not entered") }),
  sCostNone: usd("compare.cost.none", "/cash_cost_in_twelve_months", { ...cmp, unavailable: words("no plan, no cost") }),
} as const satisfies Record<string, Binding>;

/** As signed against this scenario in one window: the figures, each with its 80% and 95% range. */
function forWindow(key: string, window: string) {
  const range = (id: string, path: string) => usd(`window.${key}.${id}`, path);
  return {
    asSigned: usd(`window.${key}.as-signed`, `${PLAN}/baseline/${window}`),
    withPlan: usd(`window.${key}.with-plan`, `${PLAN}/with_plan/${window}`),
    gain: usd(`window.${key}.gain`, `${ME}/bookings_change/${window}`, { ...cmp, unavailable: words("not valued") }),
    base80Low: range("as-signed.range80.low", `/forecasts/fitted_ranges/horizons/${window}/range80/0`),
    base80High: range("as-signed.range80.high", `/forecasts/fitted_ranges/horizons/${window}/range80/1`),
    base95Low: range("as-signed.range95.low", `/forecasts/fitted_ranges/horizons/${window}/range95/0`),
    base95High: range("as-signed.range95.high", `/forecasts/fitted_ranges/horizons/${window}/range95/1`),
    plan80Low: range("with-plan.range80.low", `${PLAN}/ranges/bookings_in_window/${window}/range80/0`),
    plan80High: range("with-plan.range80.high", `${PLAN}/ranges/bookings_in_window/${window}/range80/1`),
    plan95Low: range("with-plan.range95.low", `${PLAN}/ranges/bookings_in_window/${window}/range95/0`),
    plan95High: range("with-plan.range95.high", `${PLAN}/ranges/bookings_in_window/${window}/range95/1`),
  } as const satisfies Record<string, Binding>;
}

export const W = { rest: forWindow("rest", REST), next12: forWindow("next12", TWELVE) } as const;

export const ROWS = {
  scenarios: "/companies/{id={company}}/scenarios",
  items: `${PLAN}/items`,
  actions: "/actions/comparison",
  compare: "/rows",
} as const;

export const LISTED_BINDINGS: readonly Binding[] = [...Object.values(B), ...Object.values(W.rest), ...Object.values(W.next12), ...DRIVER_ACTION_BINDINGS];
