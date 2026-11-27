import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";

/**
 * The Capacity screen's committed binding list: every business value the screen shows, with the file,
 * pointer, unit and format it is read through. A row binding is read from each row of a collection (ROWS);
 * `{company}` in a pointer stands for the visitor's current choice. The tests assert this list against
 * independently written expectations.
 */
const RC = "/roster_capacity";
const QP = "/quota_productivity";
const ROSTER = `${RC}/roster`;

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const qty = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "quantity", format: "quantity", ...extra });
const count = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "count", format: "count", ...extra });
const share = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "fraction", format: "percent1", ...extra });
const words = (w: string) => ({ words: w }) as const;

export const B = {
  fiscalYear: text("fiscal-year", "/inputs/fiscal_year"),
  asOf: bind({ id: "as-of", path: "/inputs/as_of", unit: "date", format: "date" }),

  // the roster today: the headline (a roster that cannot be read says why instead)
  rosterUnavailable: text("roster.unavailable", `${ROSTER}/unavailable`),
  heads: count("roster.heads", `${ROSTER}/heads_at_as_of`),
  ramped: qty("roster.ramped", `${ROSTER}/ramped_equivalents_at_as_of`, { unavailable: words("unavailable") }),
  target: count("roster.target", `${ROSTER}/headcount_target_this_month`, { unavailable: words("no headcount target entered") }),
  targetNote: text("roster.target-note", `${ROSTER}/headcount_target_note`),
  departed: count("roster.departed", `${ROSTER}/departed_to_date`),

  // quota against what was observed
  quotaUnavailable: text("quota.unavailable", `${QP}/unavailable`),
  quotaOverTarget: bind({
    id: "quota.over-target",
    path: `${QP}/total_quota/quota_over_target`,
    unit: "quantity",
    format: "multiple",
    unavailable: words("no target to compare with"),
  }),
  quotaAnnual: usd("quota.annual", `${QP}/total_quota/annual_quota_of_people_employed_at_as_of`),
  quotaTarget: usd("quota.target", `${QP}/total_quota/fiscal_year_target`),
  quotaPeople: count("quota.people", `${QP}/total_quota/people`),
  quotaNote: text("quota.note", `${QP}/total_quota/note`),
  quotaDefinition: text("quota.definition", `${QP}/definition`),
  quotaWindow: text("quota.window", `${QP}/window`),
  winsCredited: usd("quota.wins-credited", `${QP}/wins_credited`),
  winsInWindow: usd("quota.wins-in-window", `${QP}/wins_in_window`),
  winsUnattributed: usd("quota.wins-unattributed", `${QP}/wins_unattributed`),
  unattributedNote: text("quota.unattributed-note", `${QP}/unattributed_note`),
  repsWithoutQuota: count("quota.reps-without-quota", `${QP}/reps_without_quota`),
  spreadMinDays: count("quota.spread-min-days", `${QP}/spread_min_days`),
  attainmentAll: share("quota.attainment", `${QP}/all_reps/attainment`, { unavailable: words("no quota in the window") }),

  // a row of the attainment table (all reps, then each segment)
  gReps: count("group.reps", "/reps"),
  gSpreadReps: count("group.spread-reps", "/spread_reps"),
  gQuota: usd("group.quota", "/prorated_quota"),
  gWins: usd("group.wins", "/wins_credited"),
  gAttainment: share("group.attainment", "/attainment", { unavailable: words("no quota in the window") }),
  gMin: share("group.spread.min", "/spread_across_reps/min", { unavailable: words("not enough tenure to show a spread") }),
  gP25: share("group.spread.p25", "/spread_across_reps/p25", { unavailable: words("not enough tenure to show a spread") }),
  gMedian: share("group.spread.median", "/spread_across_reps/median", { unavailable: words("not enough tenure to show a spread") }),
  gP75: share("group.spread.p75", "/spread_across_reps/p75", { unavailable: words("not enough tenure to show a spread") }),
  gMax: share("group.spread.max", "/spread_across_reps/max", { unavailable: words("not enough tenure to show a spread") }),

  // does headcount explain pipeline
  decisionOutcome: text("decision.outcome", `${RC}/decision/outcome`),
  decisionLabel: text("decision.label", `${RC}/decision/label`),
  decisionReason: text("decision.reason", `${RC}/decision/reason`),
  decisionRule: text("decision.rule", `${RC}/decision/declared_rule`),
  decisionUses: text("decision.forecast-uses", `${RC}/decision/forecast_uses`),
  decisionScoredOn: text("decision.scored-on", `${RC}/decision/scored_on`),
  decisionAssociation: text("decision.association", `${RC}/decision/association`),
  decisionVariation: share("decision.variation", `${RC}/decision/staffing_variation`, { unavailable: words("not measured") }),
  periodFrom: bind({ id: "decision.period.from", path: `${RC}/decision/scored_period/0`, unit: "date", format: "date", unavailable: words("no scored period") }),
  periodTo: bind({ id: "decision.period.to", path: `${RC}/decision/scored_period/1`, unit: "date", format: "date", unavailable: words("no scored period") }),
  hiringAction: text("diagnostic.hiring-action", `${RC}/diagnostic/hiring_action`),
  diagnosticLabel: text("diagnostic.label", `${RC}/diagnostic/label`),
  // a row of the scored horizons
  hMonths: count("horizon.months", "/horizon_months"),
  hFolds: count("horizon.folds", "/folds"),
  hCapacity: usd("horizon.error.capacity", "/mean_absolute_error_capacity"),
  hFlat: usd("horizon.error.flat", "/mean_absolute_error_flat"),
  hImprovement: share("horizon.improvement", "/improvement"),

  // ramp, attrition and the creation rate, each with its source and sample
  rampSource: text("ramp.source", `${RC}/ramp/source`),
  rampSample: text("ramp.sample", `${RC}/ramp/sample`),
  rampDefinition: text("ramp.definition", `${RC}/ramp/definition`),
  rampAfter: text("ramp.after", `${RC}/ramp/after`),
  rampWhyNot: text("ramp.why-not-fitted", `${RC}/ramp/why_not_fitted`),
  rampLimitation: text("ramp.limitation", `${RC}/ramp/limitation`),
  rampFittedThrough: text("ramp.fitted-through", `${RC}/ramp/fitted_through`),
  rampLeftOut: count("ramp.left-out", `${RC}/ramp/deals_left_out/count`),
  rampLeftOutWhy: text("ramp.left-out.why", `${RC}/ramp/deals_left_out/why`),
  wMonth: count("weight.tenure-month", "/tenure_month"),
  wWeight: share("weight.weight", "/weight"),
  wLow: share("weight.range95.low", "/range95/0"),
  wHigh: share("weight.range95.high", "/range95/1"),
  wCeiling: text("weight.range95.note", "/range95"),
  wNoRange: text("weight.range95.none", "/range95", { unavailable: words("no range: not fitted") }),
  attritionRate: share("attrition.rate", `${RC}/attrition/monthly_rate`),
  attritionSource: text("attrition.source", `${RC}/attrition/source`),
  attritionSample: text("attrition.sample", `${RC}/attrition/sample`),
  attritionLow: share("attrition.range95.low", `${RC}/attrition/range95/0`, { unavailable: words("no range: not fitted") }),
  attritionHigh: share("attrition.range95.high", `${RC}/attrition/range95/1`, { unavailable: words("no range: not fitted") }),
  attritionWhyNot: text("attrition.why-not-fitted", `${RC}/attrition/why_not_fitted`),
  attritionForward: text("attrition.forward", `${RC}/attrition/forward`),
  creationRate: qty("creation.rate", `${RC}/creation_rate/deals_per_ramped_ae_month`),
  creationDeals: count("creation.deals", `${RC}/creation_rate/trailing_deals`),
  creationMonths: qty("creation.ae-months", `${RC}/creation_rate/trailing_ramped_ae_months`),
  creationWindow: text("creation.window", `${RC}/creation_rate/window`),

  // a row of the month table (past and forward)
  mMonth: bind({ id: "month.month", path: "/month", unit: "month", format: "month" }),
  mKind: text("month.kind", "/kind"),
  mHeads: qty("month.heads", "/heads"),
  mRamped: qty("month.ramped", "/ramped"),
  mDepartures: qty("month.departures", "/departures"),
  mTarget: qty("month.target", "/headcount_target", { unavailable: words("no target") }),

  // stated limits, one per sentence
  limit: text("limit", ""),
} as const satisfies Record<string, Binding>;

export const ROWS = {
  months: `${RC}/months`,
  weights: `${RC}/ramp/weights`,
  horizons: `${RC}/decision/horizons`,
  limitations: `${RC}/limitations`,
  quotaLimits: `${QP}/limits`,
  allReps: `${QP}/all_reps`,
  bySegment: `${QP}/by_segment`,
} as const;

/** Every binding on the screen, once per id (for the committed list the tests check). */
export const LISTED_BINDINGS: readonly Binding[] = Object.values(B);

// ---------------------------------------------------------------- the month chart

const MONTHS = { rowsAt: ROWS.months, property: "month" } as const;
const at = (field: string) => `${ROWS.months}/{month={period}}/${field}`;

/** Heads and ramped equivalents by month, with the headcount target where the profile gives one. */
export const SERIES = {
  ramped: { key: "ramped", label: "Ramped equivalents", kind: "decimal", format: "quantity", path: at("ramped"), periods: MONTHS },
  heads: { key: "heads", label: "Heads", kind: "decimal", format: "quantity", path: at("heads"), periods: MONTHS },
  target: { key: "target", label: "Headcount target", kind: "decimal", format: "quantity", path: at("headcount_target"), periods: MONTHS },
} as const satisfies Record<string, SeriesSpec>;
