import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScenarioSelector } from "../ScenarioSelector";
import type { ScenarioSelectorProps } from "../ScenarioSelector";

const baseProps: ScenarioSelectorProps = {
  activeId: "observed",
  onSelect: vi.fn(),
  scenarios: [
    {
      id: "observed",
      label: "Observed",
      primaryLine: "SFDC · trailing 90d · n=929",
      secondaryLine: "refreshed recently",
    },
    {
      id: "plan",
      label: "Plan",
      primaryLine: "Annual plan rates",
      secondaryLine: "plan year",
    },
    {
      id: "custom",
      label: "Custom",
      primaryLine: "User-edited rates",
      secondaryLine: "manual override",
    },
  ],
};

describe("ScenarioSelector", () => {
  it("renders all three pills with provenance", () => {
    render(<ScenarioSelector {...baseProps} />);
    expect(screen.getByText("Observed")).toBeInTheDocument();
    expect(screen.getByText("SFDC · trailing 90d · n=929")).toBeInTheDocument();
    expect(screen.getByText("refreshed recently")).toBeInTheDocument();
    expect(screen.getByText("Plan")).toBeInTheDocument();
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("highlights the active pill", () => {
    render(<ScenarioSelector {...baseProps} activeId="plan" />);
    const planButton = screen.getByRole("button", { name: /Plan/ });
    expect(planButton.className).toMatch(/bg-blue-600/);
  });

  it("calls onSelect when a different pill is clicked", () => {
    const onSelect = vi.fn();
    render(<ScenarioSelector {...baseProps} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Custom/ }));
    expect(onSelect).toHaveBeenCalledWith("custom");
  });
});
