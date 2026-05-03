import { describe, it, expect } from "vitest";
import { extractQuarterlyBookingsFromPlan } from "../planExtract";
import { acmeFY26, fiveQuarterFixture, mightyOakFY27 } from "./_fixtures";

/** Build a plan with monthly values keyed by ISO date strings. */
function makePlan(monthly: Record<string, number>, shape: "camel" | "snake" = "snake") {
  if (shape === "camel") {
    return { components: { sales_led: { arrTargets: { monthly } } } };
  }
  return { components: { sales_led: { arr_targets: { monthly } } } };
}

/** Full Acme FY26 monthly map (all 12 months covered). */
const acmeMonthly: Record<string, number> = {
  "2026-02-01": 100_000,
  "2026-03-01": 200_000,
  "2026-04-01": 300_000,
  "2026-05-01": 400_000,
  "2026-06-01": 500_000,
  "2026-07-01": 600_000,
  "2026-08-01": 700_000,
  "2026-09-01": 800_000,
  "2026-10-01": 900_000,
  "2026-11-01": 1_000_000,
  "2026-12-01": 1_100_000,
  "2027-01-01": 1_200_000,
};

describe("extractQuarterlyBookingsFromPlan — Acme FY26 (snake_case plan)", () => {
  it("sums three months per quarter correctly", () => {
    const result = extractQuarterlyBookingsFromPlan(acmeFY26(), makePlan(acmeMonthly));
    expect(result).not.toBeNull();
    expect(result!["Q1FY26"]).toBe(600_000);   // 100+200+300
    expect(result!["Q2FY26"]).toBe(1_500_000); // 400+500+600
    expect(result!["Q3FY26"]).toBe(2_400_000); // 700+800+900
    expect(result!["Q4FY26"]).toBe(3_300_000); // 1000+1100+1200
  });

  it("handles normalized camelCase plan shape", () => {
    const result = extractQuarterlyBookingsFromPlan(acmeFY26(), makePlan(acmeMonthly, "camel"));
    expect(result).not.toBeNull();
    expect(result!["Q1FY26"]).toBe(600_000);
    expect(result!["Q4FY26"]).toBe(3_300_000);
  });
});

describe("extractQuarterlyBookingsFromPlan — locked active quarter included", () => {
  it("includes locked Q1FY26 even though overridable_quarters omits it", () => {
    // acmeFY26() has overridable_quarters = [Q2FY26, Q3FY26, Q4FY26].
    // extractQuarterlyBookingsFromPlan must use allQuartersFromSnapshot (not getOverridableQuarters)
    // so Q1FY26 appears in the result.
    const plan = makePlan({
      "2026-02-01": 1_000_000,
      "2026-03-01": 1_500_000,
      "2026-04-01": 2_000_000,
      "2026-05-01": 0,
      "2026-06-01": 0,
      "2026-07-01": 0,
      "2026-08-01": 0,
      "2026-09-01": 0,
      "2026-10-01": 0,
      "2026-11-01": 0,
      "2026-12-01": 0,
      "2027-01-01": 0,
    });
    const out = extractQuarterlyBookingsFromPlan(acmeFY26(), plan);
    expect(out).not.toBeNull();
    expect(out!["Q1FY26"]).toBe(4_500_000); // 1M+1.5M+2M — Q1 included even though locked
    expect(out!["Q2FY26"]).toBe(0);
    expect(out!["Q3FY26"]).toBe(0);
    expect(out!["Q4FY26"]).toBe(0);
  });
});

describe("extractQuarterlyBookingsFromPlan — null/error cases", () => {
  it("returns null for null plan", () => {
    expect(extractQuarterlyBookingsFromPlan(acmeFY26(), null)).toBeNull();
  });
  it("returns null when plan lacks sales_led", () => {
    expect(extractQuarterlyBookingsFromPlan(acmeFY26(), { components: {} })).toBeNull();
  });
  it("returns null when a required month is missing from the plan", () => {
    const incomplete = { ...acmeMonthly };
    delete (incomplete as any)["2026-03-01"]; // missing Mar
    expect(extractQuarterlyBookingsFromPlan(acmeFY26(), makePlan(incomplete))).toBeNull();
  });
  it("returns null when a month value is non-numeric", () => {
    const bad = { ...acmeMonthly, "2026-03-01": "not-a-number" } as any;
    expect(extractQuarterlyBookingsFromPlan(acmeFY26(), makePlan(bad))).toBeNull();
  });
});

describe("extractQuarterlyBookingsFromPlan — 5-quarter snapshot", () => {
  it("returns all 5 quarters including Q4FY25", () => {
    const monthly: Record<string, number> = {
      "2025-11-01": 50_000,
      "2025-12-01": 60_000,
      "2026-01-01": 70_000,
      "2026-02-01": 100_000,
      "2026-03-01": 200_000,
      "2026-04-01": 300_000,
      "2026-05-01": 400_000,
      "2026-06-01": 500_000,
      "2026-07-01": 600_000,
      "2026-08-01": 700_000,
      "2026-09-01": 800_000,
      "2026-10-01": 900_000,
      "2026-11-01": 1_000_000,
      "2026-12-01": 1_100_000,
      "2027-01-01": 1_200_000,
    };
    const result = extractQuarterlyBookingsFromPlan(fiveQuarterFixture(), makePlan(monthly));
    expect(result).not.toBeNull();
    expect(Object.keys(result!).length).toBe(5);
    expect(result!["Q4FY25"]).toBe(180_000);   // 50+60+70
    expect(result!["Q1FY26"]).toBe(600_000);   // 100+200+300
    expect(result!["Q4FY26"]).toBe(3_300_000); // 1000+1100+1200
  });
});

describe("extractQuarterlyBookingsFromPlan — Mighty Oak FY27 (April-start)", () => {
  it("correctly maps April-start quarters", () => {
    const monthly: Record<string, number> = {
      "2026-04-01": 100_000,
      "2026-05-01": 200_000,
      "2026-06-01": 300_000,
      "2026-07-01": 400_000,
      "2026-08-01": 500_000,
      "2026-09-01": 600_000,
      "2026-10-01": 700_000,
      "2026-11-01": 800_000,
      "2026-12-01": 900_000,
      "2027-01-01": 1_000_000,
      "2027-02-01": 1_100_000,
      "2027-03-01": 1_200_000,
    };
    const result = extractQuarterlyBookingsFromPlan(mightyOakFY27(), makePlan(monthly));
    expect(result).not.toBeNull();
    expect(result!["Q1FY27"]).toBe(600_000);   // Apr+May+Jun
    expect(result!["Q2FY27"]).toBe(1_500_000); // Jul+Aug+Sep
    expect(result!["Q3FY27"]).toBe(2_400_000); // Oct+Nov+Dec
    expect(result!["Q4FY27"]).toBe(3_300_000); // Jan+Feb+Mar
  });

  it("includes locked Q1FY27 even though it is not overridable", () => {
    const monthly: Record<string, number> = {
      "2026-04-01": 1_000_000,
      "2026-05-01": 1_500_000,
      "2026-06-01": 2_000_000,
      "2026-07-01": 0,
      "2026-08-01": 0,
      "2026-09-01": 0,
      "2026-10-01": 0,
      "2026-11-01": 0,
      "2026-12-01": 0,
      "2027-01-01": 0,
      "2027-02-01": 0,
      "2027-03-01": 0,
    };
    const result = extractQuarterlyBookingsFromPlan(mightyOakFY27(), makePlan(monthly));
    expect(result).not.toBeNull();
    expect(result!["Q1FY27"]).toBe(4_500_000); // locked Q1 included
  });
});
