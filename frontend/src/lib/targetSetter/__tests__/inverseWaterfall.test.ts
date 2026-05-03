import { describe, it, expect } from "vitest";
import { inverseQuarter, rollForwardPipe } from "../inverseWaterfall";

const DEFAULT_RATES = {
  win_rate_starting: 0.059,
  win_rate_created: 0.16,
  push_rate: 0.90,
  loss_rate: 0.10,
};

describe("inverseQuarter", () => {
  it("computes created_pipe from bookings_target and starting_pipe", () => {
    const result = inverseQuarter({
      starting_pipe: 10_000_000,
      bookings_target: 1_000_000,
      rates: DEFAULT_RATES,
    });
    const starting_won = 10_000_000 * 0.059;
    const won_from_created = 1_000_000 - starting_won;
    const expected_created = won_from_created / 0.16;
    expect(result.created_pipe).toBeCloseTo(expected_created, 0);
    expect(result.infeasible).toBe(false);
  });

  it("flags infeasible when starting_pipe × win_rate >= bookings_target", () => {
    const result = inverseQuarter({
      starting_pipe: 20_000_000,
      bookings_target: 1_000_000,
      rates: DEFAULT_RATES,
    });
    expect(result.infeasible).toBe(true);
    expect(result.created_pipe).toBe(0);
  });

  it("clamps created_pipe to 0 when win_rate_created is 0", () => {
    const result = inverseQuarter({
      starting_pipe: 10_000_000,
      bookings_target: 1_000_000,
      rates: { ...DEFAULT_RATES, win_rate_created: 0 },
    });
    expect(result.created_pipe).toBe(0);
    expect(result.infeasible).toBe(true);
  });
});

describe("rollForwardPipe", () => {
  it("computes ending_pipe = pushed + remaining", () => {
    const ending = rollForwardPipe({
      starting_pipe: 10_000_000,
      created_pipe: 5_000_000,
      rates: DEFAULT_RATES,
    });
    const pushed = 10_000_000 * 0.90;
    const remaining = 5_000_000 * (1 - 0.16 - 0.10 * 0.5);
    expect(ending).toBeCloseTo(pushed + remaining, 0);
  });

  it("clamps remaining to 0 when created outflow exceeds inflow", () => {
    const ending = rollForwardPipe({
      starting_pipe: 10_000_000,
      created_pipe: 5_000_000,
      rates: { ...DEFAULT_RATES, win_rate_created: 0.7, loss_rate: 0.8 },
    });
    expect(ending).toBeCloseTo(10_000_000 * 0.90, 0);
  });
});
