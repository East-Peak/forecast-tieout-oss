import { describe, it, expect } from "vitest";
import { loadScenariosFromSnapshot } from "../scenarios";
import type { Snapshot } from "../../../types/snapshot";
import { acmeFY26 } from "./_fixtures";

const SCENARIO_A = {
  id: "plan",
  label: "Plan",
  description: { primary: "Annual plan", secondary: "FY26" },
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

const SCENARIO_B = {
  id: "marketing-led",
  label: "Marketing-led",
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

function makeSnap(scenarios?: (typeof SCENARIO_A | typeof SCENARIO_B)[]): Snapshot {
  return {
    ...acmeFY26(),
    target_setter: scenarios != null ? { scenarios } : undefined,
  } as unknown as Snapshot;
}

describe("loadScenariosFromSnapshot", () => {
  it("returns [] when target_setter is absent", () => {
    const snap = { ...acmeFY26() } as unknown as Snapshot;
    expect(loadScenariosFromSnapshot(snap)).toEqual([]);
  });

  it("returns [] when target_setter.scenarios is absent", () => {
    const snap = { ...acmeFY26(), target_setter: {} } as unknown as Snapshot;
    expect(loadScenariosFromSnapshot(snap)).toEqual([]);
  });

  it("returns [] when target_setter.scenarios is empty", () => {
    expect(loadScenariosFromSnapshot(makeSnap([]))).toEqual([]);
  });

  it("hydrates a single scenario correctly", () => {
    const result = loadScenariosFromSnapshot(makeSnap([SCENARIO_A]));
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("plan");
    expect(result[0].label).toBe("Plan");
    expect(result[0].win_rate_starting).toBe(0.059);
    expect(result[0].mql_to_s0).toBe(0.18);
    expect(result[0].s1_to_s2).toBe(0.30);
    expect(result[0].segment_share.enterprise).toBe(1.0);
    expect(result[0].acv.enterprise).toBe(250_000);
  });

  it("hydrates multiple scenarios", () => {
    const result = loadScenariosFromSnapshot(makeSnap([SCENARIO_A, SCENARIO_B]));
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("plan");
    expect(result[1].id).toBe("marketing-led");
    expect(result[1].s1_to_s2).toBe(0.40);
    expect(result[1].mql_to_s0).toBe(0.15);
  });

  it("each item is a fresh copy — mutating result does not affect snapshot", () => {
    const snap = makeSnap([SCENARIO_A]);
    const result = loadScenariosFromSnapshot(snap);
    result[0].segment_share.enterprise = 0.5;
    result[0].acv.enterprise = 1;
    expect(snap.target_setter!.scenarios![0].segment_share.enterprise).toBe(1.0);
    expect(snap.target_setter!.scenarios![0].acv.enterprise).toBe(250_000);
  });

  it("description field is passed through when present", () => {
    const result = loadScenariosFromSnapshot(makeSnap([SCENARIO_A]));
    expect(result[0].description?.primary).toBe("Annual plan");
  });
});
