/**
 * observedScenario.ts — Hydrate the Observed scenario from the engine-baked
 * snapshot.target_setter.observed_scenario block.
 *
 * The engine pre-computes and embeds all rates; this module is a pure
 * pass-through with no fallback constants or derivation logic.
 */

import type { Scenario } from "../../types/targetSetter";
import type { Snapshot } from "../../types/snapshot";

/**
 * Return the Observed scenario embedded in the snapshot, or null if the
 * snapshot pre-dates the target_setter block (engine v1 snapshots).
 */
export function buildObservedScenario(snapshot: Snapshot): Scenario | null {
  const obs = snapshot.target_setter?.observed_scenario;
  if (!obs) return null;
  return {
    id: obs.id,
    label: obs.label,
    description: obs.description,
    win_rate_starting: obs.win_rate_starting,
    win_rate_created: obs.win_rate_created,
    push_rate: obs.push_rate,
    loss_rate: obs.loss_rate,
    ae_self_gen_pct: obs.ae_self_gen_pct,
    mql_to_s0: obs.mql_to_s0,
    s0_to_s1: obs.s0_to_s1,
    s1_to_s2: obs.s1_to_s2,
    segment_share: { ...obs.segment_share },
    acv: { ...obs.acv },
  };
}
