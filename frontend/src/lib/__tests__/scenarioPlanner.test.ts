import { describe, expect, it } from "vitest";

import { normalizePlanPreset } from "../plans";
import { getQuarterPlanReference } from "../scenarioPlanner";
import { makeV2TimingAwareDraftPlan } from "./planFixtures";

describe("scenario planner plan references", () => {
  it("prefers selected-plan pacing fields and falls back field-by-field when a v2 package is partial", () => {
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());

    const reference = getQuarterPlanReference(
      "Q2FY26",
      {
        top_down: { aes: 29 },
        funnel_tieout: {
          mqls_weekly: {
            plan: 396,
          },
        },
        conversion_rates: {
          mql_to_s0: {
            blended: {
              source: "plan",
              rate: 0.22,
            },
          },
          s0_to_s1: {
            blended: {
              source: "snapshot",
              rate: 0.74,
            },
          },
          s1_to_s2: {
            blended: {
              source: "snapshot",
              rate: 0.28,
            },
          },
        },
      },
      plan,
      {
        snapshotAsOf: "2026-03-30",
        evaluationAsOf: "2026-03-30",
      },
    );

    expect(reference.comparable).toBe(true);
    expect(reference.quarterlySupported).toBe(true);
    expect(reference.quarterEndAeTarget).toBe(31);
    expect(reference.mqlWeekly).toBe(113);
    expect(reference.mqlToS0).toBe(0.18);
    expect(reference.s0ToS1).toBe(0.74);
    expect(reference.s1ToS2).toBe(0.28);
    expect(reference.avgDealSize).toBeNull();
    expect(reference.provenance.mqlWeekly?.presentationState).toBe("approved");
    expect(reference.provenance.mqlToS0?.presentationState).toBe("approved");
    expect(reference.provenance.s0ToS1?.presentationState).toBe("fallback");
    expect(reference.note).toContain("fall back to the saved snapshot field-by-field");
  });
});
