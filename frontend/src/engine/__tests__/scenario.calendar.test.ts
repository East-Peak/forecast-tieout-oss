import { describe, it, expect } from "vitest";
import {
  monthsForQuarter,
  lastMonthOfQuarter,
  daysUntilQuarterEnd,
  allQuartersFromSnapshot,
} from "../scenario";
import type { Snapshot } from "../../types/snapshot";

const snap = (months: string[], quarterByMonth: string[], overridable: string[] = []): Snapshot =>
  ({
    scenario_building_blocks: {
      months,
      quarter_by_month: quarterByMonth,
      overridable_quarters: overridable,
    },
  } as any);

const acmeFY26 = () =>
  snap(
    ["2026-02-01", "2026-03-01", "2026-04-01",
     "2026-05-01", "2026-06-01", "2026-07-01",
     "2026-08-01", "2026-09-01", "2026-10-01",
     "2026-11-01", "2026-12-01", "2027-01-01"],
    ["Q1FY26","Q1FY26","Q1FY26",
     "Q2FY26","Q2FY26","Q2FY26",
     "Q3FY26","Q3FY26","Q3FY26",
     "Q4FY26","Q4FY26","Q4FY26"],
    ["Q2FY26","Q3FY26","Q4FY26"], // Q1FY26 locked, mirrors current OSS shape
  );

describe("allQuartersFromSnapshot", () => {
  it("returns ALL quarters in fiscal-calendar order, including locked", () => {
    expect(allQuartersFromSnapshot(acmeFY26())).toEqual(
      ["Q1FY26","Q2FY26","Q3FY26","Q4FY26"],
    );
  });
  it("preserves first-occurrence order from quarter_by_month", () => {
    const s = snap(
      ["2025-04-01","2025-05-01","2025-06-01"],
      ["Q4FY25","Q1FY26","Q1FY26"],
      [],
    );
    expect(allQuartersFromSnapshot(s)).toEqual(["Q4FY25","Q1FY26"]);
  });
  it("returns [] for empty snapshot", () => {
    expect(allQuartersFromSnapshot(snap([], []))).toEqual([]);
  });
});

describe("monthsForQuarter", () => {
  it("returns ISO months for the given quarter", () => {
    expect(monthsForQuarter(acmeFY26(), "Q1FY26")).toEqual([
      "2026-02-01","2026-03-01","2026-04-01",
    ]);
  });
  it("returns months for cross-year quarter (Nov-Jan)", () => {
    expect(monthsForQuarter(acmeFY26(), "Q4FY26")).toEqual([
      "2026-11-01","2026-12-01","2027-01-01",
    ]);
  });
  it("returns [] for unknown quarter", () => {
    expect(monthsForQuarter(acmeFY26(), "QZ")).toEqual([]);
  });
});

describe("lastMonthOfQuarter", () => {
  it("returns last chronological month", () => {
    expect(lastMonthOfQuarter(acmeFY26(), "Q1FY26")).toBe("2026-04-01");
  });
  it("returns last month for cross-year quarter", () => {
    expect(lastMonthOfQuarter(acmeFY26(), "Q4FY26")).toBe("2027-01-01");
  });
  it("returns null for unknown quarter", () => {
    expect(lastMonthOfQuarter(acmeFY26(), "QZ")).toBeNull();
  });
});

describe("daysUntilQuarterEnd", () => {
  it("counts days from mid-quarter date to last day of last month", () => {
    // Q1FY26 ends 2026-04-30. From 2026-03-15 = 46 days.
    expect(daysUntilQuarterEnd(acmeFY26(), "2026-03-15", "Q1FY26")).toBe(46);
  });
  it("counts days when as_of is in last month", () => {
    expect(daysUntilQuarterEnd(acmeFY26(), "2026-04-15", "Q1FY26")).toBe(15);
  });
  it("counts days for cross-year quarter (Q4 ends Jan 31)", () => {
    // Q4FY26 ends 2027-01-31. From 2026-12-15 = 47 days.
    expect(daysUntilQuarterEnd(acmeFY26(), "2026-12-15", "Q4FY26")).toBe(47);
  });
  it("returns 0 when as_of is past the quarter end", () => {
    expect(daysUntilQuarterEnd(acmeFY26(), "2026-05-15", "Q1FY26")).toBe(0);
  });
  it("returns 0 for unknown quarter", () => {
    expect(daysUntilQuarterEnd(acmeFY26(), "2026-04-15", "QZ")).toBe(0);
  });
});
