import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoleSummaryStrip } from "../RoleSummaryStrip";

describe("RoleSummaryStrip", () => {
  const baseCards = [
    {
      role: "Marketing",
      metricLabel: "MQLs needed",
      totalValue: 6646,
      integer: true,
      perQuarter: [
        { quarter: "Q2", value: 1964 },
        { quarter: "Q3", value: 3247 },
        { quarter: "Q4", value: 5885 },
      ],
      qoqDelta: 1.4,
    },
    {
      role: "Outbound",
      metricLabel: "Outbound S0 needed",
      totalValue: 1200,
      integer: true,
      perQuarter: [
        { quarter: "Q2", value: 356 },
        { quarter: "Q3", value: 586 },
        { quarter: "Q4", value: 1075 },
      ],
      qoqDelta: null,
    },
    {
      role: "Sales",
      metricLabel: "S2 SQOs needed",
      totalValue: 279,
      integer: true,
      perQuarter: [
        { quarter: "Q2", value: 84 },
        { quarter: "Q3", value: 114 },
        { quarter: "Q4", value: 181 },
      ],
      qoqDelta: null,
    },
  ];

  it("renders all three cards with targets and per-quarter breakdowns", () => {
    render(<RoleSummaryStrip scopeLabel="Q2–Q4" cards={baseCards} />);
    expect(screen.getByText(/MARKETING/)).toBeInTheDocument();
    expect(screen.getByText("6,646")).toBeInTheDocument();
    expect(screen.getByText(/OUTBOUND/)).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(screen.getByText(/SALES/)).toBeInTheDocument();
    expect(screen.getByText("279")).toBeInTheDocument();
  });

  it("shows QoQ delta when provided and 'baseline not available' otherwise", () => {
    render(<RoleSummaryStrip scopeLabel="Q2–Q4" cards={baseCards} />);
    expect(screen.getByText(/\+140% vs Q1 actuals/)).toBeInTheDocument();
    expect(screen.getAllByText(/baseline not available/i)).toHaveLength(2);
  });

  it("renders per-quarter breakdown as slash-separated integers", () => {
    render(<RoleSummaryStrip scopeLabel="Q2–Q4" cards={baseCards} />);
    expect(screen.getByText(/1,964\s*\/\s*3,247\s*\/\s*5,885/)).toBeInTheDocument();
  });
});
