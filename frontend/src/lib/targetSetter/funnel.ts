/**
 * funnel.ts — AE/Marketing pipeline split and backwards funnel computation.
 *
 * splitAeMarketing: partitions total pipeline between marketing-sourced and
 * AE self-gen buckets.
 *
 * computeFunnel: given a marketing S2 target, backs out required MQLs and
 * intermediate stage counts using the configured conversion rates.
 */

export interface AeMarketingSplitInput {
  total_pipe: number;
  ae_self_gen_pct: number;
}

export interface AeMarketingSplitResult {
  marketing_pipe: number;
  ae_pipe: number;
}

export function splitAeMarketing({ total_pipe, ae_self_gen_pct }: AeMarketingSplitInput): AeMarketingSplitResult {
  const pct = Math.min(Math.max(ae_self_gen_pct, 0), 0.99);
  return {
    marketing_pipe: total_pipe * (1 - pct),
    ae_pipe: total_pipe * pct,
  };
}

export interface FunnelInput {
  marketing_s2_count: number;
  mql_to_s0: number;
  s0_to_s1: number;
  s1_to_s2: number;
}

export interface FunnelResult {
  mqls: number;
  s0: number;
  s1: number;
  s2: number;
}

export function computeFunnel({ marketing_s2_count, mql_to_s0, s0_to_s1, s1_to_s2 }: FunnelInput): FunnelResult {
  const product = mql_to_s0 * s0_to_s1 * s1_to_s2;
  if (product <= 0) {
    return { mqls: 0, s0: 0, s1: 0, s2: 0 };
  }
  const mqls = marketing_s2_count / product;
  const s0 = mqls * mql_to_s0;
  const s1 = s0 * s0_to_s1;
  const s2 = s1 * s1_to_s2;
  return { mqls, s0, s1, s2 };
}
