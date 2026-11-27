import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { ComparisonRow, Facts, PlanDoc } from "./protocol";

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
