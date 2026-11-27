import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";

/**
 * The Pipeline screen's committed binding list: every business value the screen shows, with the file,
 * pointer, unit and format it is read through. A row binding is read from each row of a collection (ROWS).
 * The tests assert this list against independently written expectations.
 */
const RP = "/required_pipeline";
const FLOW = "/reconciliation/pipeline_flow";

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const count = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "count", format: "count", ...extra });
const cents = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "quantity", format: "cents", ...extra });
const multiple = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "quantity", format: "multiple", ...extra });
const share = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "fraction", format: "percent1", ...extra });
const date = (id: string, path: string) => bind({ id, path, unit: "date", format: "date" });
const words = (w: string) => ({ words: w }) as const;

export const B = {
  fiscalYear: text("fiscal-year", "/inputs/fiscal_year"),
  asOf: date("as-of", "/inputs/as_of"),

  // the answer: what must be created, and which quarters are too late
  requiredUnavailable: text("required.unavailable", `${RP}/unavailable`),
  fyHeadline: text("required.headline", `${RP}/fiscal_year/headline`),
  fySolvableTotal: usd("required.solvable-total", `${RP}/fiscal_year/solvable_total`, { unavailable: words("no quarter can be solved") }),
  fySpread: text("required.single-spread", `${RP}/fiscal_year/single_spread/headline`, { unavailable: words("unavailable") }),
  fyWhyDiffer: text("required.why-differ", `${RP}/fiscal_year/why_they_differ`),

  // the open pipeline, beside the headline
  openArr: usd("open-now.arr", `${FLOW}/open at as-of/arr`),
  openCount: count("open-now.count", `${FLOW}/open at as-of/count`),

  // the pipeline flow for the year (a row of FLOW)
  flowCount: count("flow.count", "/count"),
  flowArr: usd("flow.arr", "/arr"),

  // a row of the quarter table
  qName: text("quarter.name", "/quarter"),
  qStatus: text("quarter.status", "/status"),
  qTarget: usd("quarter.target", "/target"),
  qActual: usd("quarter.actual", "/actual"),
  qWithout: usd("quarter.without-own", "/bookings_without_own_pipeline"),
  qHeadline: text("quarter.headline", "/headline"),
  qRequired: usd("quarter.required", "/required_extra_pipeline"),
  qRequiredCovered: usd("quarter.required.covered", "/required_extra_pipeline", { unavailable: words("none needed: already covered") }),
  qRequiredNone: usd("quarter.required.none", "/required_extra_pipeline", { unavailable: words("no amount helps within the cap") }),
  qExpected: usd("quarter.expected-created", "/expected_created_pipeline"),
  qYield: cents("quarter.yield", "/cents_booked_in_quarter_per_dollar"),
  qSurplus: text("quarter.surplus", "/surplus_statement", { unavailable: words("no completed schedule to compare") }),
  // what makes a quarter too late, as the report says it
  lateLabel: text("late.label", "/too_late/label"),
  lateReason: text("late.reason", ""),
  lateDiagnostic: text("late.diagnostic", ""),
  lateOpen: text("late.open-pipeline", "/too_late/open_pipeline/statement"),
  // a quarter opened: against the team's record
  qEarlier: usd("quarter.earlier-assigned", "/earlier_assigned_in_span"),
  qTotal: usd("quarter.total-created", "/total_created_in_span", { unavailable: words("nothing to create") }),
  qCapLeft: usd("quarter.cap-left", "/cap_left_before"),
  qPerDay: usd("quarter.per-day", "/per_day/required_total", { unavailable: words("not needed") }),
  qPerDayVs: multiple("quarter.per-day.vs-best", "/per_day/required_against_team_best", { unavailable: words("not needed") }),
  qPerAe: usd("quarter.per-ae", "/per_ramped_ae_month/required_total", { unavailable: words("not needed") }),
  qPerAeVs: multiple("quarter.per-ae.vs-best", "/per_ramped_ae_month/required_against_team_best", { unavailable: words("not needed") }),
  qRamped: bind({ id: "quarter.ramped-ae-months", path: "/ramped_ae_months", unit: "quantity", format: "quantity", unavailable: words("no ramp fitted") }),

  // the team's own record, which a requirement is held against
  bestQuarter: usd("team.best-quarter", `${RP}/team_history/best_four_quarter_average`, { unavailable: words("fewer than four complete quarters") }),
  bestPerDay: usd("team.best-per-day", `${RP}/team_history/best_four_quarter_average_per_day`, { unavailable: words("fewer than four complete quarters") }),
  median: usd("team.median", `${RP}/team_history/median`, { unavailable: words("no complete quarter") }),
  historyQuarters: count("team.quarters", `${RP}/team_history/quarters`),
  historyNote: text("team.note", `${RP}/team_history/note`),
  historyUnit: text("team.unit", `${RP}/team_history/unit`),
  perDayUnit: text("team.per-day-unit", `${RP}/team_history/per_day_unit`),

  // lead time: how long a created dollar takes to book (a row of the lead-time quarters)
  ltQuestion: text("lead.question", `${RP}/lead_time/question`),
  ltBasis: text("lead.basis", `${RP}/lead_time/basis`),
  ltFrom: date("lead.from", `${RP}/lead_time/created_between/0`),
  ltTo: date("lead.to", `${RP}/lead_time/created_between/1`),
  ltLater: cents("lead.later", `${RP}/lead_time/cents_booked_later`),
  ltWin: share("lead.count-win", `${RP}/lead_time/count_outcome/win_within_horizon`),
  ltCountMeaning: text("lead.count-meaning", `${RP}/lead_time/count_outcome/meaning`),
  ltQuarter: text("lead.quarter", "/quarter"),
  ltIn: cents("lead.in-quarter", "/cents_booked_in_quarter"),
  ltBy: cents("lead.by-quarter-end", "/cents_booked_by_quarter_end"),

  // how the numbers were reached
  cap: usd("notes.cap", `${RP}/cap`),
  capRule: text("notes.cap-rule", `${RP}/cap_rule`),
  forward: text("notes.forward-function", `${RP}/forward_function`),
  expectedBasis: text("notes.expected-basis", `${RP}/expected_basis`),
  method: text("notes.method", `${RP}/method`),
  lateRule: text("notes.too-late-rule", `${RP}/too_late_rule`),
  perRepWhy: text("notes.per-rep-rule", `${RP}/per_rep_rule/why`),
  meaning: text("notes.meaning", `${RP}/meaning`),

  // a row of the stage win rates (the report's rates, each once)
  rDefinition: text("rate.definition", "/definition"),
  rValue: share("rate.value", "/value"),
  rLow: share("rate.range95.low", "/range95/0", { unavailable: words("no range") }),
  rHigh: share("rate.range95.high", "/range95/1", { unavailable: words("no range") }),
  rSample: count("rate.sample", "/sample_size"),
  rNumerator: text("rate.numerator", "/numerator"),
  rDenominator: text("rate.denominator", "/denominator"),
  rSource: text("rate.source", "/source"),
} as const satisfies Record<string, Binding>;

export const ROWS = {
  flow: FLOW,
  quarters: `${RP}/quarters`,
  leadQuarters: `${RP}/lead_time/quarters`,
  rates: "/rates",
} as const;

/** The five stages of the year's flow, in the order the pipeline moves through them. */
export const FLOW_KEYS = ["open at fiscal-year start", "created", "won", "lost", "open at as-of"] as const;

/** A stage win rate: the share of deals open in a stage that are won within the horizon (not an age-group cell). */
export const STAGE_WIN_RATE = /^win_within_horizon:[^:]+$/;
export const NEW_PIPELINE_WIN_RATE = "new_pipeline_win_rate";

export const LISTED_BINDINGS: readonly Binding[] = Object.values(B);

// ---------------------------------------------------------------- the quarter chart

const QUARTERS = { rowsAt: ROWS.quarters, property: "quarter" } as const;
const at = (field: string) => `${ROWS.quarters}/{quarter={period}}/${field}`;

/** Pipeline expected to be created in each remaining quarter, and the extra that must be created on top (a gap where no amount helps). */
export const SERIES = {
  expected: { key: "expected", label: "Expected to be created", kind: "decimal", path: at("expected_created_pipeline"), periods: QUARTERS },
  required: { key: "required", label: "Extra required", kind: "decimal", path: at("required_extra_pipeline"), periods: QUARTERS },
} as const satisfies Record<string, SeriesSpec>;
