import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { HeroTarget } from "../HeroTarget";

describe("HeroTarget", () => {
  it("renders primary stat, breakdown, and active-quarter context", () => {
    render(
      <HeroTarget
        scopeLabel="Q2–Q4"
        newPipeMustYield={12_700_000}
        planTotal={18_500_000}
        carriedContribution={5_800_000}
        activeQuarter={{
          quarter: "Q1",
          ytd: 529_000,
          inQuarterRemaining: 1_200_000,
        }}
      />,
    );
    expect(screen.getByText(/GAP TO PLAN/)).toBeInTheDocument();
    expect(screen.getByText(/Q2–Q4/)).toBeInTheDocument();
    expect(screen.getByText(/\$12\.7M new pipe must yield/)).toBeInTheDocument();
    expect(screen.getByText(/\$18\.5M plan/)).toBeInTheDocument();
    expect(screen.getByText(/\$5\.8M from S2\+ pipe/)).toBeInTheDocument();
    expect(screen.getByText(/Q1/)).toBeInTheDocument();
    expect(screen.getByText(/\$529K/)).toBeInTheDocument();
    expect(screen.getByText(/\$1\.2M remaining/)).toBeInTheDocument();
  });

  it("omits active quarter block when not provided", () => {
    render(
      <HeroTarget
        scopeLabel="Q4"
        newPipeMustYield={4_500_000}
        planTotal={19_450_000}
        carriedContribution={14_950_000}
      />,
    );
    expect(screen.queryByText(/remaining in-quarter/)).not.toBeInTheDocument();
  });

  it("renders an info button for the rolling-chain tooltip", () => {
    render(
      <HeroTarget
        scopeLabel="Q2–Q4"
        newPipeMustYield={12_700_000}
        planTotal={18_500_000}
        carriedContribution={5_800_000}
      />,
    );
    expect(
      screen.getByRole("button", { name: /what counts as carried pipe/i }),
    ).toBeInTheDocument();
  });
});
