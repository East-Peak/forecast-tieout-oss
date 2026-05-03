/**
 * solve.ts — Top-level inverse-waterfall orchestrator.
 *
 * Given a snapshot, an as-of date, per-quarter bookings targets, and a
 * Scenario, back-solves the created-pipe and funnel stage counts required to
 * hit each quarter's target.
 *
 * Snapshot-threaded: determineSolveScope reads the fiscal calendar from the
 * snapshot, so no hardcoded quarter labels appear here.
 */

import type { QuarterKey, QuarterTargets, Scenario, SolveResult } from "../../types/targetSetter";
import type { Snapshot } from "../../types/snapshot";
import { inverseQuarter, rollForwardPipe } from "./inverseWaterfall";
import { splitSegments } from "./segmentSplit";
import { computeFunnel, splitAeMarketing } from "./funnel";
import { determineSolveScope } from "./scope";

export interface SolveInput {
  snapshot: Snapshot;
  as_of: string;
  starting_pipe: number;
  bookings_targets: Record<QuarterKey, number>;
  scenario: Scenario;
  active_ytd_bookings?: number;
}

export function solve(input: SolveInput): SolveResult {
  const { active, scope } = determineSolveScope(input.snapshot, input.as_of);
  const warnings: string[] = [];
  const quarters: QuarterTargets[] = [];

  let current_pipe = input.starting_pipe;

  for (const quarter of scope) {
    const bookings_target = input.bookings_targets[quarter] ?? 0;
    const inv = inverseQuarter({
      starting_pipe: current_pipe,
      bookings_target,
      rates: input.scenario,
    });

    // Total created pipe → per-segment counts (generic: any segment set)
    const totalSplit = splitSegments({
      created_pipe: inv.created_pipe,
      segment_share: input.scenario.segment_share,
      acv: input.scenario.acv,
    });

    // Marketing-sourced created pipe → per-segment marketing counts
    const mktSplit = splitAeMarketing({
      total_pipe: inv.created_pipe,
      ae_self_gen_pct: input.scenario.ae_self_gen_pct,
    });
    const marketingSegs = splitSegments({
      created_pipe: mktSplit.marketing_pipe,
      segment_share: input.scenario.segment_share,
      acv: input.scenario.acv,
    });

    const marketing_s2_total = marketingSegs.total_count;
    const funnelOut = computeFunnel({
      marketing_s2_count: marketing_s2_total,
      mql_to_s0: input.scenario.mql_to_s0,
      s0_to_s1: input.scenario.s0_to_s1,
      s1_to_s2: input.scenario.s1_to_s2,
    });

    const ending_pipe = rollForwardPipe({
      starting_pipe: current_pipe,
      created_pipe: inv.created_pipe,
      rates: input.scenario,
    });

    // Two-tributary extension: Outbound (SDR + direct AE outreach) feeds S0 just like MQLs.
    // v1 assumes same S0→S1 and S1→S2 rates for both tributaries — a documented simplification;
    // realistic Outbound-path rates are probably higher (pre-qualified before booking), so this
    // tends to overstate required Outbound-sourced S0 volume. Editable in Custom scenario (v2+).
    const r0to1 = input.scenario.s0_to_s1;
    const r1to2 = input.scenario.s1_to_s2;
    const total_s2 = totalSplit.total_count;
    const total_s1 = r1to2 > 0 ? total_s2 / r1to2 : 0;
    const total_s0 = r0to1 > 0 ? total_s1 / r0to1 : 0;
    const outbound_s2_raw = total_s2 - marketing_s2_total;
    const outbound_s1_raw = total_s1 - funnelOut.s1;
    const outbound_s0_raw = total_s0 - funnelOut.s0;

    // Clamp only tiny floating-point epsilons to 0. A meaningful negative means
    // marketing > total, which is an invariant break — warn the user instead of
    // silently zeroing it out.
    const EPSILON = 1e-6;
    const clampResidual = (raw: number, name: string): number => {
      if (raw < -EPSILON) {
        warnings.push(
          `Invariant break in ${quarter}: ${name} residual = ${raw.toFixed(3)}. Marketing-sourced count exceeds total; check scenario rates.`,
        );
        return 0;
      }
      return Math.max(0, raw);
    };

    // Build per-segment count maps from the generic splitSegments results.
    const marketing_s2_by_segment: Record<string, number> = {};
    const total_s2_by_segment: Record<string, number> = {};
    for (const seg of Object.keys(input.scenario.segment_share)) {
      marketing_s2_by_segment[seg] = marketingSegs.count_by_segment[seg] ?? 0;
      total_s2_by_segment[seg] = totalSplit.count_by_segment[seg] ?? 0;
    }

    const qt: QuarterTargets = {
      quarter,
      starting_pipe: current_pipe,
      bookings_target,
      created_pipe: inv.created_pipe,
      infeasible: inv.infeasible,
      won_from_starting: inv.won_from_starting,
      won_from_created: inv.won_from_created,
      marketing_pipe: mktSplit.marketing_pipe,
      marketing_s2_total,
      marketing_s2_by_segment,
      total_s2_by_segment,
      mqls: funnelOut.mqls,
      s0: funnelOut.s0,
      s1: funnelOut.s1,
      total_s0,
      total_s1,
      total_s2,
      outbound_s0: clampResidual(outbound_s0_raw, "outbound_s0"),
      outbound_s1: clampResidual(outbound_s1_raw, "outbound_s1"),
      outbound_s2: clampResidual(outbound_s2_raw, "outbound_s2"),
      ending_pipe,
    };
    quarters.push(qt);
    current_pipe = ending_pipe;
  }

  // Waterfall conservation warning (informational, not blocking)
  const sum =
    input.scenario.win_rate_starting + input.scenario.push_rate + input.scenario.loss_rate;
  if (sum < 0.9 || sum > 1.1) {
    warnings.push(
      `Waterfall conservation: starting rates sum to ${sum.toFixed(3)}, outside [0.90, 1.10]. Math may create or destroy pipeline.`,
    );
  }

  const active_ytd_bookings = input.active_ytd_bookings ?? 0;
  const active_remaining_gap = active
    ? (input.bookings_targets[active] ?? 0) - active_ytd_bookings
    : 0;

  return {
    scope,
    active_quarter: active,
    active_ytd_bookings,
    active_remaining_gap,
    quarters,
    warnings,
  };
}
