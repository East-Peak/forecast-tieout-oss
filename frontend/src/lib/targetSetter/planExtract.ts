import type { QuarterKey } from "../../types/targetSetter";
import type { Snapshot } from "../../types/snapshot";
import { allQuartersFromSnapshot, monthsForQuarter } from "../../engine/scenario";

/**
 * Extract per-quarter booking targets from a plan object.
 *
 * Uses `allQuartersFromSnapshot` (NOT `getOverridableQuarters`) so that the
 * locked active quarter is always included in the result.
 *
 * Handles two plan shapes:
 * - Normalized (selectedPlan from useSnapshot): components.sales_led.arrTargets.monthly (camelCase)
 * - Raw JSON (test fixtures, direct file reads): components.sales_led.arr_targets.monthly (snake_case)
 *
 * Returns null when the plan is missing or lacks the expected monthly structure,
 * or when any month in any quarter has a non-numeric value.
 */
export function extractQuarterlyBookingsFromPlan(
  snapshot: Snapshot,
  plan: any,
): Record<QuarterKey, number> | null {
  if (!plan || typeof plan !== "object") return null;
  const monthly =
    plan?.components?.sales_led?.arrTargets?.monthly ??
    plan?.components?.sales_led?.arr_targets?.monthly;
  if (!monthly || typeof monthly !== "object") return null;

  const result: Record<QuarterKey, number> = {};
  for (const quarter of allQuartersFromSnapshot(snapshot)) {
    let sum = 0;
    for (const m of monthsForQuarter(snapshot, quarter)) {
      const v = monthly[m];
      if (typeof v !== "number") return null;
      sum += v;
    }
    result[quarter] = sum;
  }
  return result;
}
