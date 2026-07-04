import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { computeScenario } from "../scenario";
import type { ScenarioOverrides } from "../scenario";
import type { Snapshot } from "../../types/snapshot";

const vectorPath = resolve(
  fileURLToPath(new URL("../../../../tests/parity/fixtures/scenario-golden-vectors.json", import.meta.url)),
);

interface GoldenVectors {
  tolerancePolicy: {
    countFields: string[];
    floats: {
      absoluteEpsilon: number;
      relativeEpsilon: number;
    };
  };
  cases: Array<{
    id: string;
    input: {
      snapshot: Snapshot;
      overrides: ScenarioOverrides;
    };
    expected: {
      result: Record<string, unknown>;
    };
  }>;
}

function loadVectors(): GoldenVectors {
  return JSON.parse(readFileSync(vectorPath, "utf-8")) as GoldenVectors;
}

function expectNumberClose(
  actual: number,
  expected: number,
  policy: GoldenVectors["tolerancePolicy"],
  path: string,
): void {
  const scale = Math.max(1, Math.abs(expected));
  const allowed = Math.max(
    policy.floats.absoluteEpsilon,
    policy.floats.relativeEpsilon * scale,
  );
  expect(Math.abs(actual - expected), path).toBeLessThanOrEqual(allowed);
}

function requiresExactNumber(path: string, policy: GoldenVectors["tolerancePolicy"]): boolean {
  return policy.countFields.some((field) => path.includes(`.${field}[`));
}

function expectValueClose(
  actual: unknown,
  expected: unknown,
  policy: GoldenVectors["tolerancePolicy"],
  path: string,
): void {
  if (typeof expected === "boolean" || typeof actual === "boolean") {
    expect(actual, path).toEqual(expected);
    return;
  }
  if (typeof expected === "number" && typeof actual === "number") {
    if (Number.isInteger(expected) && Number.isInteger(actual)) {
      expect(actual, path).toBe(expected);
      return;
    }
    if (requiresExactNumber(path, policy)) {
      expect(actual, path).toBe(expected);
      return;
    }
    expectNumberClose(actual, expected, policy, path);
    return;
  }
  if (typeof expected === "string" || expected === null) {
    expect(actual, path).toEqual(expected);
    return;
  }
  if (Array.isArray(expected)) {
    expect(Array.isArray(actual), path).toBe(true);
    const actualArray = actual as unknown[];
    expect(actualArray.length, path).toBe(expected.length);
    expected.forEach((expectedValue, index) => {
      expectValueClose(actualArray[index], expectedValue, policy, `${path}[${index}]`);
    });
    return;
  }
  if (typeof expected === "object" && expected !== null) {
    expect(typeof actual, path).toBe("object");
    expect(actual, path).not.toBeNull();
    const actualRecord = actual as Record<string, unknown>;
    const expectedRecord = expected as Record<string, unknown>;
    expect(Object.keys(actualRecord).sort(), path).toEqual(Object.keys(expectedRecord).sort());
    Object.entries(expectedRecord).forEach(([key, expectedValue]) => {
      expectValueClose(actualRecord[key], expectedValue, policy, `${path}.${key}`);
    });
    return;
  }
  expect(actual, path).toEqual(expected);
}

describe("scenario engine golden-vector parity", () => {
  const vectors = loadVectors();

  it.each(vectors.cases)("$id", (testCase) => {
    const result = computeScenario(testCase.input.snapshot, testCase.input.overrides);

    expectValueClose(
      {
        months: testCase.input.snapshot.scenario_building_blocks.months,
        ...result,
      },
      testCase.expected.result,
      vectors.tolerancePolicy,
      testCase.id,
    );
  });
});
