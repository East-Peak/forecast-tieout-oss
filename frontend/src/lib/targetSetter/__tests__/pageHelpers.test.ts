/**
 * pageHelpers.test.ts
 *
 * Tests for buildRateByEdge, buildScenarioOptions, buildRoleCards,
 * and buildTotalS0Footer.
 */

import { describe, it, expect } from "vitest";
import {
  buildRateByEdge,
  buildScenarioOptions,
  buildRoleCards,
  buildTotalS0Footer,
} from "../pageHelpers";
import type { Snapshot } from "../../../types/snapshot";
import type { Scenario } from "../../../types/targetSetter";

// ---------------------------------------------------------------------------
// Stub factories
// ---------------------------------------------------------------------------

const stubSnapshot = (overrides: Record<string, unknown> = {}): Snapshot =>
  ({
    model_output: { funnel_health: { funnel_rate_descriptions: {} } },
    target_setter: undefined,
    ...overrides,
  }) as unknown as Snapshot;

const stubScenario = (overrides: Partial<Scenario> = {}): Scenario => ({
  id: "test",
  label: "Test",
  win_rate_starting: 0.06,
  win_rate_created: 0.16,
  push_rate: 0.94,
  loss_rate: 0.08,
  ae_self_gen_pct: 0.3,
  mql_to_s0: 0.15,
  s0_to_s1: 0.55,
  s1_to_s2: 0.25,
  segment_share: { enterprise: 1.0 },
  acv: { enterprise: 250000 },
  ...overrides,
});

// ---------------------------------------------------------------------------
// buildScenarioOptions
// ---------------------------------------------------------------------------

describe("buildScenarioOptions", () => {
  it("returns [] when target_setter absent", () => {
    expect(buildScenarioOptions(stubSnapshot())).toEqual([]);
  });

  it("returns only observed when scenarios absent", () => {
    const snap = stubSnapshot({
      target_setter: {
        observed_scenario: stubScenario({
          id: "observed",
          label: "Observed",
          description: { primary: "p", secondary: "s" },
        }),
      },
    });
    const opts = buildScenarioOptions(snap);
    expect(opts.map((o) => o.id)).toEqual(["observed"]);
    expect(opts[0].primaryLine).toBe("p");
    expect(opts[0].secondaryLine).toBe("s");
  });

  it("returns only scenarios when observed absent", () => {
    const snap = stubSnapshot({
      target_setter: {
        scenarios: [
          stubScenario({
            id: "marketing-led",
            label: "ML",
            description: { primary: "p", secondary: "s" },
          }),
        ],
      },
    });
    const opts = buildScenarioOptions(snap);
    expect(opts.map((o) => o.id)).toEqual(["marketing-led"]);
  });

  it("ids exactly mirror snapshot scenario ids + observed", () => {
    const snap = stubSnapshot({
      target_setter: {
        observed_scenario: stubScenario({ id: "observed" }),
        scenarios: [
          stubScenario({ id: "marketing-led" }),
          stubScenario({ id: "ambitious" }),
        ],
      },
    });
    const opts = buildScenarioOptions(snap);
    expect(opts.map((o) => o.id)).toEqual([
      "observed",
      "marketing-led",
      "ambitious",
    ]);
  });

  it("appends custom pill when includeCustom=true", () => {
    const snap = stubSnapshot({
      target_setter: {
        observed_scenario: stubScenario({ id: "observed" }),
      },
    });
    const opts = buildScenarioOptions(snap, true);
    expect(opts.map((o) => o.id)).toEqual(["observed", "custom"]);
    const custom = opts.find((o) => o.id === "custom")!;
    expect(custom.label).toBe("Custom");
    expect(custom.primaryLine).toBe("Your adjustments");
    expect(custom.secondaryLine).toBe("session-only");
  });

  it("does not include custom pill when includeCustom=false (default)", () => {
    const snap = stubSnapshot({
      target_setter: {
        observed_scenario: stubScenario({ id: "observed" }),
      },
    });
    const opts = buildScenarioOptions(snap);
    expect(opts.map((o) => o.id)).not.toContain("custom");
  });

  it("falls back to empty strings for description when absent", () => {
    const snap = stubSnapshot({
      target_setter: {
        observed_scenario: stubScenario({ id: "observed" }),
        scenarios: [stubScenario({ id: "x" })],
      },
    });
    const opts = buildScenarioOptions(snap);
    for (const o of opts) {
      expect(o.primaryLine).toBe("");
      expect(o.secondaryLine).toBe("");
    }
  });
});

// ---------------------------------------------------------------------------
// buildRateByEdge — observed scenario
// ---------------------------------------------------------------------------

describe("buildRateByEdge for observed scenario", () => {
  it("coerces Acme-shape {label, lookback_days} into RateProvenance", () => {
    const snap = stubSnapshot({
      model_output: {
        funnel_health: {
          funnel_rate_descriptions: {
            mql_to_sql: { label: "Backed by 90-day cohort", lookback_days: 90 },
            sql_to_opp: { label: "S0→S1 from cohort", lookback_days: 90 },
            opp_to_s2: { label: "S1→S2 from cohort", lookback_days: 90 },
          },
        },
      },
    });
    const observed = stubScenario({
      id: "observed",
      mql_to_s0: 0.18,
      s0_to_s1: 0.65,
      s1_to_s2: 0.3,
    });
    const r = buildRateByEdge(observed, snap);
    // value falls back to scenario value because raw lacks `value` key
    expect(r.mql_to_s0.value).toBe(0.18);
    // source pulled from raw `label`
    expect(r.mql_to_s0.source).toBe("Backed by 90-day cohort");
    // lookback_days preserved
    expect(r.mql_to_s0.lookback_days).toBe(90);
    // fallback methodology applied
    expect(r.mql_to_s0.methodology).toBe("observed");
    expect(r.s0_to_s1.value).toBe(0.65);
    expect(r.s1_to_s2.value).toBe(0.3);
  });

  it("coerces other-demo-shape {value, source} into RateProvenance", () => {
    const snap = stubSnapshot({
      model_output: {
        funnel_health: {
          funnel_rate_descriptions: {
            mql_to_s0: { value: 0.2, source: "config" },
            s0_to_s1: { value: 0.65, source: "config" },
            s1_to_s2: { value: 0.3, source: "config" },
          },
        },
      },
    });
    const observed = stubScenario({ id: "observed", mql_to_s0: 0.2 });
    const r = buildRateByEdge(observed, snap);
    expect(r.mql_to_s0.value).toBe(0.2);
    expect(r.mql_to_s0.source).toBe("config");
    expect(r.mql_to_s0.n).toBeNull();
    expect(r.mql_to_s0.lookback_days).toBeUndefined();
  });

  it("falls back when funnel_rate_descriptions absent", () => {
    const snap = stubSnapshot();
    const observed = stubScenario({ id: "observed", mql_to_s0: 0.18 });
    const r = buildRateByEdge(observed, snap);
    expect(r.mql_to_s0.value).toBe(0.18);
    expect(r.mql_to_s0.source).toBe("snapshot");
    expect(r.mql_to_s0.methodology).toBe("observed");
  });

  it("preserves methodology field when present in raw description", () => {
    const snap = stubSnapshot({
      model_output: {
        funnel_health: {
          funnel_rate_descriptions: {
            mql_to_s0: { value: 0.15, source: "config", methodology: "static_seed" },
            s0_to_s1: { value: 0.55, source: "config" },
            s1_to_s2: { value: 0.25, source: "config" },
          },
        },
      },
    });
    const observed = stubScenario({ id: "observed", mql_to_s0: 0.15 });
    const r = buildRateByEdge(observed, snap);
    expect(r.mql_to_s0.methodology).toBe("static_seed");
    // s0_to_s1 has no methodology key → falls back
    expect(r.s0_to_s1.methodology).toBe("observed");
  });

  it("outbound_to_s0 has same-rate-proxy suffix on source", () => {
    const snap = stubSnapshot({
      model_output: {
        funnel_health: {
          funnel_rate_descriptions: {
            mql_to_s0: { value: 0.2, source: "config" },
            s0_to_s1: { value: 0.65, source: "config" },
            s1_to_s2: { value: 0.3, source: "config" },
          },
        },
      },
    });
    const observed = stubScenario({ id: "observed", mql_to_s0: 0.2 });
    const r = buildRateByEdge(observed, snap);
    expect(r.outbound_to_s0.source).toBe("config · same-rate proxy");
    expect(r.outbound_to_s0.methodology).toBe(
      "MQL→S0 rate applied to outbound conversion",
    );
    expect(r.outbound_to_s0.value).toBe(r.mql_to_s0.value);
  });

  it("falls back outbound_to_s0 source correctly when descriptions absent", () => {
    const snap = stubSnapshot();
    const observed = stubScenario({ id: "observed", mql_to_s0: 0.18 });
    const r = buildRateByEdge(observed, snap);
    expect(r.outbound_to_s0.source).toBe("snapshot · same-rate proxy");
  });
});

// ---------------------------------------------------------------------------
// buildRateByEdge — non-observed scenario
// ---------------------------------------------------------------------------

describe("buildRateByEdge for non-observed scenario", () => {
  it("uses scenario.description as source/methodology", () => {
    const snap = stubSnapshot();
    const scenario = stubScenario({
      id: "marketing-led",
      label: "Marketing-led",
      mql_to_s0: 0.3,
      s0_to_s1: 0.7,
      s1_to_s2: 0.4,
      description: { primary: "Aspirational", secondary: "Synthetic demo" },
    });
    const r = buildRateByEdge(scenario, snap);
    expect(r.mql_to_s0.source).toBe("Aspirational");
    expect(r.mql_to_s0.methodology).toBe("Synthetic demo");
    expect(r.mql_to_s0.value).toBe(0.3);
    expect(r.outbound_to_s0.methodology).toBe("Synthetic demo · same-rate proxy");
    expect(r.s0_to_s1.value).toBe(0.7);
    expect(r.s1_to_s2.value).toBe(0.4);
  });

  it("falls back to scenario.label when description absent", () => {
    const snap = stubSnapshot();
    const scenario = stubScenario({ id: "x", label: "X", mql_to_s0: 0.5 });
    const r = buildRateByEdge(scenario, snap);
    expect(r.mql_to_s0.source).toBe("X");
    expect(r.mql_to_s0.value).toBe(0.5);
  });

  it("n is null for synthetic provenance", () => {
    const snap = stubSnapshot();
    const scenario = stubScenario({ id: "y", label: "Y" });
    const r = buildRateByEdge(scenario, snap);
    expect(r.mql_to_s0.n).toBeNull();
    expect(r.outbound_to_s0.n).toBeNull();
    expect(r.s0_to_s1.n).toBeNull();
    expect(r.s1_to_s2.n).toBeNull();
  });

  it("does NOT contain hardcoded internal strings", () => {
    const snap = stubSnapshot();
    const scenario = stubScenario({ id: "arbitrary", label: "Arbitrary" });
    const r = buildRateByEdge(scenario, snap);
    const allStrings = JSON.stringify(r);
    expect(allStrings).not.toContain("Caroline");
    expect(allStrings).not.toContain("marketing_v2");
    expect(allStrings).not.toContain("Mar 2026");
    expect(allStrings).not.toContain("Q1 OKR");
  });
});

// ---------------------------------------------------------------------------
// buildRoleCards
// ---------------------------------------------------------------------------

describe("buildRoleCards", () => {
  it("aggregates totals and per-quarter from input rows", () => {
    const rows = [
      { quarter: "Q1FY26", mqls: 100, s0: 50, outbound_s0: 30, marketing_s2_total: 10 },
      { quarter: "Q2FY26", mqls: 200, s0: 100, outbound_s0: 60, marketing_s2_total: 20 },
    ];
    const cards = buildRoleCards(rows, 0.5);
    expect(cards).toHaveLength(3);

    const marketing = cards[0];
    expect(marketing.role).toBe("Marketing");
    expect(marketing.metricLabel).toBe("MQLs needed");
    expect(marketing.totalValue).toBe(300);
    expect(marketing.integer).toBe(true);
    expect(marketing.qoqDelta).toBe(0.5);
    expect(marketing.perQuarter).toEqual([
      { quarter: "Q1FY26", value: 100 },
      { quarter: "Q2FY26", value: 200 },
    ]);
    expect(marketing.secondary?.totalValue).toBe(150);
    expect(marketing.secondary?.label).toBe("→ Marketing-sourced S0 needed");
    expect(marketing.secondary?.perQuarter).toEqual([
      { quarter: "Q1FY26", value: 50 },
      { quarter: "Q2FY26", value: 100 },
    ]);

    const outbound = cards[1];
    expect(outbound.role).toBe("Outbound");
    expect(outbound.totalValue).toBe(90);
    expect(outbound.qoqDelta).toBeNull();

    const sales = cards[2];
    expect(sales.role).toBe("Sales");
    expect(sales.totalValue).toBe(30);
    expect(sales.qoqDelta).toBeNull();
  });

  it("passes null mqlQoq through to Marketing card", () => {
    const rows = [
      { quarter: "Q1FY26", mqls: 50, s0: 25, outbound_s0: 10, marketing_s2_total: 5 },
    ];
    const cards = buildRoleCards(rows, null);
    expect(cards[0].qoqDelta).toBeNull();
  });

  it("handles empty quarters array", () => {
    const cards = buildRoleCards([], null);
    expect(cards).toHaveLength(3);
    for (const c of cards) {
      expect(c.totalValue).toBe(0);
      expect(c.perQuarter).toEqual([]);
    }
    expect(cards[0].secondary?.totalValue).toBe(0);
  });

  it("produces integer:true on all cards", () => {
    const rows = [
      { quarter: "Q1FY26", mqls: 1, s0: 1, outbound_s0: 1, marketing_s2_total: 1 },
    ];
    const cards = buildRoleCards(rows, null);
    for (const c of cards) {
      expect(c.integer).toBe(true);
    }
    expect(cards[0].secondary?.integer).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// buildTotalS0Footer
// ---------------------------------------------------------------------------

describe("buildTotalS0Footer", () => {
  it("sums total_s0 across quarters", () => {
    const rows = [
      { quarter: "Q1FY26", s0: 50, outbound_s0: 30, total_s0: 80 },
      { quarter: "Q2FY26", s0: 100, outbound_s0: 60, total_s0: 160 },
    ];
    const f = buildTotalS0Footer(rows);
    expect(f.totalValue).toBe(240);
    expect(f.integer).toBe(true);
    expect(f.label).toBe("Total S0 needed (Marketing + Outbound)");
    expect(f.perQuarter).toEqual([
      { quarter: "Q1FY26", value: 80 },
      { quarter: "Q2FY26", value: 160 },
    ]);
    expect(f.components).toEqual([
      { label: "Marketing", value: 150 },
      { label: "Outbound", value: 90 },
    ]);
  });

  it("handles empty quarters array", () => {
    const f = buildTotalS0Footer([]);
    expect(f.totalValue).toBe(0);
    expect(f.perQuarter).toEqual([]);
    expect(f.components).toEqual([
      { label: "Marketing", value: 0 },
      { label: "Outbound", value: 0 },
    ]);
  });

  it("components Marketing + Outbound sum to totalValue", () => {
    const rows = [
      { quarter: "Q1", s0: 33, outbound_s0: 17, total_s0: 50 },
      { quarter: "Q2", s0: 67, outbound_s0: 33, total_s0: 100 },
    ];
    const f = buildTotalS0Footer(rows);
    const componentSum = f.components!.reduce((acc, c) => acc + c.value, 0);
    expect(componentSum).toBe(f.totalValue);
  });
});
