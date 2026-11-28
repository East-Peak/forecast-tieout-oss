import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";

/**
 * The win-rate actions' committed binding list: what the plan editor shows beside an action (the pooled baseline and the
 * worksheet's low and high, the core's figures for an applied action) and what the Plan screen's Actions block shows after
 * Apply. Everything is read from the report's `driver_actions` section and the worksheet's win-rate driver, as the core wrote
 * them: the browser adds, subtracts and compares nothing, so the change in points is the core's, not the form's.
 * A row binding is read from `/driver_actions/items/{i}`. The tests assert this list against independently written expectations.
 */
const SECTION = "/driver_actions";
const WIN_RATE = "/worksheet/drivers/{driver=win_rate}";
const REST = "rest of fiscal year";
const TWELVE = "next twelve months";

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const rate = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "fraction", format: "percent1", ...extra });
const points = (id: string, path: string) => bind({ id, path, unit: "quantity", format: "decimal2" });
const words = (w: string) => ({ words: w }) as const;

/** What the form shows beside an action's target, read from the worksheet's win-rate driver: where the pooled rate stands and the worksheet's low and high settings. */
export const FORM = {
  line: text("driver-actions.form.line", `${WIN_RATE}/applies_to`),
  baseline: rate("driver-actions.form.baseline", `${WIN_RATE}/current/value`, { unavailable: words("no baseline") }),
  low: rate("driver-actions.form.low", `${WIN_RATE}/historical/low/setting`, { unavailable: words("not offered") }),
  high: rate("driver-actions.form.high", `${WIN_RATE}/historical/high/setting`, { unavailable: words("not offered") }),
} as const;

/** One action's own evidence, read from `/driver_actions/items/{i}`: the core's change in points, the resulting rate, and where the target sits against the worksheet. */
export const EVIDENCE = {
  change: points("driver-actions.item.change-points", "/evidence/change_points"),
  resulting: rate("driver-actions.item.resulting", "/evidence/resulting_rate"),
  low: rate("driver-actions.item.low", "/evidence/historical_low", { unavailable: words("not offered") }),
  high: rate("driver-actions.item.high", "/evidence/historical_high", { unavailable: words("not offered") }),
  label: text("driver-actions.item.label", "/evidence/label"),
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

export const DRIVER_ACTION_BINDINGS: readonly Binding[] = [...Object.values(FORM), ...Object.values(EVIDENCE), ...Object.values(BLOCK)];
