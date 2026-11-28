import { describe, expect, it } from "vitest";
import type { Facts, PlanDoc } from "../protocol";
import { withAction } from "../yourPlan";

const FACTS: Facts = {
  company: "acme",
  segments: [
    { value: "commercial", label: "Commercial" },
    { value: "enterprise", label: "Enterprise" },
    { value: "mid_market", label: "Mid Market" },
  ],
  months: ["2026-09", "2026-10"],
  max_dollars: "9",
  demo_plan: { hires: [], programs: [] },
};
const EMPTY: PlanDoc = { hires: [], programs: [] };

describe("a draft action", () => {
  it("starts in the first month a plan may start in, with no ramp, on the slice and at the target it was asked for", () => {
    const { plan, id } = withAction(EMPTY, FACTS, { slice: "company", target: "0.2220", origin: "tornado" });
    expect(plan.actions).toEqual([{ id: "action-0", name: "Company win-rate action", driver: "win_rate", slice: "company", start: "2026-09", ramp_months: 0, target: "0.2220" }]);
    expect(id).toBe("action-0");
    expect(EMPTY.actions).toBeUndefined();
  });

  it("is named for its segment in the core's words for it", () => {
    const { plan } = withAction(EMPTY, FACTS, { slice: "enterprise", target: "0.2193", origin: "grid" });
    expect(plan.actions?.[0]).toMatchObject({ slice: "enterprise", name: "Enterprise win-rate action" });
  });

  it("takes an id no other action of the plan holds", () => {
    const first = withAction(EMPTY, FACTS, { slice: "enterprise", target: "0.22", origin: "grid" });
    const second = withAction(first.plan, FACTS, { slice: "commercial", target: "0.22", origin: "grid" });
    expect(second.plan.actions?.map((a) => a.id)).toEqual(["action-0", "action-1"]);
    const gap = { ...second.plan, actions: second.plan.actions!.filter((a) => a.id !== "action-0") };
    expect(withAction(gap, FACTS, { slice: "mid_market", target: "0.22", origin: "grid" }).id).toBe("action-0");
  });

  it("is not added a second time for a slice that already has one: the one it has is the one to show", () => {
    const first = withAction(EMPTY, FACTS, { slice: "enterprise", target: "0.22", origin: "grid" });
    const again = withAction(first.plan, FACTS, { slice: "enterprise", target: "0.30", origin: "tornado" });
    expect(again.plan).toBe(first.plan);
    expect(again.id).toBe("action-0");
  });

  it("is not added when every segment already has one, as no more can be told apart (the core refuses overlaps)", () => {
    let plan = EMPTY;
    for (const s of ["commercial", "enterprise", "mid_market"]) plan = withAction(plan, FACTS, { slice: s, target: "0.2", origin: "grid" }).plan;
    const full = withAction(plan, FACTS, { slice: "company", target: "0.2", origin: "tornado" });
    expect(full.plan).toBe(plan);
    expect(full.id).toBeNull();
  });
});

describe("a draft action on another driver", () => {
  it("names its driver and is named for it in the core's words", () => {
    const size = withAction(EMPTY, FACTS, { slice: "enterprise", driver: "won_arr", target: "413835.73", origin: "grid" });
    expect(size.plan.actions).toEqual([
      { id: "action-0", name: "Enterprise deal-size action", driver: "won_arr", slice: "enterprise", start: "2026-09", ramp_months: 0, target: "413835.73" },
    ]);
    const creation = withAction(EMPTY, FACTS, { slice: "company", driver: "productivity", target: "2.0662", origin: "tornado" });
    expect(creation.plan.actions?.[0]).toMatchObject({ name: "Company creation action", driver: "productivity", target: "2.0662" });
  });

  it("is a second action where the slice has one on another driver, and the same one where it is the same driver", () => {
    const rate = withAction(EMPTY, FACTS, { slice: "enterprise", target: "0.22", origin: "grid" });
    const size = withAction(rate.plan, FACTS, { slice: "enterprise", driver: "won_arr", target: "400000", origin: "grid" });
    expect(size.plan.actions?.map((a) => [a.id, a.driver])).toEqual([["action-0", "win_rate"], ["action-1", "won_arr"]]);
    const again = withAction(size.plan, FACTS, { slice: "enterprise", driver: "won_arr", target: "500000", origin: "tornado" });
    expect(again.plan).toBe(size.plan);
    expect(again.id).toBe("action-1");
  });

  it("holds as many as three drivers on every segment, and no driver more than once on a slice", () => {
    let plan = EMPTY;
    for (const driver of ["win_rate", "won_arr", "productivity"] as const) for (const s of ["commercial", "enterprise", "mid_market"]) plan = withAction(plan, FACTS, { slice: s, driver, target: "1", origin: "grid" }).plan;
    expect(plan.actions).toHaveLength(9);
    expect(withAction(plan, FACTS, { slice: "company", driver: "won_arr", target: "1", origin: "tornado" })).toMatchObject({ plan, id: null });
  });
});
