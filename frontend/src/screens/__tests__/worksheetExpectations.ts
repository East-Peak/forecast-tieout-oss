/**
 * Test-only. What the planning worksheet must show for a company and scenario, written by hand as typed accessors
 * on the generated report types and read through texts from independent.ts, not from src/lib/format.ts or the
 * screen's selectors. Several ids appear once per row; the ids a window other than the default would add are
 * returned as `alsoNamed` so that the committed list and these expectations still name the same bindings.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { WS } from "../plan/worksheetBindings";
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
  return { alsoNamed };
}
