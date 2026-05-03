/**
 * distribute.ts — Monthly and weekly cadence distribution helpers.
 *
 * Splits a quarterly total into 3 monthly (or 13 weekly) buckets using a
 * named shape profile.  Largest-remainder rounding guarantees the integer
 * outputs sum exactly to the input.
 */

export type MonthlyShape = string; // "flat" | "back_loaded" — open string for future shapes

const SHAPE_WEIGHTS: Record<string, [number, number, number]> = {
  flat: [1 / 3, 1 / 3, 1 / 3],
  back_loaded: [0.25, 0.35, 0.40],
};

export interface DistributeMonthlyInput {
  quarterly: number;
  shape: MonthlyShape;
  integer?: boolean;
}

export function distributeMonthly({ quarterly, shape, integer = true }: DistributeMonthlyInput): number[] {
  const weights = SHAPE_WEIGHTS[shape] ?? SHAPE_WEIGHTS["flat"];
  if (!integer) {
    return weights.map((w) => quarterly * w);
  }
  return largestRemainderRound(weights.map((w) => quarterly * w), quarterly);
}

export function distributeWeekly({ quarterly, integer = true }: { quarterly: number; integer?: boolean }): number[] {
  const weights = Array(13).fill(1 / 13);
  if (!integer) {
    return weights.map((w) => quarterly * w);
  }
  return largestRemainderRound(
    weights.map((w) => quarterly * w),
    quarterly,
  );
}

// Largest-remainder rounding: floor each, distribute remainder to highest fractional parts.
// Guarantees sum(result) === target for integer targets.
function largestRemainderRound(values: number[], target: number): number[] {
  const floors = values.map(Math.floor);
  const sumFloors = floors.reduce((a, b) => a + b, 0);
  const remainder = Math.round(target - sumFloors);
  if (remainder === 0) return floors;

  const fracs = values
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac);
  const result = [...floors];
  for (let k = 0; k < Math.abs(remainder); k++) {
    result[fracs[k % fracs.length].i] += remainder > 0 ? 1 : -1;
  }
  return result;
}
