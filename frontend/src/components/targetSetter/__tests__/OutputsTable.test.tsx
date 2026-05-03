import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OutputsTable } from "../OutputsTable";
import type { QuarterTargets } from "../../../types/targetSetter";

const sampleQuarter: QuarterTargets = {
  quarter: "Q2",
  starting_pipe: 10_000_000,
  bookings_target: 5_000_000,
  created_pipe: 20_000_000,
  infeasible: false,
  won_from_starting: 590_000,
  won_from_created: 3_200_000,
  marketing_pipe: 14_200_000,
  marketing_s2_total: 50,
  marketing_s2_by_segment: { seg_a: 45, seg_b: 5 },
  total_s2_by_segment: { seg_a: 60, seg_b: 7 },
  mqls: 2000,
  s0: 360,
  s1: 252,
  total_s0: 508,
  total_s1: 355,
  total_s2: 67,
  outbound_s0: 148,
  outbound_s1: 103,
  outbound_s2: 17,
  ending_pipe: 15_000_000,
};

describe("OutputsTable", () => {
  it("renders quarterly MQL row with formatted number", () => {
    render(<OutputsTable quarters={[sampleQuarter]} distributionShape="flat" />);
    expect(screen.getByText(/MQLs/i)).toBeTruthy();
    expect(screen.getByText("2,000")).toBeTruthy();
  });
  it("renders infeasible marker for a flagged quarter", () => {
    const infeasible = { ...sampleQuarter, infeasible: true, mqls: 0, created_pipe: 0, marketing_s2_total: 0, s0: 0, s1: 0 };
    render(<OutputsTable quarters={[infeasible]} distributionShape="flat" />);
    expect(screen.getByText(/infeasible/i)).toBeTruthy();
  });
  it("renders nothing-in-scope message when quarters is empty", () => {
    render(<OutputsTable quarters={[]} distributionShape="flat" />);
    expect(screen.getByText(/no quarters/i)).toBeTruthy();
  });
});
