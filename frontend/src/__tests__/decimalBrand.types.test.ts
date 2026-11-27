import { describe, expect, it } from "vitest";
import type { Money, TieoutReport } from "../generated/report";

/** Compile-time checks (tsc runs over tests): arithmetic on a report decimal does not type-check. */
describe("report decimals are branded, so arithmetic on them is a compile error", () => {
  it("is enforced by tsc", () => {
    const gap = "1.00" as Money;
    // @ts-expect-error a branded decimal string is not a number
    const a = gap - gap;
    // @ts-expect-error nor can it be multiplied
    const b = gap * 2;
    // @ts-expect-error nor handed to Math
    const c = Math.round(gap);
    // @ts-expect-error a plain string is not a report decimal
    const d: Money = "5.00";
    // @ts-expect-error a report's money field cannot be assigned an arbitrary string
    const e: TieoutReport["gap"]["fiscal_year"]["actual_to_date"] = "5";
    expect([a, b, c, d, e].length).toBe(5);
  });
});
