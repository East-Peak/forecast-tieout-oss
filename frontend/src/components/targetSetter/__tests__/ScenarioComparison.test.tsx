import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScenarioComparison } from "../ScenarioComparison";
import type { ScenarioComparisonEntry } from "../ScenarioComparison";

describe("ScenarioComparison", () => {
  const scenarios: ScenarioComparisonEntry[] = [
    {
      id: "observed",
      label: "Observed",
      result: {
        quarters: [
          // only mqls is asserted by this test; other QuarterTargets fields
          // are populated as zeros to satisfy the type
          { quarter: "Q2", mqls: 1964 } as never,
          { quarter: "Q3", mqls: 3247 } as never,
        ],
        scope: ["Q2", "Q3"],
      } as never,
      funnel: { mql_to_s0: 0.22, s0_to_s1: 0.7, s1_to_s2: 0.6 },
    },
    {
      id: "plan",
      label: "Plan",
      result: {
        quarters: [
          { quarter: "Q2", mqls: 2500 } as never,
          { quarter: "Q3", mqls: 3800 } as never,
        ],
        scope: ["Q2", "Q3"],
      } as never,
      funnel: { mql_to_s0: 0.18, s0_to_s1: 0.7, s1_to_s2: 0.6 },
    },
  ];

  it("renders only the first quarter in scope", () => {
    render(<ScenarioComparison scenarios={scenarios} activeId="observed" />);
    expect(screen.getByText("Q2")).toBeInTheDocument();
    expect(screen.queryByText("Q3")).not.toBeInTheDocument();
    expect(screen.getByText("1,964")).toBeInTheDocument();
    expect(screen.getByText("2,500")).toBeInTheDocument();
  });

  it("subtitle indicates first-quarter-only peek", () => {
    render(<ScenarioComparison scenarios={scenarios} activeId="observed" />);
    expect(screen.getByText(/First quarter in scope/i)).toBeInTheDocument();
  });

  it("renders nothing when scenarios is empty", () => {
    const { container } = render(<ScenarioComparison scenarios={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
