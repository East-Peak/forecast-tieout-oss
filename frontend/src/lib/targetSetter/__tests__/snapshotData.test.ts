import { describe, it, expect } from "vitest";
import { computeStartingPipe, computeYtdBookings } from "../snapshotData";
import { acmeFY26, fiveQuarterFixture, mightyOakFY27 } from "./_fixtures";

describe("computeStartingPipe", () => {
  it("sums total_value across S2, S3, S4, S5 only", () => {
    const inventory = [
      { stage: "S0", count: 10, total_value: 100_000 },
      { stage: "S1", count: 5, total_value: 500_000 },
      { stage: "S2", count: 3, total_value: 600_000 },
      { stage: "S3", count: 2, total_value: 400_000 },
      { stage: "S4", count: 1, total_value: 300_000 },
      { stage: "S5", count: 1, total_value: 250_000 },
    ];
    expect(computeStartingPipe(inventory)).toBe(1_550_000);
  });
  it("returns 0 for empty inventory", () => {
    expect(computeStartingPipe([])).toBe(0);
  });
  it("excludes S0 and S1 stages", () => {
    const inventory = [
      { stage: "S0", total_value: 999_999 },
      { stage: "S1", total_value: 999_999 },
    ];
    expect(computeStartingPipe(inventory)).toBe(0);
  });
});

describe("computeYtdBookings — Acme FY26 (Feb-start)", () => {
  it("sums bookings for completed months of active quarter before as_of", () => {
    const bookings = [
      { month: "2026-02-01", total: 200_000 },
      { month: "2026-03-01", total: 300_000 },
      { month: "2026-04-01", total: 150_000 },
      { month: "2026-05-01", total: 500_000 }, // Q2FY26 — excluded
    ];
    expect(
      computeYtdBookings(acmeFY26(), {
        bookings,
        activeQuarter: "Q1FY26",
        asOf: "2026-04-21",
      }),
    // Apr 1 <= Apr 21 → included. Total = 200k + 300k + 150k = 650k.
    ).toBe(650_000);
  });

  it("excludes future months after as_of", () => {
    const bookings = [
      { month: "2026-02-01", total: 200_000 },
      { month: "2026-03-01", total: 300_000 },
      { month: "2026-04-01", total: 150_000 }, // Apr 1 > Feb 28 as_of
    ];
    expect(
      computeYtdBookings(acmeFY26(), {
        bookings,
        activeQuarter: "Q1FY26",
        asOf: "2026-02-28",
      }),
    ).toBe(200_000); // only Feb
  });

  it("returns 0 when active quarter has no bookings in range", () => {
    const bookings = [{ month: "2026-05-01", total: 500_000 }];
    expect(
      computeYtdBookings(acmeFY26(), {
        bookings,
        activeQuarter: "Q1FY26",
        asOf: "2026-04-21",
      }),
    ).toBe(0);
  });

  it("handles cross-year Q4 quarter (Nov-Jan)", () => {
    const bookings = [
      { month: "2026-11-01", total: 100_000 },
      { month: "2026-12-01", total: 200_000 },
      { month: "2027-01-01", total: 300_000 },
      { month: "2026-08-01", total: 999_999 }, // Q3FY26 — excluded
    ];
    expect(
      computeYtdBookings(acmeFY26(), {
        bookings,
        activeQuarter: "Q4FY26",
        asOf: "2026-12-31",
      }),
    ).toBe(300_000); // Nov + Dec (Jan 1 > Dec 31 as_of)
  });
});

describe("computeYtdBookings — 5-quarter snapshot", () => {
  it("correctly identifies Q4FY25 months (Nov-Jan) in 5Q snapshot", () => {
    const bookings = [
      { month: "2025-11-01", total: 100_000 },
      { month: "2025-12-01", total: 150_000 },
      { month: "2026-01-01", total: 200_000 },
      { month: "2026-02-01", total: 999_999 }, // Q1FY26 — excluded
    ];
    expect(
      computeYtdBookings(fiveQuarterFixture(), {
        bookings,
        activeQuarter: "Q4FY25",
        asOf: "2025-12-31",
      }),
    ).toBe(250_000); // Nov + Dec only
  });
});

describe("computeYtdBookings — Mighty Oak FY27 (April-start)", () => {
  it("correctly maps April-start Q1 months", () => {
    const bookings = [
      { month: "2026-04-01", total: 100_000 },
      { month: "2026-05-01", total: 150_000 },
      { month: "2026-06-01", total: 200_000 },
      { month: "2026-07-01", total: 999_999 }, // Q2FY27 — excluded
    ];
    // Jun 1 <= Jun 15, so all three Q1FY27 months are included.
    expect(
      computeYtdBookings(mightyOakFY27(), {
        bookings,
        activeQuarter: "Q1FY27",
        asOf: "2026-06-15",
      }),
    ).toBe(450_000); // Apr + May + Jun
  });

  it("excludes months after as_of in April-start calendar", () => {
    const bookings = [
      { month: "2026-04-01", total: 100_000 },
      { month: "2026-05-01", total: 150_000 },
      { month: "2026-06-01", total: 200_000 },
    ];
    expect(
      computeYtdBookings(mightyOakFY27(), {
        bookings,
        activeQuarter: "Q1FY27",
        asOf: "2026-04-30",
      }),
    ).toBe(100_000); // only Apr (May 1 > Apr 30)
  });
});
