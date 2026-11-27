/**
 * Test-only. What the planning worksheet must show for a company and scenario, written by hand as typed accessors
 * on the generated report types and read through texts from independent.ts, not from src/lib/format.ts or the
 * screen's selectors. Several ids appear once per row; the ids a window other than the default would add are
 * returned as `alsoNamed` so that the committed list and these expectations still name the same bindings.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { ACTION, CHAIN, DRIVER, OBSERVATION, QUARTER, STEP, WS } from "../plan/worksheetBindings";
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
  bridge(ws, put);
  quarters(r, put);
  chain(ws, put);
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
export function tornado(sheet: Sheet, { one: _one, many }: Put, window: WindowKey): void {
  // the rows stand in the report's own rank for the window (1 first, none last, ties in the report's order)
  const order = (ranks: Array<number | null>) =>
    ranks.map((_, i) => i).sort((a, b) => (ranks[a] ?? Infinity) - (ranks[b] ?? Infinity) || a - b);
  const idx = order(sheet.drivers.map((d) => d.rank[window]));
  const ws = { ...sheet, drivers: idx.map((i) => sheet.drivers[i]) };
  const rows = idx.map((i) => `/worksheet/drivers/${i}`);
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
  put(each((d) => (d.current.value === null ? (d.cannot_scale_because ?? "no figure") : shown(d.display, d.current.value)), (d) => DRIVER.current[d.display].id), variants((k) => DRIVER.current[k as "percent"].id));

  const withHistory = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.historical !== null);
  const without = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.historical === null);
  many(DRIVER.unavailable.id, without.map(([d]) => d.historical_unavailable_because!), without.map(([, i]) => rows[i]));
  put(each((d) => (d.historical ? shown(d.display, d.historical.low.setting) : null), (d) => DRIVER.lowSetting[d.display].id), variants((k) => DRIVER.lowSetting[k as "percent"].id));
  put(each((d) => (d.historical ? shown(d.display, d.historical.high.setting) : null), (d) => DRIVER.highSetting[d.display].id), variants((k) => DRIVER.highSetting[k as "percent"].id));
  many(DRIVER.lowChange[window].id, withHistory.map(([d]) => fmt.usdShort(d.historical!.low.change[window])), withHistory.map(([, i]) => rows[i]));
  many(DRIVER.highChange[window].id, withHistory.map(([d]) => fmt.usdShort(d.historical!.high.change[window])), withHistory.map(([, i]) => rows[i]));

  // needed alone: the value where it solves, the report's words where it does not
  // (a driver the history cannot scale has none, and the report's sentence stands in its place)
  const solves = (d: Sheet["drivers"][number]) => d.needed_alone !== null && d.needed_alone.outcome === "solves";
  put(each((d) => (solves(d) ? shown(d.display, d.needed_alone!.value!) : null), (d) => DRIVER.neededValue[d.display].id), variants((k) => DRIVER.neededValue[k as "percent"].id));
  const none = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.needed_alone === null);
  many(DRIVER.neededNone.id, none.map(([d]) => d.cannot_scale_because ?? "no figure"), none.map(([, i]) => rows[i]));
  // the label is in the cell where it does not solve, and in the opened row where it does
  const withWords = ws.drivers.map((d, i) => [d, i] as const).filter(([d]) => d.needed_alone !== null);
  many(DRIVER.neededLabel.id, withWords.map(([d]) => d.needed_alone!.outcome_label), withWords.map(([, i]) => rows[i]));
  const reasoned = withWords.filter(([d]) => d.needed_alone!.reason_label !== null);
  many(DRIVER.neededReason.id, reasoned.map(([d]) => d.needed_alone!.reason_label!), reasoned.map(([, i]) => rows[i]));
  const overshot = withWords.filter(([d]) => d.needed_alone!.overshoot !== null);
  many(DRIVER.overshoot.id, overshot.map(([d]) => fmt.usdShort(d.needed_alone!.overshoot!)), overshot.map(([, i]) => rows[i]));
  const precise = withWords.filter(([d]) => d.needed_alone!.precision_note !== null);
  many(DRIVER.precision.id, precise.map(([d]) => d.needed_alone!.precision_note!), precise.map(([, i]) => rows[i]));
  many(DRIVER.history.id, ws.drivers.map((d) => d.needed_alone?.history_label ?? "not compared with history"), rows);

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
  const quarters = ws.drivers.flatMap((d, i) => d.evidence.quarters.map((q, j) => ({ d, q, row: `/worksheet/drivers/${idx[i]}/evidence/quarters/${j}` })));
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
  const aIdx = order(sheet.actions.rows.map((a) => a.rank[window]));
  const actions = aIdx.map((i) => sheet.actions.rows[i]);
  const aRows = aIdx.map((i) => `/worksheet/actions/rows/${i}`);
  many(ACTION.name.id, actions.map((a) => a.action.value), aRows);
  many(ACTION.gain[window].id, actions.map((a) => (a.bookings_gained.value === null ? a.status.value : fmt.usdShort(a.bookings_gained.value[window]))), aRows);
  many(ACTION.closes.id, actions.map((a) => a.closes_alone_label), aRows);
}

/** The bridge, drawn only where a plan is in force: its steps in the report's own order, each with its amount and its change. */
function bridge(ws: Sheet, { many, when }: Put): void {
  const b = ws.bridge;
  const on = ws.plan_in_force;
  when(on, WS.bridgeMeasure.id, () => b.measure);
  when(on, WS.bridgeTarget.id, () => fmt.usdShort(b.target.value));
  when(on, WS.bridgeOrder.id, () => b.order);
  const steps = on ? b.steps.map((s, i) => [s, i] as const) : [];
  const rows = (list: ReadonlyArray<readonly [unknown, number]>) => list.map(([, i]) => `/worksheet/bridge/steps/${i}`);
  many(STEP.label.id, steps.map(([s]) => s.label), rows(steps));
  many(STEP.level.id, steps.map(([s]) => fmt.usdShort(s.to)), rows(steps));
  const changed = steps.filter(([s]) => s.change !== null);
  many(STEP.change.id, changed.map(([s]) => fmt.usdShort(s.change!)), rows(changed));
  const noted = steps.filter(([s]) => s.note !== null);
  many(STEP.note.id, noted.map(([s]) => s.note!), rows(noted));
}

/** Each quarter against its target: the working plan's quarters from the plan in force, or the as-signed ones where there is none. */
function quarters(r: TieoutReport, { many }: Put): void {
  const q = r.gap.quarters;
  const signed = q.map((_, i) => `/gap/quarters/${i}`);
  many(QUARTER.quarter.id, q.map((x) => x.quarter), signed);
  many(QUARTER.target.id, q.map((x) => fmt.usdShort(x.target)), signed);
  many(QUARTER.asSigned.id, q.map((x) => (x.expected === null ? "unavailable" : fmt.usdShort(x.expected))), signed);
  const plan = r.plan;
  if (plan !== undefined && "unavailable" in plan) {
    many(QUARTER.planned.id, []);
    many(QUARTER.remainingGap.id, []);
    return;
  }
  const own = plan === undefined ? q : plan.with_plan_quarters;
  const prefix = plan === undefined ? "/gap/quarters" : "/plan/with_plan_quarters";
  many(QUARTER.planned.id, own.map((x) => (x.expected === null ? "unavailable" : fmt.usdShort(x.expected))), own.map((_, i) => `${prefix}/${i}`));
  many(QUARTER.remainingGap.id, own.map((x) => (x.gap === null ? "unavailable" : fmt.usdShort(x.gap))), own.map((_, i) => `${prefix}/${i}`));
}

/** The as-signed chain: three measures and the timing constraint for each remaining quarter. */
function chain(ws: Sheet, { one, many }: Put): void {
  one(WS.chainNote.id, ws.chain.note);
  const unavailable = ws.chain.unavailable;
  many(WS.chainUnavailable.id, unavailable === null ? [] : [unavailable]);
  const q = unavailable === null ? ws.chain.quarters : [];
  const rows = q.map((_, i) => `/worksheet/chain/quarters/${i}`);
  many(CHAIN.quarter.id, q.map((x) => x.quarter), rows);
  many(CHAIN.status.id, q.map((x) => x.status.value), rows);
  many(CHAIN.bookingsTarget.id, q.map((x) => fmt.usdShort(x.bookings.target.value)), rows);
  many(CHAIN.bookingsExpected.id, q.map((x) => (x.bookings.expected.value === null ? "unavailable" : fmt.usdShort(x.bookings.expected.value))), rows);
  many(CHAIN.bookingsGap.id, q.map((x) => (x.bookings.gap.value === null ? "unavailable" : fmt.usdShort(x.bookings.gap.value))), rows);
  const pipeline = q.map((x) => x.created_pipeline);
  many(CHAIN.pipelineRequired.id, pipeline.map((p) => (p.required.value === null ? (p.required_note.value ?? "no figure") : fmt.usdShort(p.required.value))), rows);
  many(CHAIN.pipelineExpected.id, pipeline.map((p) => fmt.usdShort(p.expected.value)), rows);
  many(CHAIN.pipelineHeadline.id, pipeline.map((p) => p.headline.value), rows);
  const per = q.map((x) => x.per_ramped_ae_month);
  many(CHAIN.perRequired.id, per.map((p) => (p.required.value === null ? (p.note.value ?? "no figure") : fmt.usdShort(p.required.value))), rows);
  many(CHAIN.perExpected.id, per.map((p) => (p.expected.value === null ? (p.note.value ?? "no figure") : fmt.usdShort(p.expected.value))), rows);
  const timed = q.map((x, i) => [x, i] as const).filter(([x]) => x.timing.applies.value);
  many(CHAIN.timingLabel.id, timed.map(([x]) => x.timing.label.value ?? ""), timed.map(([, i]) => rows[i]));
  const reasons = timed.flatMap(([x, i]) => x.timing.reasons.value.map((text, j) => ({ text, row: `/worksheet/chain/quarters/${i}/timing/reasons/value/${j}` })));
  many(CHAIN.timingReason.id, reasons.map((x) => x.text), reasons.map((x) => x.row));
}
