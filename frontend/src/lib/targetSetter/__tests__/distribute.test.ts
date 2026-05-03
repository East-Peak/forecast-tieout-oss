import { describe, it, expect } from "vitest";
import { distributeMonthly, distributeWeekly } from "../distribute";

describe("distributeMonthly", () => {
  it("flat-thirds split for 100 sums to 100 via largest-remainder", () => {
    const parts = distributeMonthly({ quarterly: 100, shape: "flat" });
    expect(parts.length).toBe(3);
    expect(parts.reduce((a, b) => a + b, 0)).toBe(100);
  });
  it("25/35/40 shape for 100 sums to 100", () => {
    const parts = distributeMonthly({ quarterly: 100, shape: "back_loaded" });
    expect(parts.length).toBe(3);
    expect(parts.reduce((a, b) => a + b, 0)).toBe(100);
    expect(parts[2]).toBeGreaterThan(parts[0]);
  });
  it("continuous values pass through as floats when integer=false", () => {
    const parts = distributeMonthly({ quarterly: 100, shape: "flat", integer: false });
    expect(parts[0]).toBeCloseTo(100 / 3, 6);
    expect(parts.reduce((a, b) => a + b, 0)).toBeCloseTo(100, 6);
  });
});

describe("distributeWeekly", () => {
  it("13-way flat split for 130 sums to 130", () => {
    const parts = distributeWeekly({ quarterly: 130 });
    expect(parts.length).toBe(13);
    expect(parts.reduce((a, b) => a + b, 0)).toBe(130);
  });
});
