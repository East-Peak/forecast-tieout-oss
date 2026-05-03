import { describe, it, expect } from "vitest";
import { buildObservedScenario } from "../observedScenario";
import type { Snapshot } from "../../../types/snapshot";
import { acmeFY26 } from "./_fixtures";

/** Minimal SnapshotScenario for observed_scenario injection. */
const OBS_SCENARIO = {
  id: "observed",
  label: "Observed",
  description: { primary: "Trailing 90d calibrated", secondary: "refreshed Apr 2026" },
  win_rate_starting: 0.06,
  win_rate_created: 0.15,
  push_rate: 0.93,
  loss_rate: 0.08,
  ae_self_gen_pct: 0.30,
  mql_to_s0: 0.22,
  s0_to_s1: 0.81,
  s1_to_s2: 0.32,
  segment_share: { enterprise: 0.85, commercial: 0.15 },
  acv: { enterprise: 280_000, commercial: 80_000 },
};

function makeSnapshotWithObs(obs: typeof OBS_SCENARIO | undefined): Snapshot {
  return {
    ...acmeFY26(),
    target_setter: obs ? { observed_scenario: obs } : {},
  } as unknown as Snapshot;
}

describe("buildObservedScenario", () => {
  it("returns null when target_setter is absent", () => {
    const snap = { ...acmeFY26() } as unknown as Snapshot;
    // No target_setter key at all
    expect(buildObservedScenario(snap)).toBeNull();
  });

  it("returns null when target_setter.observed_scenario is absent", () => {
    const snap = makeSnapshotWithObs(undefined);
    expect(buildObservedScenario(snap)).toBeNull();
  });

  it("hydrates all rate fields correctly", () => {
    const result = buildObservedScenario(makeSnapshotWithObs(OBS_SCENARIO));
    expect(result).not.toBeNull();
    expect(result!.id).toBe("observed");
    expect(result!.label).toBe("Observed");
    expect(result!.win_rate_starting).toBe(0.06);
    expect(result!.win_rate_created).toBe(0.15);
    expect(result!.push_rate).toBe(0.93);
    expect(result!.loss_rate).toBe(0.08);
    expect(result!.ae_self_gen_pct).toBe(0.30);
    expect(result!.mql_to_s0).toBe(0.22);
    expect(result!.s0_to_s1).toBe(0.81);
    expect(result!.s1_to_s2).toBe(0.32);
  });

  it("hydrates description when present", () => {
    const result = buildObservedScenario(makeSnapshotWithObs(OBS_SCENARIO));
    expect(result!.description?.primary).toBe("Trailing 90d calibrated");
    expect(result!.description?.secondary).toBe("refreshed Apr 2026");
  });

  it("hydrates segment_share and acv correctly", () => {
    const result = buildObservedScenario(makeSnapshotWithObs(OBS_SCENARIO));
    expect(result!.segment_share.enterprise).toBe(0.85);
    expect(result!.segment_share.commercial).toBe(0.15);
    expect(result!.acv.enterprise).toBe(280_000);
    expect(result!.acv.commercial).toBe(80_000);
  });

  it("returns a fresh copy — mutating result does not affect snapshot", () => {
    const snap = makeSnapshotWithObs(OBS_SCENARIO);
    const result = buildObservedScenario(snap)!;
    result.segment_share.enterprise = 0.99;
    result.acv.enterprise = 999_999;
    // Original snapshot values should be unchanged
    expect(snap.target_setter!.observed_scenario!.segment_share.enterprise).toBe(0.85);
    expect(snap.target_setter!.observed_scenario!.acv.enterprise).toBe(280_000);
  });
});
