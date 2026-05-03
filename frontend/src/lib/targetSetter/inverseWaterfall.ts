import type { WaterfallRates } from "../../types/snapshot";

export interface InverseQuarterInput {
  starting_pipe: number;
  bookings_target: number;
  rates: WaterfallRates;
}

export interface InverseQuarterResult {
  created_pipe: number;
  won_from_starting: number;
  won_from_created: number;
  infeasible: boolean;
}

export function inverseQuarter({
  starting_pipe,
  bookings_target,
  rates,
}: InverseQuarterInput): InverseQuarterResult {
  const won_from_starting = starting_pipe * rates.win_rate_starting;
  const won_from_created_needed = bookings_target - won_from_starting;

  if (won_from_created_needed <= 0 || rates.win_rate_created <= 0) {
    return {
      created_pipe: 0,
      won_from_starting,
      won_from_created: 0,
      infeasible: true,
    };
  }

  const created_pipe = won_from_created_needed / rates.win_rate_created;
  return {
    created_pipe,
    won_from_starting,
    won_from_created: won_from_created_needed,
    infeasible: false,
  };
}

export interface RollForwardInput {
  starting_pipe: number;
  created_pipe: number;
  rates: WaterfallRates;
}

export function rollForwardPipe({ starting_pipe, created_pipe, rates }: RollForwardInput): number {
  const pushed = starting_pipe * rates.push_rate;
  const remaining_coeff = 1 - rates.win_rate_created - rates.loss_rate * 0.5;
  const remaining = remaining_coeff > 0 ? created_pipe * remaining_coeff : 0;
  return pushed + remaining;
}
