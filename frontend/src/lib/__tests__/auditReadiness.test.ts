import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Snapshot } from "../../types/snapshot";
import { buildAuditReadinessViewModel } from "../auditReadiness";
import { createFallbackOrgProfile } from "../orgProfiles";
import { normalizePlanPreset } from "../plans";
import { makeV2TimingAwareDraftPlan } from "./planFixtures";

function loadSnapshot(): Snapshot {
  const snapshotPath = resolve(
    fileURLToPath(new URL("../../../public/data/profiles/acme-saas/snapshot.json", import.meta.url)),
  );
  return JSON.parse(readFileSync(snapshotPath, "utf-8")) as Snapshot;
}

describe("audit readiness view model", () => {
  it("keeps the finance trust summary aligned to the saved snapshot", () => {
    const snapshot = loadSnapshot();
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());
    const viewModel = buildAuditReadinessViewModel(
      snapshot,
      createFallbackOrgProfile("/data"),
      plan,
    );

    expect(viewModel.topMetrics).toHaveLength(4);
    expect(viewModel.quarterTieoutRows.every((row) => row.status === "green")).toBe(true);
    expect(viewModel.monthLockRows.every((row) => row.status === "green")).toBe(true);
    expect(viewModel.fallbackExceptions).toEqual([]);
    expect(viewModel.connectorPolicyNotes).toHaveLength(3);
    expect(viewModel.planTimingSemantics.selectedPlanName).toBe("Timing Aware Draft");
    expect(
      viewModel.planTimingSemantics.items.find((item) => item.label === "Forward Context")?.detail,
    ).toContain("note-only in v2");
  });
});
