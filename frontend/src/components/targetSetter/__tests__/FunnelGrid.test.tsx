import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FunnelGrid } from "../FunnelGrid";
import type { Scenario } from "../../../types/targetSetter";
import type { RateProvenance } from "../../../types/snapshot";

// Synthetic Acme-scale scenario fixture (no company-specific data)
const acmeScenario: Scenario = {
  id: "observed",
  label: "Observed",
  win_rate_starting: 0.35,
  win_rate_created: 0.18,
  push_rate: 0.1,
  loss_rate: 0.15,
  ae_self_gen_pct: 0.3,
  mql_to_s0: 0.22,
  s0_to_s1: 0.7,
  s1_to_s2: 0.6,
  segment_share: { enterprise: 0.6, smb: 0.4 },
  acv: { enterprise: 80_000, smb: 20_000 },
};

const sampleRate = (value: number): RateProvenance => ({
  value,
  source: "SFDC trailing 90d",
  n: 200,
  methodology: "Weighted trailing 90d",
});

const rateByEdge = {
  mql_to_s0: sampleRate(0.22),
  outbound_to_s0: sampleRate(0.22),
  s0_to_s1: sampleRate(0.7),
  s1_to_s2: sampleRate(0.6),
};

const quarters = [
  {
    quarter: "Q2FY26",
    mqls: 500,
    s0: 110,
    outbound_s0: 50,
    total_s0: 160,
    total_s1: 112,
    total_s2: 67,
    marketing_s2_total: 67,
    created_pipe: 3_200_000,
    won_from_created: 576_000,
    won_from_starting: 280_000,
    bookings_target: 800_000,
    infeasible: false,
  } as never,
];

describe("FunnelGrid rate provenance", () => {
  it("renders rate rows for each funnel transition", () => {
    render(
      <FunnelGrid
        quarters={quarters}
        scenario={acmeScenario}
        rateByEdge={rateByEdge}
      />,
    );
    // All three rate labels should appear (as the label text next to the popover trigger)
    expect(screen.getAllByText("MQL → S0").length).toBeGreaterThan(0);
    expect(screen.getAllByText("S0 → S1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("S1 → S2").length).toBeGreaterThan(0);
  });

  it("renders clickable rate percentages", () => {
    render(
      <FunnelGrid
        quarters={quarters}
        scenario={acmeScenario}
        rateByEdge={rateByEdge}
      />,
    );
    // 22.0% appears for mql_to_s0
    const rateButtons = screen.getAllByText(/22\.0%/);
    expect(rateButtons.length).toBeGreaterThan(0);
    // 70.0% for s0_to_s1
    expect(screen.getAllByText(/70\.0%/).length).toBeGreaterThan(0);
    // 60.0% for s1_to_s2
    expect(screen.getAllByText(/60\.0%/).length).toBeGreaterThan(0);
  });

  it("opens provenance popover when a rate cell is clicked", () => {
    render(
      <FunnelGrid
        quarters={quarters}
        scenario={acmeScenario}
        rateByEdge={rateByEdge}
      />,
    );
    // Click the first rate cell showing "22.0%"
    const rateButtons = screen.getAllByText(/22\.0%/);
    expect(rateButtons.length).toBeGreaterThan(0);
    fireEvent.click(rateButtons[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText(/trailing 90d/i).length).toBeGreaterThan(0);
  });

  it("opens popover for S0→S1 rate", () => {
    render(
      <FunnelGrid
        quarters={quarters}
        scenario={acmeScenario}
        rateByEdge={rateByEdge}
      />,
    );
    const s0ToS1Button = screen.getAllByText(/70\.0%/)[0];
    fireEvent.click(s0ToS1Button);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The popover should show the label
    expect(screen.getAllByText(/S0 → S1/i).length).toBeGreaterThan(0);
  });

  it("opens popover for S1→S2 rate", () => {
    render(
      <FunnelGrid
        quarters={quarters}
        scenario={acmeScenario}
        rateByEdge={rateByEdge}
      />,
    );
    const s1ToS2Button = screen.getAllByText(/60\.0%/)[0];
    fireEvent.click(s1ToS2Button);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText(/S1 → S2/i).length).toBeGreaterThan(0);
  });

  it("does not render an internal-flavor suffix in the scenario subtitle", () => {
    const altScenario = { ...acmeScenario, id: "marketing-led", label: "Marketing-led" };
    render(
      <FunnelGrid
        quarters={quarters}
        scenario={altScenario}
        rateByEdge={rateByEdge}
      />,
    );
    // The subtitle should show only the scenario label — no appended suffix
    expect(screen.queryByText(/funnel on current waterfall/i)).not.toBeInTheDocument();
    expect(screen.getByText("Marketing-led")).toBeInTheDocument();
  });
});
