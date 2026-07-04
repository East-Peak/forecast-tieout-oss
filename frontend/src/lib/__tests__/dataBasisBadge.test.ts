import { describe, expect, it } from "vitest";
import { getDataBasisBadge } from "../dataBasisBadge";

describe("getDataBasisBadge", () => {
  it("marks rows with actuals as actual plus projected", () => {
    expect(getDataBasisBadge(1)).toEqual({
      label: "Actual + Projected",
      tone: "actualProjected",
    });
  });

  it("marks zero or missing actuals as projected", () => {
    expect(getDataBasisBadge(0)).toEqual({
      label: "Projected",
      tone: "projected",
    });
    expect(getDataBasisBadge(null)).toEqual({
      label: "Projected",
      tone: "projected",
    });
  });
});
