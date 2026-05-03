import { describe, it, expect } from "vitest";
import { getQuarterFromDate, determineSolveScope } from "../scope";
import { acmeFY26, fiveQuarterFixture, mightyOakFY27 } from "./_fixtures";

describe("getQuarterFromDate — Acme FY26 (Feb-start)", () => {
  it("Feb 2026 maps to Q1FY26", () => {
    expect(getQuarterFromDate(acmeFY26(), "2026-02-15")).toBe("Q1FY26");
  });
  it("Apr 2026 maps to Q1FY26", () => {
    expect(getQuarterFromDate(acmeFY26(), "2026-04-21")).toBe("Q1FY26");
  });
  it("May 2026 maps to Q2FY26", () => {
    expect(getQuarterFromDate(acmeFY26(), "2026-05-01")).toBe("Q2FY26");
  });
  it("Aug 2026 maps to Q3FY26", () => {
    expect(getQuarterFromDate(acmeFY26(), "2026-08-15")).toBe("Q3FY26");
  });
  it("Jan 2027 maps to Q4FY26", () => {
    expect(getQuarterFromDate(acmeFY26(), "2027-01-15")).toBe("Q4FY26");
  });
  it("returns null for a date outside the snapshot range", () => {
    expect(getQuarterFromDate(acmeFY26(), "2025-10-01")).toBeNull();
  });
});

describe("getQuarterFromDate — Mighty Oak FY27 (April-start)", () => {
  it("Apr 2026 maps to Q1FY27", () => {
    expect(getQuarterFromDate(mightyOakFY27(), "2026-04-15")).toBe("Q1FY27");
  });
  it("Jul 2026 maps to Q2FY27", () => {
    expect(getQuarterFromDate(mightyOakFY27(), "2026-07-01")).toBe("Q2FY27");
  });
  it("Jan 2027 maps to Q4FY27", () => {
    expect(getQuarterFromDate(mightyOakFY27(), "2027-01-31")).toBe("Q4FY27");
  });
  it("Mar 2027 maps to Q4FY27", () => {
    expect(getQuarterFromDate(mightyOakFY27(), "2027-03-15")).toBe("Q4FY27");
  });
});

describe("determineSolveScope — Acme FY26 (4-quarter, Feb-start)", () => {
  it("mid-Q1 as_of: active=Q1FY26, scope=[Q2,Q3,Q4]", () => {
    const { active, scope } = determineSolveScope(acmeFY26(), "2026-04-21");
    expect(active).toBe("Q1FY26");
    expect(scope).toEqual(["Q2FY26", "Q3FY26", "Q4FY26"]);
  });
  it("end-of-Q4 as_of: active=Q4FY26, scope=[]", () => {
    const { active, scope } = determineSolveScope(acmeFY26(), "2027-01-31");
    expect(active).toBe("Q4FY26");
    expect(scope).toEqual([]);
  });
  it("as_of outside snapshot: active=null, scope=all quarters", () => {
    const { active, scope } = determineSolveScope(acmeFY26(), "2025-12-01");
    expect(active).toBeNull();
    expect(scope).toEqual(["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]);
  });
});

describe("determineSolveScope — 5-quarter snapshot", () => {
  it("as_of in Q4FY25 (prior year): active=Q4FY25, scope=[Q1-Q4 FY26]", () => {
    const { active, scope } = determineSolveScope(fiveQuarterFixture(), "2025-12-15");
    expect(active).toBe("Q4FY25");
    expect(scope).toEqual(["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]);
  });
  it("as_of in Q2FY26: active=Q2FY26, scope=[Q3FY26, Q4FY26]", () => {
    const { active, scope } = determineSolveScope(fiveQuarterFixture(), "2026-06-01");
    expect(active).toBe("Q2FY26");
    expect(scope).toEqual(["Q3FY26", "Q4FY26"]);
  });
});

describe("determineSolveScope — Mighty Oak FY27 (April-start)", () => {
  it("mid-Q1 as_of: active=Q1FY27, scope=[Q2,Q3,Q4]", () => {
    const { active, scope } = determineSolveScope(mightyOakFY27(), "2026-05-15");
    expect(active).toBe("Q1FY27");
    expect(scope).toEqual(["Q2FY27", "Q3FY27", "Q4FY27"]);
  });
  it("mid-Q3 as_of: active=Q3FY27, scope=[Q4FY27]", () => {
    const { active, scope } = determineSolveScope(mightyOakFY27(), "2026-11-01");
    expect(active).toBe("Q3FY27");
    expect(scope).toEqual(["Q4FY27"]);
  });
});
