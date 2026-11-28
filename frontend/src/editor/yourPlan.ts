import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { ActionDoc, ComparisonRow, Facts, PlanDoc } from "./protocol";

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

/** What a draft action starts from: the slice ("company" or a segment), a target the report gave (a probability, as text) and where it came from. */
export interface ActionSeed {
  slice: string;
  target: string;
  /** null for an action the visitor adds by hand: it has no note beside it */
  origin: ActionOrigin | null;
}

/**
 * The plan with a draft action added: the first month a plan may start in, no ramp. A slice that already has an action is
 * not given a second (the core refuses two on one slice), and a plan whose segments all have one holds no more (the core
 * refuses the rest as overlaps). `id` is the action to show the visitor: the new one, the one the slice already has, or null.
 */
export function withAction(plan: PlanDoc, facts: Facts, seed: ActionSeed): { plan: PlanDoc; id: string | null } {
  const held = plan.actions ?? [];
  const same = held.find((a) => a.slice === seed.slice);
  if (same) return { plan, id: same.id };
  if (held.length >= facts.segments.length) return { plan, id: null };
  const used = new Set(held.map((a) => a.id));
  const id = Array.from({ length: facts.segments.length }, (_, i) => `action-${i}`).find((candidate) => !used.has(candidate));
  if (id === undefined) return { plan, id: null };
  const slice = seed.slice === "company" ? "Company" : (facts.segments.find((s) => s.value === seed.slice)?.label ?? seed.slice);
  const action: ActionDoc = { id, name: `${slice} win-rate action`, driver: "win_rate", slice: seed.slice, start: facts.months[0], ramp_months: 0, target: seed.target };
  return { plan: { ...plan, actions: [...held, action] }, id };
}
