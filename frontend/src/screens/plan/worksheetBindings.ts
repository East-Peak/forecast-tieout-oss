import { bind } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";

/**
 * The planning worksheet's committed binding list: every figure and sentence of the landing screen's worksheet,
 * with the file, pointer, unit and format it is read through. The worksheet is one section of the report
 * (`/worksheet`), written by the core; the browser draws and says it, and adds, sorts and ranks nothing.
 * A row binding is read from each row of a collection (WS_ROWS), by its position in the report. A driver's
 * figures come in three display kinds (a share, dollars, a plain quantity), chosen by the report's own `display`.
 * The tests assert this list against independently written expectations.
 */
const SHEET = "/worksheet";

const text = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "text", format: "text", ...extra });
const usd = (id: string, path: string, extra: Partial<Binding> = {}) => bind({ id, path, unit: "usd", format: "usd-short", ...extra });
const words = (w: string) => ({ words: w }) as const;

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



} as const satisfies Record<string, Binding>;

function everyBinding(): Binding[] {
  const flat = (o: Record<string, unknown>): Binding[] =>
    Object.values(o).flatMap((v) => (v && typeof v === "object" && "id" in v ? [v as Binding] : flat(v as Record<string, unknown>)));
  return [...flat(WS)];
}

export const WORKSHEET_BINDINGS: readonly Binding[] = everyBinding();
