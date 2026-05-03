/**
 * segmentSplit.ts — Split pipeline dollars across segments and derive deal counts.
 *
 * Genericized: segment names are runtime keys, not literal types.  All segment
 * access uses Object.keys() iteration — no hardcoded ".enterprise"/".commercial".
 */

import type { SegmentKey } from "../../types/targetSetter";

export interface SegmentSplitInput {
  created_pipe: number;
  segment_share: Record<SegmentKey, number>;
  acv: Record<SegmentKey, number>;
}

export interface SegmentSplitResult {
  /** Pipeline dollars attributed to each segment. */
  pipe_by_segment: Record<SegmentKey, number>;
  /** Deal count for each segment (pipe / ACV, guarded against ACV ≤ 0). */
  count_by_segment: Record<SegmentKey, number>;
  /** Sum of all per-segment deal counts. */
  total_count: number;
}

export function splitSegments({ created_pipe, segment_share, acv }: SegmentSplitInput): SegmentSplitResult {
  const pipe_by_segment: Record<SegmentKey, number> = {};
  const count_by_segment: Record<SegmentKey, number> = {};
  let total_count = 0;

  for (const seg of Object.keys(segment_share)) {
    const share = segment_share[seg] ?? 0;
    const seg_acv = (acv[seg] != null && acv[seg] > 0) ? acv[seg] : 1;
    const pipe = created_pipe * share;
    const count = pipe / seg_acv;
    pipe_by_segment[seg] = pipe;
    count_by_segment[seg] = count;
    total_count += count;
  }

  return { pipe_by_segment, count_by_segment, total_count };
}
