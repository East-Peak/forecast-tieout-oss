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
