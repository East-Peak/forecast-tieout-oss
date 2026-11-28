import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";

/**
 * The driver actions' committed binding list: what the plan editor shows beside an action (the pooled baseline and the
 * worksheet's low and high for the action's driver, the core's figures for an applied action) and what the Plan screen's Actions
 * block shows after Apply. Everything is read from the report's `driver_actions` section and the worksheet's driver rows, as the core wrote
 * them: the browser adds, subtracts and compares nothing, so the change in points is the core's, not the form's.
 * A row binding is read from `/driver_actions/items/{i}`. The tests assert this list against independently written expectations.
 */
const SECTION = "/driver_actions";
const WIN_RATE = "/worksheet/drivers/{driver=win_rate}";
const SIZE = "/worksheet/drivers/{driver=won_arr}";
const CREATION = "/worksheet/drivers/{driver=productivity}";
const CYCLE = "/worksheet/drivers/{driver=cycle_days}";
const REST = "rest of fiscal year";
const TWELVE = "next twelve months";

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const rate = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "fraction", format: "percent1", ...extra });
const dollars = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const deals = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "quantity", format: "decimal2", ...extra });
const points = (id: string, path: string) => bind({ id, path, unit: "quantity", format: "decimal2" });
const words = (w: string) => ({ words: w }) as const;

/** What the form shows beside an action's target, read from the worksheet's win-rate driver: where the pooled rate stands and the worksheet's low and high settings. */
export const FORM = {
  /** what an action is: the report's sentence, which the section carries even when the plan holds no action */
  line: text("driver-actions.form.line", `${SECTION}/line`),
  baseline: rate("driver-actions.form.baseline", `${WIN_RATE}/current/value`, { unavailable: words("no baseline") }),
  low: rate("driver-actions.form.low", `${WIN_RATE}/historical/low/setting`, { unavailable: words("not offered") }),
  high: rate("driver-actions.form.high", `${WIN_RATE}/historical/high/setting`, { unavailable: words("not offered") }),
} as const;

/** The same beside an action on the size of a win (dollars per won deal) and on creation (deals per ramped AE-month, or per day), each with the unit the worksheet gives. */
const FORM_SIZE = {
  baseline: dollars("driver-actions.form.won_arr.baseline", `${SIZE}/current/value`, { unavailable: words("no baseline") }),
  low: dollars("driver-actions.form.won_arr.low", `${SIZE}/historical/low/setting`, { unavailable: words("not offered") }),
  high: dollars("driver-actions.form.won_arr.high", `${SIZE}/historical/high/setting`, { unavailable: words("not offered") }),
  unit: text("driver-actions.form.won_arr.unit", `${SIZE}/unit_label`),
} as const;
const FORM_CREATION = {
  baseline: deals("driver-actions.form.productivity.baseline", `${CREATION}/current/value`, { unavailable: words("no baseline") }),
  low: deals("driver-actions.form.productivity.low", `${CREATION}/historical/low/setting`, { unavailable: words("not offered") }),
  high: deals("driver-actions.form.productivity.high", `${CREATION}/historical/high/setting`, { unavailable: words("not offered") }),
  unit: text("driver-actions.form.productivity.unit", `${CREATION}/unit_label`),
} as const;

/** And beside an action on the cycle: the pooled mean days from creation to win and the worksheet's low and high, in days. */
const FORM_CYCLE = {
  baseline: deals("driver-actions.form.cycle_days.baseline", `${CYCLE}/current/value`, { unavailable: words("no baseline") }),
  low: deals("driver-actions.form.cycle_days.low", `${CYCLE}/historical/low/setting`, { unavailable: words("not offered") }),
  high: deals("driver-actions.form.cycle_days.high", `${CYCLE}/historical/high/setting`, { unavailable: words("not offered") }),
  unit: text("driver-actions.form.cycle_days.unit", `${CYCLE}/unit_label`),
} as const;

/** What the form reads for each driver's action. */
export const FORM_BY_DRIVER = { win_rate: FORM, won_arr: FORM_SIZE, productivity: FORM_CREATION, cycle_days: FORM_CYCLE } as const;

/** One action's own evidence, read from `/driver_actions/items/{i}`: the core's change in points, the resulting rate, and where the target sits against the worksheet. */
export const EVIDENCE = {
  change: points("driver-actions.item.change-points", "/evidence/change_points"),
  resulting: rate("driver-actions.item.resulting", "/evidence/resulting_rate"),
  low: rate("driver-actions.item.low", "/evidence/historical_low", { unavailable: words("not offered") }),
  high: rate("driver-actions.item.high", "/evidence/historical_high", { unavailable: words("not offered") }),
  label: text("driver-actions.item.label", "/evidence/label"),
} as const;

/** The evidence of an action on the size of a win or on creation: the core's percent on the baseline, the resulting value, and where it sits against the worksheet (the label above is shared). */
export const EVIDENCE_AMOUNT = {
  changePercent: deals("driver-actions.item.change-percent", "/evidence/change_percent"),
  resultingSize: dollars("driver-actions.item.resulting.won_arr", "/evidence/resulting"),
  resultingCreation: deals("driver-actions.item.resulting.productivity", "/evidence/resulting"),
  resultingCycle: deals("driver-actions.item.resulting.cycle_days", "/evidence/resulting"),
} as const;

/** The Actions block, after Apply. */
export const BLOCK = {
  definition: text("driver-actions.definition", `${SECTION}/definition`),
  name: text("driver-actions.item.name", "/name"),
  affects: text("driver-actions.item.affects", "/affects"),
  removedRest: usd("driver-actions.item.removal.rest", `/removal_value/${REST}`),
  removedNext: usd("driver-actions.item.removal.next12", `/removal_value/${TWELVE}`),
  removalLabel: text("driver-actions.removal-label", `${SECTION}/removal_label`),
  jointRest: usd("driver-actions.joint.rest", `${SECTION}/joint_gain/${REST}`),
  jointNext: usd("driver-actions.joint.next12", `${SECTION}/joint_gain/${TWELVE}`),
  reconRest: usd("driver-actions.reconciliation.rest", `${SECTION}/reconciliation/values/${REST}`),
  reconNext: usd("driver-actions.reconciliation.next12", `${SECTION}/reconciliation/values/${TWELVE}`),
  reconSentenceRest: text("driver-actions.reconciliation.sentence.rest", `${SECTION}/reconciliation/sentences/${REST}`),
  reconSentenceNext: text("driver-actions.reconciliation.sentence.next12", `${SECTION}/reconciliation/sentences/${TWELVE}`),
  withYear: usd("driver-actions.with.year", `${SECTION}/with_actions/expected_fiscal_year`),
  withNext: usd("driver-actions.with.next12", `${SECTION}/with_actions/bookings/${TWELVE}`),
  withoutYear: usd("driver-actions.without.year", `${SECTION}/without_actions/expected_fiscal_year`),
  withoutNext: usd("driver-actions.without.next12", `${SECTION}/without_actions/bookings/${TWELVE}`),
  removalNote: text("driver-actions.removal-note", `${SECTION}/removal_note`),
  rangeNote: text("driver-actions.range-note", `${SECTION}/range_note`),
  roundingNote: text("driver-actions.rounding-note", `${SECTION}/rounding_note`),
} as const;

/** Where the block's rows are read from. */
export const DA_ROWS = { items: `${SECTION}/items` } as const;

export const DRIVER_ACTION_BINDINGS: readonly Binding[] = [
  ...Object.values(FORM),
  ...Object.values(FORM_SIZE),
  ...Object.values(FORM_CREATION),
  ...Object.values(FORM_CYCLE),
  ...Object.values(EVIDENCE),
  ...Object.values(EVIDENCE_AMOUNT),
  ...Object.values(BLOCK),
];

/** What each driver is called beside an action (a name, not a figure). */
export const DRIVER_CHOICE = { win_rate: "Win rate", won_arr: "Won ARR per win", productivity: "Creation productivity", cycle_days: "Cycle length" } as const;
