import { describe, it, expect } from "vitest";
import { solve } from "../solve";
import { acmeFY26, fiveQuarterFixture, mightyOakFY27 } from "./_fixtures";

// ---------------------------------------------------------------------------
// Inline scenarios — no imported constants from scenarios.ts
// All values are synthetic; no production data.
// ---------------------------------------------------------------------------

/** 90/10 Ent/Com split — typical marketing scenario */
const SCENARIO_90_10 = {
  id: "mkt_90_10",
  label: "Marketing 90/10",
  win_rate_starting: 0.059,
  win_rate_created: 0.16,
  push_rate: 0.90,
  loss_rate: 0.10,
  ae_self_gen_pct: 0.29,
  mql_to_s0: 0.15,
  s0_to_s1: 0.70,
  s1_to_s2: 0.40,
  segment_share: { enterprise: 0.9, commercial: 0.1 },
  acv: { enterprise: 250_000, commercial: 75_000 },
};

/** 100/0 plan scenario — commercial segment gets 0 share */
const SCENARIO_100_0 = {
  id: "plan_100_0",
  label: "Plan 100/0",
  win_rate_starting: 0.059,
  win_rate_created: 0.16,
  push_rate: 0.90,
  loss_rate: 0.10,
  ae_self_gen_pct: 0.29,
  mql_to_s0: 0.18,
  s0_to_s1: 0.70,
  s1_to_s2: 0.30,
  segment_share: { enterprise: 1.0, commercial: 0.0 },
  acv: { enterprise: 250_000, commercial: 75_000 },
};

/** 3-segment scenario: enterprise / mid_market / commercial */
const SCENARIO_3SEG = {
  id: "three_seg",
  label: "3-Segment",
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

/** Bookings targets keyed to Acme FY26 quarters */
const ACME_TARGETS: Record<string, number> = {
  Q1FY26: 1_500_000,
  Q2FY26: 3_000_000,
  Q3FY26: 5_000_000,
  Q4FY26: 9_000_000,
};

/** Bookings targets keyed to Mighty Oak FY27 quarters */
const OAK_TARGETS: Record<string, number> = {
  Q1FY27: 2_000_000,
  Q2FY27: 5_000_000,
  Q3FY27: 9_000_000,
  Q4FY27: 18_000_000,
};

// ---------------------------------------------------------------------------
// Fixture 1 — 4-quarter Acme FY26, 90/10 scenario
// as_of mid-Q1: active=Q1FY26, scope=[Q2, Q3, Q4]
// ---------------------------------------------------------------------------
describe("solve — Acme FY26 / 90-10 scenario (4-quarter)", () => {
  it("produces non-negative outputs for all solve-scope quarters", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    expect(result.active_quarter).toBe("Q1FY26");
    expect(result.scope).toEqual(["Q2FY26", "Q3FY26", "Q4FY26"]);
    for (const q of result.quarters) {
      expect(q.mqls).toBeGreaterThanOrEqual(0);
      expect(q.s0).toBeGreaterThanOrEqual(0);
      expect(q.created_pipe).toBeGreaterThanOrEqual(0);
    }
  });

  it("per-segment total S2 counts are consistent with AE+marketing split", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    for (const q of result.quarters) {
      const totalSum = Object.values(q.total_s2_by_segment).reduce((a, b) => a + b, 0);
      const marketingSum = Object.values(q.marketing_s2_by_segment).reduce((a, b) => a + b, 0);
      expect(marketingSum).toBeLessThanOrEqual(totalSum + 1e-6);
      expect(q.marketing_s2_total).toBeCloseTo(marketingSum, 3);
    }
  });

  it("tributary additivity holds at each funnel stage (marketing + outbound = total)", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    for (const q of result.quarters) {
      expect(q.s0 + q.outbound_s0).toBeCloseTo(q.total_s0, 3);
      expect(q.s1 + q.outbound_s1).toBeCloseTo(q.total_s1, 3);
      expect(q.marketing_s2_total + q.outbound_s2).toBeCloseTo(q.total_s2, 3);
    }
  });

  it("no invariant-break warnings on well-formed scenario", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    const hasTributaryBreak = result.warnings.some(
      (w) => w.includes("Invariant break") || w.includes("residual"),
    );
    expect(hasTributaryBreak).toBe(false);
  });

  it("roundtrip: forward(inverse(bookings)) recovers bookings for each quarter", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    for (const q of result.quarters) {
      const implied =
        q.starting_pipe * SCENARIO_90_10.win_rate_starting +
        q.created_pipe * SCENARIO_90_10.win_rate_created;
      if (!q.infeasible) {
        expect(implied).toBeCloseTo(q.bookings_target, 0);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Fixture 2 — 100/0 plan scenario (commercial always zero)
// ---------------------------------------------------------------------------
describe("solve — 100/0 plan scenario", () => {
  it("commercial counts are zero", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_100_0,
    });
    for (const q of result.quarters) {
      expect(q.total_s2_by_segment.commercial).toBe(0);
      expect(q.marketing_s2_by_segment.commercial).toBe(0);
    }
  });

  it("no division-by-zero even with commercial ACV unused", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_100_0,
    });
    for (const q of result.quarters) {
      expect(Number.isFinite(q.mqls)).toBe(true);
      expect(Number.isFinite(q.total_s2_by_segment.enterprise)).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// Fixture 3 — 3-segment scenario (enterprise/mid_market/commercial)
// Validates generic iteration — no hardcoded segment names
// ---------------------------------------------------------------------------
describe("solve — 3-segment scenario", () => {
  it("produces outputs for all three segments", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_3SEG,
    });
    for (const q of result.quarters) {
      expect(q.total_s2_by_segment).toHaveProperty("enterprise");
      expect(q.total_s2_by_segment).toHaveProperty("mid_market");
      expect(q.total_s2_by_segment).toHaveProperty("commercial");
      expect(q.marketing_s2_by_segment).toHaveProperty("enterprise");
      expect(q.marketing_s2_by_segment).toHaveProperty("mid_market");
      expect(q.marketing_s2_by_segment).toHaveProperty("commercial");
    }
  });

  it("segment shares sum correctly: all 3 segment pipes add up to created_pipe", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_3SEG,
    });
    // Import splitSegments inline check
    for (const q of result.quarters) {
      const totalSegS2 = Object.values(q.total_s2_by_segment).reduce((a, b) => a + b, 0);
      expect(totalSegS2).toBeCloseTo(q.total_s2, 3);
    }
  });

  it("tributary additivity holds for 3-segment scenario", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_3SEG,
    });
    for (const q of result.quarters) {
      expect(q.s0 + q.outbound_s0).toBeCloseTo(q.total_s0, 3);
      expect(q.marketing_s2_total + q.outbound_s2).toBeCloseTo(q.total_s2, 3);
    }
  });

  it("no invariant-break warnings with 3-segment scenario", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_3SEG,
    });
    const hasTributaryBreak = result.warnings.some((w) => w.includes("Invariant break"));
    expect(hasTributaryBreak).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Fixture 4 — 5-quarter snapshot
// ---------------------------------------------------------------------------
describe("solve — 5-quarter snapshot", () => {
  const FIVE_Q_TARGETS: Record<string, number> = {
    Q4FY25: 500_000,
    Q1FY26: 1_500_000,
    Q2FY26: 3_000_000,
    Q3FY26: 5_000_000,
    Q4FY26: 9_000_000,
  };

  it("mid-Q1FY26 as_of: active=Q1FY26, scope=[Q2-Q4 FY26]", () => {
    const result = solve({
      snapshot: fiveQuarterFixture(),
      as_of: "2026-03-15",
      starting_pipe: 8_000_000,
      bookings_targets: FIVE_Q_TARGETS,
      scenario: SCENARIO_90_10,
    });
    expect(result.active_quarter).toBe("Q1FY26");
    expect(result.scope).toEqual(["Q2FY26", "Q3FY26", "Q4FY26"]);
    expect(result.quarters).toHaveLength(3);
  });

  it("all solved quarters have non-negative created_pipe and mqls", () => {
    const result = solve({
      snapshot: fiveQuarterFixture(),
      as_of: "2026-03-15",
      starting_pipe: 8_000_000,
      bookings_targets: FIVE_Q_TARGETS,
      scenario: SCENARIO_90_10,
    });
    for (const q of result.quarters) {
      expect(q.created_pipe).toBeGreaterThanOrEqual(0);
      expect(q.mqls).toBeGreaterThanOrEqual(0);
    }
  });
});

// ---------------------------------------------------------------------------
// Fixture 5 — Mighty Oak FY27 (April-start fiscal year)
// ---------------------------------------------------------------------------
describe("solve — Mighty Oak FY27 (April-start)", () => {
  it("mid-Q1 as_of: active=Q1FY27, scope=[Q2,Q3,Q4]", () => {
    const result = solve({
      snapshot: mightyOakFY27(),
      as_of: "2026-05-15",
      starting_pipe: 10_000_000,
      bookings_targets: OAK_TARGETS,
      scenario: SCENARIO_90_10,
    });
    expect(result.active_quarter).toBe("Q1FY27");
    expect(result.scope).toEqual(["Q2FY27", "Q3FY27", "Q4FY27"]);
  });
});

// ---------------------------------------------------------------------------
// Fixture 6 — Infeasible quarter
// starting_pipe × win_rate_starting >= bookings_target → infeasible: true
// ---------------------------------------------------------------------------
describe("solve — infeasible target", () => {
  it("flags infeasible when starting_pipe × win_rate >= bookings_target", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 200_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    // All scope quarters should be infeasible given huge starting pipe
    for (const q of result.quarters) {
      expect(q.infeasible).toBe(true);
      expect(q.mqls).toBe(0);
    }
  });
});

// ---------------------------------------------------------------------------
// Fixture 7 — Active quarter YTD bookings
// ---------------------------------------------------------------------------
describe("solve — active quarter YTD", () => {
  it("exposes YTD bookings and remaining gap for active quarter", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
      active_ytd_bookings: 500_000,
    });
    expect(result.active_ytd_bookings).toBe(500_000);
    expect(result.active_remaining_gap).toBeCloseTo(
      ACME_TARGETS.Q1FY26 - 500_000,
      0,
    );
  });

  it("active_remaining_gap is 0 when no active quarter", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2025-10-01", // outside snapshot range
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
      active_ytd_bookings: 400_000,
    });
    expect(result.active_quarter).toBeNull();
    expect(result.active_remaining_gap).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Fixture 8 — Waterfall conservation warning
// ---------------------------------------------------------------------------
describe("solve — waterfall conservation warning", () => {
  it("emits a warning when starting-pipe rates sum outside [0.9, 1.1]", () => {
    const degenerate = {
      ...SCENARIO_90_10,
      win_rate_starting: 0.5,
      push_rate: 0.5,
      loss_rate: 0.5,
    };
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: degenerate,
    });
    const conservation = result.warnings.find((w) => w.includes("Waterfall conservation"));
    expect(conservation).toBeDefined();
    expect(conservation).toContain("1.500");
  });

  it("does not warn when rates sum within [0.9, 1.1]", () => {
    const result = solve({
      snapshot: acmeFY26(),
      as_of: "2026-04-21",
      starting_pipe: 10_000_000,
      bookings_targets: ACME_TARGETS,
      scenario: SCENARIO_90_10,
    });
    const conservation = result.warnings.find((w) => w.includes("Waterfall conservation"));
    expect(conservation).toBeUndefined();
  });
});
