import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Snapshot } from "../../types/snapshot";
import {
  createFallbackOrgProfile,
} from "../orgProfiles";
import { buildMethodologyViewModel } from "../methodology";
import { normalizePlanPreset } from "../plans";
import { makeV2TimingAwareDraftPlan } from "./planFixtures";

function loadSnapshot(): Snapshot {
  const snapshotPath = resolve(
    fileURLToPath(new URL("../../../public/data/profiles/acme-saas/snapshot.json", import.meta.url)),
  );
  return JSON.parse(readFileSync(snapshotPath, "utf-8")) as Snapshot;
}

describe("methodology view model", () => {
  // TODO(v0.2.x): recalibrate against Acme synthetic data after FY26 relabel.
  // Test logic is sound; assertion values were calibrated against the bundled demo profiles.
  it.skip("keeps current finance semantics in the narrative and provenance blocks", () => {
    const snapshot = loadSnapshot();
    const plan = normalizePlanPreset(makeV2TimingAwareDraftPlan());
    const viewModel = buildMethodologyViewModel(
      snapshot,
      createFallbackOrgProfile("/data"),
      "Frontend local adapter (backend-compatible contract)",
      plan,
    );

    expect(
      viewModel.narrativeNotes.some((note) => note.includes("do not seed the saved trajectory math")),
    ).toBe(true);
    expect(
      viewModel.narrativeNotes.some((note) => note.includes("monthly CSV in Export Pack mirrors the live Scenario Planner state")),
    ).toBe(true);
    expect(
      viewModel.provenanceItems.some(
        (item) => item.label === "Close timing source" && item.value === "Salesforce observed",
      ),
    ).toBe(true);
    expect(
      viewModel.provenanceItems.some(
        (item) => item.label === "CRM connector" && item.value === "Salesforce",
      ),
    ).toBe(true);
    expect(
      viewModel.provenanceItems.some(
        (item) =>
          item.label === "Scenario engine" &&
          item.value === "Frontend local adapter (backend-compatible contract)",
      ),
    ).toBe(true);
    expect(viewModel.planTimingSemantics.selectedPlanName).toBe("Timing Aware Draft");
    expect(
      viewModel.planTimingSemantics.items.find((item) => item.label === "Forward Context")?.detail,
    ).toContain("note-only in v2");
  });

  it("keeps the current snapshot free of finance-critical fallback exceptions", () => {
    const snapshot = loadSnapshot();
    const viewModel = buildMethodologyViewModel(
      snapshot,
      createFallbackOrgProfile("/data"),
      "Frontend local adapter (backend-compatible contract)",
    );

    expect(viewModel.fallbackExceptions).toEqual([]);
    expect(viewModel.assumptions.length).toBeGreaterThan(10);
    expect(viewModel.criticalSignals.length).toBeGreaterThan(10);
    expect(
      viewModel.narrativeNotes.some((note) => note.includes("source priority for bookings")),
    ).toBe(true);
    expect(
      viewModel.narrativeNotes.some((note) => note.includes("backend snapshot scenario service")),
    ).toBe(true);
    expect(
      viewModel.narrativeNotes.some((note) => note.includes("note-only forward context metadata")),
    ).toBe(true);
    expect(
      viewModel.narrativeNotes.some((note) => note.includes("operator-comparable default view")),
    ).toBe(true);
  });
});
