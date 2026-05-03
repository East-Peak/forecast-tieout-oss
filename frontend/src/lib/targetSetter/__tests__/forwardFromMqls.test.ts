import { describe, it, expect } from "vitest";
import { forwardFromMqls } from "../forwardFromMqls";
import { inverseQuarter } from "../inverseWaterfall";
import { splitSegments } from "../segmentSplit";
import { splitAeMarketing, computeFunnel } from "../funnel";

const SCENARIO = {
  id: "observed" as const,
  label: "Test",
  win_rate_starting: 0.059,
  win_rate_created: 0.16,
  push_rate: 0.90,
  loss_rate: 0.10,
  ae_self_gen_pct: 0.29,
  mql_to_s0: 0.18,
  s0_to_s1: 0.70,
  s1_to_s2: 0.30,
  segment_share: { enterprise: 0.9, commercial: 0.1 },
  acv: { enterprise: 250_000, commercial: 75_000 },
};

describe("forwardFromMqls", () => {
  it("produces bookings >= starting_pipe × win_rate_starting", () => {
    const result = forwardFromMqls({
      mqls: 1000,
      starting_pipe: 10_000_000,
      scenario: SCENARIO,
    });
    expect(result.bookings).toBeGreaterThanOrEqual(10_000_000 * 0.059);
  });

  it("zero MQLs still produces starting_won", () => {
    const result = forwardFromMqls({
      mqls: 0,
      starting_pipe: 10_000_000,
      scenario: SCENARIO,
    });
    expect(result.bookings).toBeCloseTo(10_000_000 * 0.059, 0);
    expect(result.ending_pipe).toBeCloseTo(10_000_000 * 0.90, 0);
  });
});

describe("forwardFromMqls — roundtrip with inverse chain", () => {
  it("mqls from inverse chain reproduces bookings within floating-point tolerance", () => {
    const starting_pipe = 10_000_000;
    const bookings_target = 5_000_000;

    // Run inverse chain: bookings_target → mqls
    const inv = inverseQuarter({ starting_pipe, bookings_target, rates: SCENARIO });
    const marketing = splitAeMarketing({ total_pipe: inv.created_pipe, ae_self_gen_pct: SCENARIO.ae_self_gen_pct });
    const segs = splitSegments({
      created_pipe: marketing.marketing_pipe,
      segment_share: SCENARIO.segment_share,
      acv: SCENARIO.acv,
    });
    const funnel = computeFunnel({
      marketing_s2_count: segs.total_count,
      mql_to_s0: SCENARIO.mql_to_s0,
      s0_to_s1: SCENARIO.s0_to_s1,
      s1_to_s2: SCENARIO.s1_to_s2,
    });

    // Now run forward chain with those MQLs — should return bookings_target
    const fwd = forwardFromMqls({ mqls: funnel.mqls, starting_pipe, scenario: SCENARIO });

    expect(fwd.bookings).toBeCloseTo(bookings_target, 0); // within $1
  });

  it("roundtrip holds for a 3-segment scenario (enterprise/mid_market/commercial)", () => {
    const scenario3 = {
      id: "three_seg" as const,
      label: "3-Segment Test",
      win_rate_starting: 0.059,
      win_rate_created: 0.16,
      push_rate: 0.90,
      loss_rate: 0.10,
      ae_self_gen_pct: 0.25,
      mql_to_s0: 0.18,
      s0_to_s1: 0.70,
      s1_to_s2: 0.30,
      segment_share: { enterprise: 0.6, mid_market: 0.3, commercial: 0.1 },
      acv: { enterprise: 300_000, mid_market: 120_000, commercial: 50_000 },
    };

    const starting_pipe = 8_000_000;
    const bookings_target = 3_000_000;

    const inv = inverseQuarter({ starting_pipe, bookings_target, rates: scenario3 });
    const marketing = splitAeMarketing({ total_pipe: inv.created_pipe, ae_self_gen_pct: scenario3.ae_self_gen_pct });
    const segs = splitSegments({
      created_pipe: marketing.marketing_pipe,
      segment_share: scenario3.segment_share,
      acv: scenario3.acv,
    });
    const funnel = computeFunnel({
      marketing_s2_count: segs.total_count,
      mql_to_s0: scenario3.mql_to_s0,
      s0_to_s1: scenario3.s0_to_s1,
      s1_to_s2: scenario3.s1_to_s2,
    });

    const fwd = forwardFromMqls({ mqls: funnel.mqls, starting_pipe, scenario: scenario3 });

    expect(fwd.bookings).toBeCloseTo(bookings_target, 0);
  });
});
