/**
 * Test-only. What the planning worksheet must show for a company and scenario, written by hand as typed accessors
 * on the generated report types and read through texts from independent.ts, not from src/lib/format.ts or the
 * screen's selectors. Several ids appear once per row; the ids a window other than the default would add are
 * returned as `alsoNamed` so that the committed list and these expectations still name the same bindings.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { ACTION, DRIVER, OBSERVATION, WS } from "../plan/worksheetBindings";
import * as fmt from "./independent";
import type { Case } from "./screenChecks";

type Sheet = Exclude<TieoutReport["worksheet"], { unavailable: string }>;

export interface Put {
  one: (id: string, text: string, times?: number) => void;
  many: (id: string, texts: string[], rows?: string[]) => void;
  when: (condition: boolean, id: string, text: () => string, times?: number) => void;
  expected: Expectation[];
  absent: Absent[];
}

const sheetOf = (r: TieoutReport): Sheet | null => ("unavailable" in r.worksheet ? null : r.worksheet);

export function worksheetExpectations({ report: r, comparison, scenario }: Case, put: Put): { alsoNamed: string[] } {
  const ws = sheetOf(r);
  const { one, when } = put;
  const alsoNamed: string[] = [];
  when(ws === null, WS.unavailable.id, () => ("unavailable" in r.worksheet ? r.worksheet.unavailable : ""));
  if (ws === null) return { alsoNamed };

  // the summary row
  const s = ws.summary;
  one(WS.target.id, fmt.usdShort(s.fiscal_year_target.value));
  one(WS.asSigned.id, fmt.usdShort(s.as_signed.value));
  one(WS.workingPlan.id, fmt.usdShort(s.working_plan.value));
  one(WS.remainingGap.id, fmt.usdShort(s.remaining_gap.value));
  // a plan with nothing valued is "not valued" from the comparison file, never the summary's zero
  const notValued = comparison.rows.find((x) => x.scenario === scenario)!.bookings_change === null;
  when(ws.plan_in_force && !notValued, WS.gain.id, () => (s.twelve_month_gain === null ? "not valued" : fmt.usdShort(s.twelve_month_gain.value)));
  when(ws.plan_in_force && notValued, WS.gainNotValued.id, () => "not valued");
  when(ws.plan_in_force, WS.cost.id, () => (s.cash_cost_in_twelve_months === null || s.cash_cost_in_twelve_months.value === null ? "cost not entered" : fmt.usdShort(s.cash_cost_in_twelve_months.value)));
  when(!ws.plan_in_force, WS.noPlanNote.id, () => s.no_plan_note!);

  // the sentences that stand near the chart
  one(WS.definition.id, ws.definition);
  one(WS.measuredAround.id, ws.measured_around);
  one(WS.historyNote.id, ws.history_note);
  one(WS.sensitivityNote.id, ws.sensitivity_note);
  one(WS.expectationNote.id, ws.expectation_note);

  tornado(ws, put, REST_WINDOW);
  alsoNamed.push(...otherWindowIds());
  return { alsoNamed };
}

// the windows, written here: the screen's own constants are what a mutation swaps
export const REST_WINDOW = "rest of fiscal year";
export const TWELVE_WINDOW = "next twelve months";
type WindowKey = typeof REST_WINDOW | typeof TWELVE_WINDOW;

const shown = (display: string, raw: string): string => (display === "percent" ? fmt.percent1(raw) : display === "money" ? fmt.usdShort(raw) : fmt.decimal2(raw));

/** The ids a window other than the first adds to the page, so the committed list and these expectations name the same bindings. */
function otherWindowIds(): string[] {
  return [DRIVER.lowChange[TWELVE_WINDOW].id, DRIVER.highChange[TWELVE_WINDOW].id, ACTION.gain[TWELVE_WINDOW].id];
}

/** The driver table, its disclosures and the two actions, for the window the switch is on. */
export function tornado(ws: Sheet, { one: _one, many }: Put, window: WindowKey): void {
  const rows = ws.drivers.map((_, i) => `/worksheet/drivers/${i}`);
  const each = (id: (d: Sheet["drivers"][number]) => string | null, ids: (d: Sheet["drivers"][number]) => string) => {
    // grouped by binding id, in row order
    const byId = new Map<string, { texts: string[]; rows: string[] }>();
    ws.drivers.forEach((d, i) => {
      const text = id(d);
      if (text === null) return;
      const key = ids(d);
      const entry = byId.get(key) ?? { texts: [], rows: [] };
      entry.texts.push(text);
      entry.rows.push(rows[i]);
      byId.set(key, entry);
    });
    return byId;
  };
  const put = (m: Map<string, { texts: string[]; rows: string[] }>, all: string[]) => {
    for (const id of all) {
      const e = m.get(id);
      many(id, e?.texts ?? [], e?.rows);
    }
  };
  const DISPLAYS = ["percent", "money", "decimal"] as const;
  const variants = (base: (d: string) => string) => DISPLAYS.map(base);

  many(DRIVER.label.id, ws.drivers.map((d) => d.label), rows);
  many(DRIVER.unitLabel.id, ws.drivers.map((d) => d.unit_label), rows);
  put(each((d) => shown(d.display, d.current.value), (d) => DRIVER.current[d.display].id), variants((k) => DRIVER.current[k as "percent"].id));

  const withHistory = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.historical !== null);
  const without = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.historical === null);
  many(DRIVER.unavailable.id, without.map(([d]) => d.historical_unavailable_because!), without.map(([, i]) => rows[i]));
  put(each((d) => (d.historical ? shown(d.display, d.historical.low.setting) : null), (d) => DRIVER.lowSetting[d.display].id), variants((k) => DRIVER.lowSetting[k as "percent"].id));
  put(each((d) => (d.historical ? shown(d.display, d.historical.high.setting) : null), (d) => DRIVER.highSetting[d.display].id), variants((k) => DRIVER.highSetting[k as "percent"].id));
  many(DRIVER.lowChange[window].id, withHistory.map(([d]) => fmt.usdShort(d.historical!.low.change[window])), withHistory.map(([, i]) => rows[i]));
  many(DRIVER.highChange[window].id, withHistory.map(([d]) => fmt.usdShort(d.historical!.high.change[window])), withHistory.map(([, i]) => rows[i]));

  // needed alone: the value where it solves, the report's words where it does not
  const solved = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.needed_alone.outcome === "solves");
  const unsolved = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.needed_alone.outcome !== "solves");
  put(each((d) => (d.needed_alone.outcome === "solves" ? shown(d.display, d.needed_alone.value!) : null), (d) => DRIVER.neededValue[d.display].id), variants((k) => DRIVER.neededValue[k as "percent"].id));
  // the label is in the cell where it does not solve, and in the opened row where it does
  const withLabel = [...unsolved, ...solved].sort((a, b) => a[1] - b[1]);
  many(DRIVER.neededLabel.id, withLabel.map(([d]) => d.needed_alone.outcome_label), withLabel.map(([, i]) => rows[i]));
  const reasoned = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.needed_alone.reason_label !== null);
  many(DRIVER.neededReason.id, reasoned.map(([d]) => d.needed_alone.reason_label!), reasoned.map(([, i]) => rows[i]));
  const overshot = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.needed_alone.overshoot !== null);
  many(DRIVER.overshoot.id, overshot.map(([d]) => fmt.usdShort(d.needed_alone.overshoot!)), overshot.map(([, i]) => rows[i]));
  many(DRIVER.history.id, ws.drivers.map((d) => d.needed_alone.history_label ?? "not compared with history"), rows);

  // the opened row
  many(DRIVER.appliesTo.id, ws.drivers.map((d) => d.applies_to), rows);
  put(each((d) => (d.historical ? shown(d.display, d.historical.minimum) : null), (d) => DRIVER.minimum[d.display].id), variants((k) => DRIVER.minimum[k as "percent"].id));
  put(each((d) => (d.historical ? shown(d.display, d.historical.maximum) : null), (d) => DRIVER.maximum[d.display].id), variants((k) => DRIVER.maximum[k as "percent"].id));
  many(DRIVER.rule.id, withHistory.map(([d]) => d.historical!.rule), withHistory.map(([, i]) => rows[i]));
  many(DRIVER.gate.id, ws.drivers.map((d) => d.evidence.gate), rows);
  many(DRIVER.eligible.id, ws.drivers.map((d) => fmt.quantity(d.evidence.eligible_quarters)), rows);
  many(DRIVER.required.id, ws.drivers.map((d) => fmt.quantity(d.evidence.required_quarters)), rows);
  const limited = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.limitation !== null);
  many(DRIVER.limitation.id, limited.map(([d]) => d.limitation!), limited.map(([, i]) => rows[i]));

  // every past quarter of every driver
  const quarters = ws.drivers.flatMap((d, i) => d.evidence.quarters.map((q, j) => ({ d, q, row: `/worksheet/drivers/${i}/evidence/quarters/${j}` })));
  many(OBSERVATION.quarter.id, quarters.map(({ q }) => q.quarter), quarters.map(({ row }) => row));
  many(OBSERVATION.created.id, quarters.map(({ q }) => fmt.quantity(q.created)), quarters.map(({ row }) => row));
  many(OBSERVATION.wins.id, quarters.map(({ q }) => fmt.quantity(q.wins)), quarters.map(({ row }) => row));
  for (const display of DISPLAYS) {
    const mine = quarters.filter(({ d }) => d.display === display);
    many(
      OBSERVATION.value[display].id,
      mine.map(({ q }) => (q.value === null ? (q.not_eligible_because ?? "not counted") : shown(display, q.value))),
      mine.map(({ row }) => row),
    );
  }

  // the two actions, in the same window
  const actions = ws.actions.rows;
  const aRows = actions.map((_, i) => `/worksheet/actions/rows/${i}`);
  many(ACTION.name.id, actions.map((a) => a.action.value), aRows);
  many(ACTION.gain[window].id, actions.map((a) => (a.bookings_gained.value === null ? a.status.value : fmt.usdShort(a.bookings_gained.value[window]))), aRows);
  many(ACTION.closes.id, actions.map((a) => a.closes_alone_label), aRows);
}
