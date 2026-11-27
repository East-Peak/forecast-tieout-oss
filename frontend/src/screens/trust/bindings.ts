import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { B as FORECAST } from "../forecast/bindings";

/**
 * The Trust screen's committed binding list: every business value the screen shows, with the file,
 * pointer, unit and format it is read through. A row binding is read from each row of a collection (ROWS);
 * `{company}` and `{scenario}` in a pointer stand for the visitor's current choice. The two verdicts are
 * the Forecast screen's own bindings, so the two screens cannot say different things about them.
 * The tests assert this list against independently written expectations.
 */
const REC = "/reconciliation";
const FACTS = "/history/facts";
const SCENARIO = "/companies/{id={company}}/scenarios/{id={scenario}}";

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const usdFull = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-full", ...extra });
const count = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "count", format: "count", ...extra });
const share = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "fraction", format: "percent1", ...extra });
const date = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "date", format: "date", ...extra });
const passed = (id: string, path: string) => bind({ id, path, unit: "flag", format: "passed" });
const words = (w: string) => ({ words: w }) as const;

export const VERDICTS = {
  software: FORECAST.softwareVerdict,
  softwareSummary: FORECAST.softwareSummary,
  better: FORECAST.betterVerdict,
  betterReason: FORECAST.betterReason,
  months: FORECAST.cmpMonths,
  model: FORECAST.cmpModel,
  stage: FORECAST.cmpStage,
  stageOutcome: FORECAST.cmpStageOutcome,
  runRate: FORECAST.cmpRunRate,
  runRateOutcome: FORECAST.cmpRunRateOutcome,
} as const;

export const B = {
  fiscalYear: text("fiscal-year", "/inputs/fiscal_year"),
  asOf: date("as-of", "/inputs/as_of"),

  // the software's own checks, each passed or failed
  softwareScope: text("software.scope", "/verdicts/software_correct/scope"),
  checkName: text("software.check.name", "/name"),
  checkDetail: text("software.check.detail", "/detail"),
  checkPassed: passed("software.check.passed", "/passed"),

  // reconciliation to the source files
  sourceRows: count("recon.source-rows", `${REC}/source_rows`),
  includedRows: count("recon.included-rows", `${REC}/included_rows`),
  sourceArr: usdFull("recon.source-arr", `${REC}/source_arr_total`),
  bookingsFytd: usdFull("recon.bookings-fytd", `${REC}/bookings_fytd`),
  recName: text("recon.check.name", "/name"),
  recDetail: text("recon.check.detail", "/detail"),
  recPassed: passed("recon.check.passed", "/passed"),
  motionRows: count("recon.motion.rows", "/rows"),
  motionArr: usd("recon.motion.arr", "/arr"),
  motionWon: usd("recon.motion.won-fytd", "/won_fytd_arr"),
  exRow: count("recon.exclusion.row", "/row"),
  exDeal: text("recon.exclusion.deal", "/deal_id"),
  exReason: text("recon.exclusion.reason", "/reason"),
  exArr: usdFull("recon.exclusion.arr", "/arr", { unavailable: words("no readable ARR") }),

  // what the history can and cannot support
  monthsOfHistory: count("history.months", `${FACTS}/months_of_history`),
  newBusinessDeals: count("history.deals", `${FACTS}/new_business_deals`),
  closedOutcomes: count("history.closed-outcomes", `${FACTS}/closed_outcomes`),
  maturedSnapshots: count("history.matured-snapshots", `${FACTS}/matured_snapshots`),
  firstDeal: date("history.first-deal", `${FACTS}/first_deal_created`, { unavailable: words("no deals") }),
  earliestClose: date("history.earliest-close", `${FACTS}/earliest_close`, { unavailable: words("no closed deals") }),
  deals: bind({ id: "history.deal-observations", path: `${FACTS}/deal_observations`, unit: "flag", format: "yesno" }),
  foldCount: count("history.backtest-folds", ""),
  limitation: text("history.limitation", ""),

  // the back-test, against both baselines (a row of the horizons)
  btMonths: count("backtest.months", "/horizon_months"),
  btFolds: count("backtest.folds", "/folds"),
  btFitted: usd("backtest.error.fitted", "/mean_absolute_error/fitted model", { unavailable: words("unavailable") }),
  btStage: usd("backtest.error.stage", "/mean_absolute_error/stage-weighted pipeline", { unavailable: words("unavailable") }),
  btRunRate: usd("backtest.error.run-rate", "/mean_absolute_error/trailing run-rate", { unavailable: words("unavailable") }),
  btBias: usd("backtest.bias.fitted", "/signed_bias/fitted model", { unavailable: words("unavailable") }),
  btRangeFolds: count("backtest.range.folds", "/range_coverage/folds_with_a_range"),
  btCover80: share("backtest.range.coverage80", "/range_coverage/80%", { unavailable: words("not scored") }),
  btCover95: share("backtest.range.coverage95", "/range_coverage/95%", { unavailable: words("not scored") }),
  btScoring: text("backtest.scoring", "/backtest/scoring"),
  btNote: text("backtest.note", ""),
  recencyCandidate: text("backtest.recency.candidate", "/backtest/candidates/recency/candidate"),
  recencyInUse: text("backtest.recency.in-use", "/backtest/candidates/recency/fit_in_use"),
  recencyAdopted: bind({ id: "backtest.recency.adopted", path: "/backtest/candidates/recency/adopted", unit: "flag", format: "yesno" }),
  recencyReason: text("backtest.recency.reason", "/backtest/candidates/recency/reason"),

  // every rate, once (a row of the rates)
  rName: text("rate.name", "/name"),
  rDefinition: text("rate.definition", "/definition"),
  rShare: share("rate.value.share", "/value"),
  rDollars: usdFull("rate.value.dollars", "/value"),
  rNumber: bind({ id: "rate.value.number", path: "/value", unit: "quantity", format: "quantity" }),
  rLow: share("rate.range95.low", "/range95/0"),
  rHigh: share("rate.range95.high", "/range95/1"),
  rNoRange: text("rate.range95.none", "/range95", { unavailable: words("no range reported") }),
  rSample: count("rate.sample", "/sample_size"),
  rNumerator: text("rate.numerator", "/numerator"),
  rDenominator: text("rate.denominator", "/denominator"),
  rSource: text("rate.source", "/source"),

  // the files, and what was run
  reportJson: text("files.report-json", `${SCENARIO}/report`, { source: "index" }),
  reportMd: text("files.report-md", `${SCENARIO}/report_markdown`, { source: "index" }),
  schemaVersion: text("run.schema-version", "/schema_version"),
  runData: text("run.data", "/inputs/data"),
  runProfile: text("run.profile", "/inputs/profile"),
  runFit: text("run.fit", "/inputs/fit"),
  runRanges: text("run.ranges", "/inputs/ranges"),
  runMeasure: text("run.measure", "/inputs/measure"),
  runDraws: count("run.draws", "/inputs/simulation/draws"),
  runSeed: count("run.seed", "/inputs/simulation/seed"),
} as const satisfies Record<string, Binding>;

export const ROWS = {
  softwareChecks: "/verdicts/software_correct/checks",
  recChecks: `${REC}/checks`,
  motions: `${REC}/excluded_motions`,
  exclusions: `${REC}/exclusions`,
  limitations: "/history/limitations",
  folds: `${FACTS}/backtest_folds`,
  horizons: "/backtest/horizons",
  notes: "/backtest/notes",
  rates: "/rates",
} as const;

/** The back-test's three horizons are named in the report as "1m", "3m" and "6m"; the screen says them in words. */
export const HORIZON_WORDS: Record<string, string> = { "1m": "One month ahead", "3m": "Three months ahead", "6m": "Six months ahead" };

export const LISTED_BINDINGS: readonly Binding[] = [...Object.values(VERDICTS), ...Object.values(B)];
