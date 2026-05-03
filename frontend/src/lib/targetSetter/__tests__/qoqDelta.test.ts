import { describe, it, expect } from "vitest";
import { computeMqlQoqDelta } from "../qoqDelta";
import type { Actuals } from "../../../types/snapshot";
import { acmeFY26, mightyOakFY27, fiveQuarterFixture } from "./_fixtures";

function actualsWith(entries: { month_index: number; value: number }[]): Actuals {
  return {
    bookings_by_month: [],
    mql_by_month: entries,
  } as Actuals;
}

describe("computeMqlQoqDelta — Acme FY26 (Feb-start)", () => {
  it("returns delta when all three Q1 months are present (indices 0-2)", () => {
    const actuals = actualsWith([
      { month_index: 0, value: 800 }, // Feb
      { month_index: 1, value: 900 }, // Mar
      { month_index: 2, value: 1100 }, // Apr
    ]);
    const delta = computeMqlQoqDelta({
      snapshot: acmeFY26(),
      actuals,
      asOf: "2026-04-30",    // Q1FY26 complete
      targetQNext: 3900,     // +39.3% vs 2800 observed
    });
    expect(delta).toBeCloseTo(0.393, 2);
  });

  it("returns delta with only 2 months of data", () => {
    const actuals = actualsWith([
      { month_index: 0, value: 800 },
      { month_index: 1, value: 900 },
      // Apr (idx 2) missing — still in progress
    ]);
    const delta = computeMqlQoqDelta({
      snapshot: acmeFY26(),
      actuals,
      asOf: "2026-03-31", // mid-Q1
      targetQNext: 2380,  // +40% vs 1700
    });
    expect(delta).toBeCloseTo(0.4, 2);
  });

  it("returns null when mql_by_month is empty", () => {
    expect(
      computeMqlQoqDelta({
        snapshot: acmeFY26(),
        actuals: actualsWith([]),
        asOf: "2026-04-30",
        targetQNext: 3900,
      }),
    ).toBeNull();
  });

  it("returns null when active quarter has fewer than 2 months of data", () => {
    const actuals = actualsWith([{ month_index: 0, value: 800 }]);
    expect(
      computeMqlQoqDelta({
        snapshot: acmeFY26(),
        actuals,
        asOf: "2026-02-28",
        targetQNext: 1500,
      }),
    ).toBeNull();
  });

  it("returns null when historical sum is 0", () => {
    const actuals = actualsWith([
      { month_index: 0, value: 0 },
      { month_index: 1, value: 0 },
    ]);
    expect(
      computeMqlQoqDelta({
        snapshot: acmeFY26(),
        actuals,
        asOf: "2026-03-31",
        targetQNext: 1000,
      }),
    ).toBeNull();
  });

  it("computes correctly when as_of is in Q4 (Nov-Jan cross-year, indices 9-11)", () => {
    const actuals = actualsWith([
      { month_index: 9, value: 500 },  // Nov 2026
      { month_index: 10, value: 600 }, // Dec 2026
      { month_index: 11, value: 700 }, // Jan 2027
    ]);
    const delta = computeMqlQoqDelta({
      snapshot: acmeFY26(),
      actuals,
      asOf: "2027-01-31",
      targetQNext: 2160, // +20% vs 1800
    });
    expect(delta).toBeCloseTo(0.2, 2);
  });
});

describe("computeMqlQoqDelta — Mighty Oak FY27 (April-start)", () => {
  it("correctly uses April-start Q1 indices (0=Apr, 1=May, 2=Jun)", () => {
    const actuals = actualsWith([
      { month_index: 0, value: 600 }, // Apr
      { month_index: 1, value: 700 }, // May
      { month_index: 2, value: 800 }, // Jun
    ]);
    const delta = computeMqlQoqDelta({
      snapshot: mightyOakFY27(),
      actuals,
      asOf: "2026-06-30", // end of Q1FY27
      targetQNext: 2940,  // +40% vs 2100
    });
    expect(delta).toBeCloseTo(0.4, 2);
  });

  it("returns null when as_of is outside snapshot range", () => {
    const actuals = actualsWith([
      { month_index: 0, value: 600 },
      { month_index: 1, value: 700 },
    ]);
    expect(
      computeMqlQoqDelta({
        snapshot: mightyOakFY27(),
        actuals,
        asOf: "2026-01-15", // before Apr-start FY
        targetQNext: 2000,
      }),
    ).toBeNull();
  });

  it("handles Q4FY27 (Jan-Mar 2027, indices 9-11)", () => {
    const actuals = actualsWith([
      { month_index: 9, value: 400 },  // Jan
      { month_index: 10, value: 500 }, // Feb
    ]);
    const delta = computeMqlQoqDelta({
      snapshot: mightyOakFY27(),
      actuals,
      asOf: "2027-02-28",
      targetQNext: 1800, // +100% vs 900
    });
    expect(delta).toBeCloseTo(1.0, 2);
  });
});

describe("computeMqlQoqDelta — 5-quarter snapshot", () => {
  it("correctly identifies Q4FY25 indices (0-2 = Nov/Dec/Jan in 5Q snapshot)", () => {
    // In the 5Q fixture, months[0]="2025-11-01" through months[14]="2027-01-01".
    // Q4FY25 = indices 0,1,2; Q1FY26 = indices 3,4,5; etc.
    const actuals = actualsWith([
      { month_index: 0, value: 300 }, // Nov 2025
      { month_index: 1, value: 400 }, // Dec 2025
    ]);
    const delta = computeMqlQoqDelta({
      snapshot: fiveQuarterFixture(),
      actuals,
      asOf: "2025-12-31",
      targetQNext: 1400, // +40% vs 700 (no wait, +100% vs 700)
    });
    // sum = 700; delta = 1400/700 - 1 = 1.0
    expect(delta).toBeCloseTo(1.0, 2);
  });
});
