import { describe, expect, it } from "vitest";
import { getVerdictTint } from "../verdictTint";

describe("getVerdictTint", () => {
  it("uses the negative verdict tint for values below zero", () => {
    expect(getVerdictTint(-1)).toEqual({
      tone: "negative",
      cellClassName: "bg-red-50 text-red-700",
      metricClassName: "border-red-100 bg-red-50 text-red-700",
    });
  });

  it("uses the positive verdict tint for zero and values above zero", () => {
    expect(getVerdictTint(0)).toEqual({
      tone: "positive",
      cellClassName: "bg-green-50 text-green-700",
      metricClassName: "border-green-100 bg-green-50 text-green-700",
    });
    expect(getVerdictTint(1).tone).toBe("positive");
  });

  it("uses a neutral tint when no comparable value exists", () => {
    expect(getVerdictTint(null)).toEqual({
      tone: "neutral",
      cellClassName: "bg-slate-50 text-slate-500",
      metricClassName: "border-slate-200 bg-slate-50 text-slate-600",
    });
  });
});
