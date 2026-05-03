import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RateProvenancePopover } from "../RateProvenancePopover";
import type { RateProvenance } from "../../../types/snapshot";

describe("RateProvenancePopover", () => {
  const sample: RateProvenance = {
    value: 0.221,
    source: "SFDC OpportunityHistory",
    n: 929,
    methodology: "Weighted trailing 90d, excluding stage S0 loopbacks",
    lookback_days: 90,
    calibrated_at: "2026-04-18",
    date_range: { start: "2026-01-18", end: "2026-04-18" },
  };

  it("renders the value as a trigger", () => {
    render(
      <RateProvenancePopover label="MQL → S0" rate={sample}>
        <span>22.1%</span>
      </RateProvenancePopover>,
    );
    expect(screen.getByText("22.1%")).toBeInTheDocument();
  });

  it("opens the popover on click and shows all provenance fields", () => {
    render(
      <RateProvenancePopover label="MQL → S0" rate={sample}>
        <span>22.1%</span>
      </RateProvenancePopover>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/SFDC OpportunityHistory/)).toBeInTheDocument();
    expect(screen.getByText(/n = 929/)).toBeInTheDocument();
    expect(screen.getByText(/90d lookback/)).toBeInTheDocument();
    expect(screen.getByText(/calibrated 2026-04-18/)).toBeInTheDocument();
    expect(screen.getByText(/Weighted trailing 90d/)).toBeInTheDocument();
  });

  it("renders 'n = —' when sample size is null", () => {
    const rate = { ...sample, n: null };
    render(
      <RateProvenancePopover label="MQL → S0" rate={rate}>
        <span>22.1%</span>
      </RateProvenancePopover>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/n = —/)).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    render(
      <RateProvenancePopover label="MQL → S0" rate={sample}>
        <span>22.1%</span>
      </RateProvenancePopover>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
