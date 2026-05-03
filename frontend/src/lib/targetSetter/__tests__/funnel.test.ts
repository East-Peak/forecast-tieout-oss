import { describe, it, expect } from "vitest";
import { computeFunnel, splitAeMarketing } from "../funnel";

describe("splitAeMarketing", () => {
  it("29% AE self-gen leaves 71% marketing", () => {
    const result = splitAeMarketing({ total_pipe: 1_000_000, ae_self_gen_pct: 0.29 });
    expect(result.marketing_pipe).toBeCloseTo(710_000, 0);
    expect(result.ae_pipe).toBeCloseTo(290_000, 0);
  });
  it("clamps ae_self_gen_pct >= 1 to 0.99", () => {
    const result = splitAeMarketing({ total_pipe: 1_000_000, ae_self_gen_pct: 1.0 });
    expect(result.marketing_pipe).toBeCloseTo(10_000, 0);
    expect(result.ae_pipe).toBeCloseTo(990_000, 0);
  });
});

describe("computeFunnel", () => {
  it("backs out MQLs from marketing S2 count using full funnel product", () => {
    const result = computeFunnel({
      marketing_s2_count: 10,
      mql_to_s0: 0.18,
      s0_to_s1: 0.70,
      s1_to_s2: 0.30,
    });
    const expected_mqls = 10 / (0.18 * 0.70 * 0.30);
    expect(result.mqls).toBeCloseTo(expected_mqls, 3);
    expect(result.s0).toBeCloseTo(expected_mqls * 0.18, 3);
    expect(result.s1).toBeCloseTo(expected_mqls * 0.18 * 0.70, 3);
  });
  it("returns zeros when funnel product is zero", () => {
    const result = computeFunnel({
      marketing_s2_count: 10,
      mql_to_s0: 0,
      s0_to_s1: 0.70,
      s1_to_s2: 0.30,
    });
    expect(result.mqls).toBe(0);
    expect(result.s0).toBe(0);
    expect(result.s1).toBe(0);
  });
});
