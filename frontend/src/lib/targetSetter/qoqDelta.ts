import type { Actuals } from "../../types/snapshot";
import type { Snapshot } from "../../types/snapshot";
import { quarterForMonth } from "../../engine/scenario";

export interface QoqDeltaInput {
  snapshot: Snapshot;
  actuals: Actuals;
  /** ISO date (YYYY-MM-DD) — the snapshot's as_of date. */
  asOf: string;
  /** MQL target for the first quarter in solve scope. */
  targetQNext: number;
}

/**
 * Returns (target / historical) - 1, or null when historical is unavailable.
 *
 * "Historical" = sum of `mql_by_month` values for the month indices in the
 * fiscal quarter containing `asOf`. Requires ≥2 months of data.
 *
 * Fiscal calendar is derived entirely from the snapshot — no hardcoded
 * month-range conditionals (no "if month >= 2 && month <= 4" logic).
 */
export function computeMqlQoqDelta(input: QoqDeltaInput): number | null {
  const { snapshot, actuals, asOf, targetQNext } = input;
  const entries = actuals.mql_by_month ?? [];
  if (entries.length === 0) return null;

  const months = snapshot.scenario_building_blocks?.months ?? [];
  const qbm = snapshot.scenario_building_blocks?.quarter_by_month ?? [];

  // Resolve the active quarter from the snapshot's fiscal calendar.
  const activeQuarter = quarterForMonth(snapshot, asOf.slice(0, 7) + "-01");
  if (!activeQuarter) return null;

  // Find the indices (into the parallel months/qbm arrays) that belong to the active quarter.
  const activeIndices = new Set<number>();
  for (let i = 0; i < months.length; i++) {
    if (qbm[i] === activeQuarter) activeIndices.add(i);
  }

  const observed = entries
    .filter((e) => activeIndices.has(e.month_index))
    .map((e) => e.value);

  if (observed.length < 2) return null;

  const sum = observed.reduce((a, b) => a + b, 0);
  if (sum <= 0) return null;

  return targetQNext / sum - 1;
}
