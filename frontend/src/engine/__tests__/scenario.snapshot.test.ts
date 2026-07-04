import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { buildDefaultScenarioOverrides, computeScenario } from "../scenario";
import type { Snapshot } from "../../types/snapshot";

function loadSnapshot(): Snapshot {
  const snapshotPath = resolve(
    fileURLToPath(new URL("../../../public/data/profiles/sapling-industries/snapshot.json", import.meta.url)),
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
  it("uses scenario building block baselines at canonical default overrides", () => {
    const snapshot = loadSnapshot();
    const bb = snapshot.scenario_building_blocks;
    const result = computeScenario(snapshot, buildDefaultScenarioOverrides(snapshot));
    const expectedMonthly = bb.monthly_inventory_wins.map(
      (value, index) => value + (bb.monthly_future_wins[index] ?? 0),
    );

    expectSeriesClose(result.monthly_expected, expectedMonthly);
    expectSeriesClose(result.monthly_future_wins, bb.monthly_future_wins);
    result.monthly_capped.forEach((value, index) => {
      expect(value).toBeLessThanOrEqual((result.monthly_capacity[index] ?? 0) + 1e-6);
    });
    expect(result.fy_expected).toBeCloseTo(sum(expectedMonthly), 6);
    expect(result.fy_capped).toBeCloseTo(sum(result.monthly_capped), 6);
  });
});

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
