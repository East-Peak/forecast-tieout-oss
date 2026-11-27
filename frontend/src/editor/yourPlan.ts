import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { ComparisonRow } from "./protocol";

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
