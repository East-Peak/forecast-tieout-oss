import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RateAdjust } from "../RateAdjust";

describe("RateAdjust", () => {
  const baseProps = {
    rates: { mql_to_s0: 0.22, s0_to_s1: 0.7, s1_to_s2: 0.6, win_rate_created: 0.16 },
    onChange: vi.fn(),
    canReset: false,
    onReset: vi.fn(),
  };

  it("renders four labeled inputs showing current rates as percentages", () => {
    render(<RateAdjust {...baseProps} />);
    expect(screen.getByLabelText(/MQL → S0/)).toHaveValue(22);
    expect(screen.getByLabelText(/S0 → S1/)).toHaveValue(70);
    expect(screen.getByLabelText(/S1 → S2/)).toHaveValue(60);
    expect(screen.getByLabelText(/S2 → Won/)).toHaveValue(16);
  });

  it("calls onChange with the edited rate as a decimal (0-1)", () => {
    const onChange = vi.fn();
    render(<RateAdjust {...baseProps} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/S0 → S1/), { target: { value: "75" } });
    expect(onChange).toHaveBeenCalledWith({ s0_to_s1: 0.75 });
  });

  it("clamps values outside 0-100 to the valid range", () => {
    const onChange = vi.fn();
    render(<RateAdjust {...baseProps} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/MQL → S0/), { target: { value: "150" } });
    expect(onChange).toHaveBeenCalledWith({ mql_to_s0: 1 });
    fireEvent.change(screen.getByLabelText(/MQL → S0/), { target: { value: "-5" } });
    expect(onChange).toHaveBeenCalledWith({ mql_to_s0: 0 });
  });

  it("hides the reset button when canReset is false", () => {
    render(<RateAdjust {...baseProps} canReset={false} />);
    expect(screen.queryByText("Reset")).not.toBeInTheDocument();
  });

  it("shows the reset button and calls onReset when canReset is true", () => {
    const onReset = vi.fn();
    render(<RateAdjust {...baseProps} canReset onReset={onReset} />);
    fireEvent.click(screen.getByText("Reset"));
    expect(onReset).toHaveBeenCalled();
  });

  it("lets the user edit S2 → Won as a decimal rate", () => {
    const onChange = vi.fn();
    render(<RateAdjust {...baseProps} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/S2 → Won/), { target: { value: "20" } });
    expect(onChange).toHaveBeenCalledWith({ win_rate_created: 0.2 });
  });
});
