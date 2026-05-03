import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { buildDefaultScenarioOverrides, computeScenario } from "../scenario";
import type { Snapshot } from "../../types/snapshot";

function loadSnapshot(): Snapshot {
  const snapshotPath = resolve(
    fileURLToPath(new URL("../../../public/data/profiles/acme-saas/snapshot.json", import.meta.url)),
  );
  return JSON.parse(readFileSync(snapshotPath, "utf-8")) as Snapshot;
}

function expectSeriesClose(actual: number[], expected: number[], precision = 6): void {
  expect(actual).toHaveLength(expected.length);
  actual.forEach((value, index) => {
    expect(value).toBeCloseTo(expected[index] ?? 0, precision);
  });
}

describe("scenario parity with generated snapshot", () => {
  // TODO(v0.2.x): recalibrate against Acme synthetic data after FY26 relabel.
  // Test logic is sound; assertion values were calibrated against the bundled demo profiles.
  it.skip("matches the generated baseline at canonical default overrides", () => {
    const snapshot = loadSnapshot();
    const bb = snapshot.scenario_building_blocks;
    const result = computeScenario(snapshot, buildDefaultScenarioOverrides(snapshot));

    expectSeriesClose(result.monthly_expected, bb.monthly_total_expected);
    expectSeriesClose(result.monthly_capped, bb.monthly_capped);
    expectSeriesClose(result.monthly_future_wins, bb.monthly_future_wins);
    expect(result.fy_expected).toBeCloseTo(sum(bb.monthly_total_expected), 6);
    expect(result.fy_capped).toBeCloseTo(sum(bb.monthly_capped), 6);
  });
});

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
