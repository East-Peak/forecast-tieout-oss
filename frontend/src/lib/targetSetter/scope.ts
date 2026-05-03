import type { QuarterKey } from "../../types/targetSetter";
import type { Snapshot } from "../../types/snapshot";
import { quarterForMonth, allQuartersFromSnapshot } from "../../engine/scenario";

/**
 * Return the quarter that contains `isoDate`, derived entirely from the
 * snapshot's fiscal calendar. Never hardcodes fiscal year boundaries.
 */
export function getQuarterFromDate(snapshot: Snapshot, isoDate: string): QuarterKey | null {
  const monthIso = isoDate.slice(0, 7) + "-01";
  return quarterForMonth(snapshot, monthIso);
}

/**
 * Determine the active quarter (the one containing `asOf`) and the solve scope
 * (all subsequent quarters in fiscal-calendar order).
 *
 * If `asOf` falls outside the snapshot's fiscal year, `active` is null and
 * `scope` contains all quarters from the snapshot.
 */
export function determineSolveScope(
  snapshot: Snapshot,
  asOf: string,
): {
  active: QuarterKey | null;
  scope: QuarterKey[];
} {
  const all = allQuartersFromSnapshot(snapshot);
  const active = getQuarterFromDate(snapshot, asOf);
  if (!active) return { active: null, scope: all };
  const idx = all.indexOf(active);
  return { active, scope: idx < 0 ? all : all.slice(idx + 1) };
}
