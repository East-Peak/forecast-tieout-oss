/**
 * scenarios.ts — Load the scenario palette from the engine-baked snapshot.
 *
 * All scenarios (rates, segment splits, ACVs, bookings targets) are computed
 * by the engine and embedded in snapshot.target_setter.scenarios.
 * Scenarios load from the snapshot. No module-level scenario constants.
 */

import type { Scenario } from "../../types/targetSetter";
import type { Snapshot } from "../../types/snapshot";

/**
 * Return the full scenario palette from the snapshot.
 * Returns an empty array when the snapshot pre-dates the target_setter block.
 */
export function loadScenariosFromSnapshot(snapshot: Snapshot): Scenario[] {
  const raw = snapshot.target_setter?.scenarios ?? [];
  return raw.map((s) => ({
    id: s.id,
    label: s.label,
    description: s.description,
    win_rate_starting: s.win_rate_starting,
    win_rate_created: s.win_rate_created,
    push_rate: s.push_rate,
    loss_rate: s.loss_rate,
    ae_self_gen_pct: s.ae_self_gen_pct,
    mql_to_s0: s.mql_to_s0,
    s0_to_s1: s.s0_to_s1,
    s1_to_s2: s.s1_to_s2,
    segment_share: { ...s.segment_share },
    acv: { ...s.acv },
  }));
}
