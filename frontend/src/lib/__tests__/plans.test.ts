import { describe, expect, it } from "vitest";

import {
  buildPlanMonthlyReference,
  buildPlanTimingSemantics,
  getPlanFyTarget,
  normalizePlanPreset,
} from "../plans";
import { makeV2BoardPlan, makeV2TimingAwareDraftPlan } from "./planFixtures";

describe("plan preset helpers", () => {
  it("normalizes legacy plan json into a richer domain object", () => {
    const plan = normalizePlanPreset(
      {
        name: "Dec FY26 Board Plan",
        version: "1.0",
        created_date: "2025-12-01",
        quarterly_targets: {
          Q1FY26: 7_000_000,
          Q2FY26: 9_000_000,
        },
        hiring_schedule: [],
        slider_defaults: {
          avg_deal_size: 300_000,
          avg_cycle_days: 90,
        },
      },
      { manifestId: "dec-fy26-board", path: "./dec-fy26-board.json" },
    );

    expect(plan.id).toBe("dec-fy26-board");
    expect(plan.createdDate).toBe("2025-12-01");
    expect(plan.targets.quarterlyBookings.Q2FY26).toBe(9_000_000);
    expect(plan.assumptions.avgDealSize).toBe(300_000);
    expect(plan.source.path).toBe("./dec-fy26-board.json");
    expect(getPlanFyTarget(plan)).toBe(16_000_000);
  });

  it("keeps the legacy even-split fallback for non-v2 assets", () => {
    const plan = normalizePlanPreset({
      name: "Quarter Only",
      version: "1.0",
      created_date: "2026-01-01",
      quarterly_targets: {
        Q2FY26: 9_000_000,
      },
    });

    const reference = buildPlanMonthlyReference(
      ["2026-05-01", "2026-06-01", "2026-07-01"],
      plan,
    );

    expect(reference.basis).toBe("derived_even_quarter_split");
    expect(reference.values).toEqual([3_000_000, 3_000_000, 3_000_000]);
    expect(reference.note).toContain("legacy plan asset");
  });

  it("prefers explicit month-level values on the v2 comparable view", () => {
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());

    const reference = buildPlanMonthlyReference(
      ["2026-02-01", "2026-03-01", "2026-04-01"],
      plan,
    );

    expect(reference.basis).toBe("explicit_monthly_plan");
    expect(reference.values).toEqual([750_000, 825_000, 925_000]);
    expect(reference.rows.every((row) => row.basis === "explicit_monthly_plan")).toBe(true);
  });

  it("preserves v2 month-level AE targets separately from quarter-end rollups", () => {
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());

    expect(plan.targets.explicitMonthlyAeTargets["2026-06-01"]).toBe(24);
    expect(plan.hiring.hasExplicitMonthlySeatPath).toBe(true);
    expect(plan.availability.explicitMonthlyAeTargets).toBe(true);
    expect(plan.targets.quarterEndAeTargets.Q2FY26).toBe(31);
  });

  it("suppresses monthly overlays for v2 comparable views that only support quarterly grain", () => {
    const plan = normalizePlanPreset(makeV2BoardPlan());

    const reference = buildPlanMonthlyReference(
      ["2026-05-01", "2026-06-01", "2026-07-01"],
      plan,
    );

    expect(reference.basis).toBe("unsupported_monthly");
    expect(reference.values).toEqual([0, 0, 0]);
    expect(reference.note).toContain("intentionally suppressed");
  });

  it("describes explicit month shaping and note-only forward context for v2 plans", () => {
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());

    const semantics = buildPlanTimingSemantics(
      ["2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01"],
      plan,
    );

    const comparisonScope = semantics.items.find((item) => item.label === "Comparison Scope");
    const monthlyRail = semantics.items.find((item) => item.label === "Monthly Plan Rail");
    const seatOwnership = semantics.items.find((item) => item.label === "Seat And Pacing Ownership");
    const forwardContext = semantics.items.find((item) => item.label === "Forward Context");

    expect(semantics.selectedPlanName).toBe("Timing Aware Draft");
    expect(comparisonScope?.detail).toContain("Sales-Led Plan");
    expect(monthlyRail?.detail).toContain("month-shaped across the active app horizon");
    expect(seatOwnership?.detail).toContain("explicit month-level seat path");
    expect(forwardContext?.detail).toContain("note-only in v2");
    expect(forwardContext?.detail).toContain("cannot be promoted into active math");
  });
});
