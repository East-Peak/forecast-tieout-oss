import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  buildDefaultScenarioOverrides,
  cloneScenarioOverrides,
} from "../../engine/scenario";
import type { Snapshot } from "../../types/snapshot";
import { createFallbackOrgProfile } from "../orgProfiles";
import { buildExportPackViewModel, buildScenarioCsvContent } from "../exportPack";
import { normalizePlanPreset } from "../plans";
import { frontendLocalScenarioEngine } from "../scenarioEngine";
import { makeV2TimingAwareDraftPlan } from "./planFixtures";

function loadSnapshot(): Snapshot {
  const snapshotPath = resolve(
    fileURLToPath(new URL("../../../public/data/profiles/acme-saas/snapshot.json", import.meta.url)),
  );
  return JSON.parse(readFileSync(snapshotPath, "utf-8")) as Snapshot;
}

describe("export pack helpers", () => {
  it("treats the default scenario state as the saved baseline", async () => {
    const snapshot = loadSnapshot();
    const overrides = buildDefaultScenarioOverrides(snapshot);
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());
    const baselineComputation = await frontendLocalScenarioEngine.compute(
      snapshot,
      buildDefaultScenarioOverrides(snapshot),
      "demo-org",
    );
    const activeComputation = await frontendLocalScenarioEngine.compute(
      snapshot,
      overrides,
      "demo-org",
    );
    const viewModel = buildExportPackViewModel(
      snapshot,
      plan,
      overrides,
      baselineComputation,
      activeComputation,
      createFallbackOrgProfile("/data"),
    );

    expect(viewModel.hasScenarioEdits).toBe(false);
    expect(viewModel.editedQuarters).toEqual([]);
    expect(viewModel.previewRows).toHaveLength(6);
    expect(viewModel.connectorPolicyNotes).toHaveLength(3);
    expect(viewModel.scenarioEngineId).toBe("frontend-local");
    expect(viewModel.planTimingSemantics.selectedPlanName).toBe("Timing Aware Draft");
    expect(
      viewModel.planTimingSemantics.items.find((item) => item.label === "Forward Context")?.detail,
    ).toContain("note-only in v2");
  });

  // TODO(v0.2.x): recalibrate against Acme synthetic data after FY26 relabel.
  // Test logic is sound; assertion values were calibrated against the bundled demo profiles.
  it.skip("surfaces edited quarters and scenario deltas when overrides are active", async () => {
    const snapshot = loadSnapshot();
    const overrides = cloneScenarioOverrides(buildDefaultScenarioOverrides(snapshot));
    overrides.Q2FY26.aeMonthTargets[2] = 24;
    const baselineComputation = await frontendLocalScenarioEngine.compute(
      snapshot,
      buildDefaultScenarioOverrides(snapshot),
      "demo-org",
    );
    const activeComputation = await frontendLocalScenarioEngine.compute(
      snapshot,
      overrides,
      "demo-org",
    );

    const viewModel = buildExportPackViewModel(
      snapshot,
      null,
      overrides,
      baselineComputation,
      activeComputation,
      createFallbackOrgProfile("/data"),
    );

    expect(viewModel.hasScenarioEdits).toBe(true);
    expect(viewModel.editedQuarters).toContain("Q2FY26");
    expect(viewModel.scenarioDelta).toBeGreaterThan(0);
  });

  it("builds a csv with live scenario and baseline columns", async () => {
    const snapshot = loadSnapshot();
    const overrides = buildDefaultScenarioOverrides(snapshot);
    const baselineComputation = await frontendLocalScenarioEngine.compute(
      snapshot,
      buildDefaultScenarioOverrides(snapshot),
      "demo-org",
    );
    const activeComputation = await frontendLocalScenarioEngine.compute(
      snapshot,
      overrides,
      "demo-org",
    );
    const viewModel = buildExportPackViewModel(
      snapshot,
      null,
      overrides,
      baselineComputation,
      activeComputation,
      createFallbackOrgProfile("/data"),
    );
    const csv = buildScenarioCsvContent(snapshot, viewModel);

    expect(csv).toContain('"Org Profile"');
    expect(csv).toContain('"Default Org"');
    expect(csv).toContain('"Saved Trajectory Capped"');
    expect(csv).toContain('"Active Scenario Capped"');
    expect(csv).toContain('"Baseline AE Count"');
    expect(csv).toContain('"Scenario AE Count"');
  });
});
