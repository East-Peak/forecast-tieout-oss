import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FunnelSankey } from "../FunnelSankey";
import type { RateProvenance } from "../../../types/snapshot";

const sampleRate = (value: number, source = "SFDC trailing 90d"): RateProvenance => ({
  value,
  source,
  n: 200,
  methodology: "Weighted trailing 90d",
});

const rateByEdge = {
  mql_to_s0: sampleRate(0.22),
  outbound_to_s0: sampleRate(0.22, "SFDC trailing 90d (same-rate proxy)"),
  s0_to_s1: sampleRate(0.7),
  s1_to_s2: sampleRate(0.6),
};

// Synthetic Acme-scale quarter fixture (FY26, no company-specific data)
const quarters = [
  {
    quarter: "Q2FY26",
    mqls: 500,
    s0: 110,
    outbound_s0: 50,
    total_s0: 160,
    total_s1: 112,
    total_s2: 67,
  } as never,
];

describe("FunnelSankey", () => {
  it("renders the time-period header", () => {
    render(<FunnelSankey quarters={quarters} rateByEdge={rateByEdge} />);
    expect(screen.getByText(/Q2FY26/)).toBeInTheDocument();
  });

  it("renders the edge-rates chip strip below the Sankey with only real conversion rates", () => {
    render(<FunnelSankey quarters={quarters} rateByEdge={rateByEdge} />);
    expect(screen.getByText("MQL → S0")).toBeInTheDocument();
    expect(screen.getByText("S0 → S1")).toBeInTheDocument();
    expect(screen.getByText("S1 → S2")).toBeInTheDocument();
    // Outbound entering S0 is a direct input, not a conversion — no chip.
    expect(screen.queryByText("Outbound → S0")).not.toBeInTheDocument();
    // Percentages
    expect(screen.getByText("22.0%")).toBeInTheDocument();
    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(screen.getByText("60.0%")).toBeInTheDocument();
  });

  it("opens a provenance popover when a chip percentage is clicked", () => {
    render(<FunnelSankey quarters={quarters} rateByEdge={rateByEdge} />);
    const s1tos2Percent = screen.getByText("60.0%");
    fireEvent.click(s1tos2Percent);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText(/trailing 90d/i).length).toBeGreaterThan(0);
  });
});
