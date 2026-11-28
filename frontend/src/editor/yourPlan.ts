import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { ActionDoc, ActionDriver, ComparisonRow, Facts, PlanDoc } from "./protocol";

/** The scenario id of the visitor's own plan; the report's identity carries it. */
export const YOUR_PLAN = "your-plan";

/** "Desktop" for the editor is where the app's widest tables become tables (Tailwind's lg). Below it there is no editor. */
export const DESKTOP_QUERY = "(min-width: 1024px)";

/** The company list with "Your plan" as a last choice for each company; the named scenarios are untouched. */
export function withYourPlan(index: ReportIndex): ReportIndex {
  const choice = {
    id: YOUR_PLAN,
    label: "Your plan",
    description: "The plan you entered, computed in your browser by the same core that wrote the other scenarios. Ranges are not validated, as for any plan.",
    plan_file: null,
    report: "",
    report_markdown: "",
  };
  return { ...index, companies: index.companies.map((c) => ({ ...c, scenarios: [...c.scenarios, choice] })) };
}

/** The comparison with the core's row for the visitor's plan as its last row (the one before it, if any, replaced). */
export function withYourPlanRow(comparison: ScenarioComparison, row: ComparisonRow): ScenarioComparison {
  return { ...comparison, rows: [...comparison.rows.filter((r) => r.scenario !== YOUR_PLAN), row] };
}

/** Most items a plan may hold, hires and programs together. */
export const MAX_ITEMS = 8;

/** The two actions the worksheet measures, one unit each: one hire, one program of one million dollars of pipeline. */
export type UnitKind = "hire" | "program";

/** The plan with one unit of the action added, starting in the first month the plan may start in; a full plan is returned as it is. */
export function withUnit(plan: PlanDoc, facts: Facts, kind: UnitKind): PlanDoc {
  if ([...plan.hires, ...plan.programs].length >= MAX_ITEMS) return plan;
  const start = facts.months[0];
  return kind === "hire"
    ? { ...plan, hires: [...plan.hires, { segment: facts.segments[0]?.value ?? "", start, count: 1 }] }
    : { ...plan, programs: [...plan.programs, { name: "Program pipeline", pipeline: 1000000, start }] };
}

/** Where a draft action was asked for: it says so beside the draft, until the visitor applies it. */
export type ActionOrigin = "tornado" | "grid";

/** What a draft action starts from: the slice ("company" or a segment), the driver (the win rate unless said), a target the report gave (as text) and where it came from. */
export interface ActionSeed {
  slice: string;
  driver?: ActionDriver;
  target: string;
  /** null for an action the visitor adds by hand: it has no note beside it */
  origin: ActionOrigin | null;
}

/** What an action is called, by its driver: "Enterprise win-rate action". */
const KIND: Record<ActionDriver, string> = { win_rate: "win-rate", won_arr: "deal-size", productivity: "creation", cycle_days: "cycle" };

/** The drivers there are to act on. */
export const ACTION_DRIVERS: readonly ActionDriver[] = ["win_rate", "won_arr", "productivity", "cycle_days"];

/**
 * The plan with a draft action added: the first month a plan may start in, no ramp. A slice that already has an action on the
 * driver is not given a second (the core refuses two on one driver and slice), and a driver every segment has an action on
 * holds no more (the core refuses the rest as overlaps). `id` is the action to show the visitor: the new one, the one the
 * slice already has, or null.
 */
export function withAction(plan: PlanDoc, facts: Facts, seed: ActionSeed): { plan: PlanDoc; id: string | null } {
  const held = plan.actions ?? [];
  const driver = seed.driver ?? "win_rate";
  const mine = held.filter((a) => a.driver === driver);
  const same = mine.find((a) => a.slice === seed.slice);
  if (same) return { plan, id: same.id };
  if (mine.length >= facts.segments.length) return { plan, id: null };
  const used = new Set(held.map((a) => a.id));
  const id = ACTION_DRIVERS.flatMap(() => facts.segments)
    .map((_, i) => `action-${i}`)
    .find((candidate) => !used.has(candidate));
  if (id === undefined) return { plan, id: null };
  const action: ActionDoc = { id, name: defaultName(sliceLabel(facts, seed.slice), driver), driver, slice: seed.slice, start: facts.months[0], ramp_months: 0, target: seed.target };
  return { plan: { ...plan, actions: [...held, action] }, id };
}

/** The name an action has until the visitor gives it one: "Enterprise deal-size action". */
export function defaultName(sliceLabel: string, driver: ActionDriver): string {
  return `${sliceLabel} ${KIND[driver]} action`;
}

/** The slice's words: the company, or the segment's label. */
export function sliceLabel(facts: Facts, slice: string): string {
  return slice === "company" ? "Company" : (facts.segments.find((s) => s.value === slice)?.label ?? slice);
}

/**
 * What "Add an action" adds: on the first driver (the win rate, the size, creation, the cycle) that still has room, the company if it has
 * no action there yet, else the first segment without one. Null where every driver has an action on every segment.
 */
export function nextAction(plan: PlanDoc, facts: Facts): { driver: ActionDriver; slice: string } | null {
  const held = plan.actions ?? [];
  for (const driver of ACTION_DRIVERS) {
    const mine = held.filter((a) => a.driver === driver);
    if (mine.length >= facts.segments.length) continue;
    if (mine.length === 0) return { driver, slice: "company" };
    const used = new Set(mine.map((a) => a.slice));
    const free = facts.segments.find((s) => !used.has(s.value));
    if (free) return { driver, slice: free.value };
  }
  return null;
}
