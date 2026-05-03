import type { Scenario } from "../../types/targetSetter";
import { rollForwardPipe } from "./inverseWaterfall";

export interface ForwardFromMqlsInput {
  mqls: number;
  starting_pipe: number;
  scenario: Scenario;
}

export interface ForwardFromMqlsResult {
  bookings: number;
  created_pipe: number;
  ending_pipe: number;
}

export function forwardFromMqls({
  mqls,
  starting_pipe,
  scenario,
}: ForwardFromMqlsInput): ForwardFromMqlsResult {
  // MQLs → marketing S2 count (scalar), then → marketing S2 dollars using blended ACV,
  // then inflate to total created pipe by dividing out (1 - ae_self_gen_pct).
  const marketing_s2_count =
    mqls * scenario.mql_to_s0 * scenario.s0_to_s1 * scenario.s1_to_s2;

  // Effective ACV = harmonic blend that inverts segmentSplit exactly.
  // Iterate over all segments generically — no hardcoded ".enterprise"/".commercial".
  let inv_sum = 0;
  for (const seg of Object.keys(scenario.segment_share)) {
    const acv = scenario.acv[seg] > 0 ? scenario.acv[seg] : 1;
    inv_sum += scenario.segment_share[seg] / acv;
  }
  const blended_acv = inv_sum > 0 ? 1 / inv_sum : 0;

  const marketing_pipe = marketing_s2_count * blended_acv;
  const ae_factor = 1 - Math.min(Math.max(scenario.ae_self_gen_pct, 0), 0.99);
  const created_pipe = ae_factor > 0 ? marketing_pipe / ae_factor : 0;

  const won_from_starting = starting_pipe * scenario.win_rate_starting;
  const won_from_created = created_pipe * scenario.win_rate_created;
  const bookings = won_from_starting + won_from_created;

  const ending_pipe = rollForwardPipe({
    starting_pipe,
    created_pipe,
    rates: scenario,
  });

  return { bookings, created_pipe, ending_pipe };
}
