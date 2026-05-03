import type { QuarterKey } from "../../types/targetSetter";
import type { Snapshot } from "../../types/snapshot";
import { monthsForQuarter } from "../../engine/scenario";

const S2_PLUS_STAGES = new Set(["S2", "S3", "S4", "S5"]);

export function computeStartingPipe(inventory: { stage: string; total_value: number }[]): number {
  return inventory
    .filter((row) => S2_PLUS_STAGES.has(row.stage))
    .reduce((sum, row) => sum + row.total_value, 0);
}

export interface YtdBookingsInput {
  bookings: { month: string; total: number }[];
  activeQuarter: QuarterKey;
  asOf: string;
}

/**
 * Sum actuals bookings for completed months of `activeQuarter` up to `asOf`.
 * Uses the snapshot's fiscal calendar to determine which months belong to
 * the active quarter — no hardcoded QUARTER_MONTHS map.
 */
export function computeYtdBookings(
  snapshot: Snapshot,
  { bookings, activeQuarter, asOf }: YtdBookingsInput,
): number {
  const activeMonths = new Set(
    monthsForQuarter(snapshot, activeQuarter).map((m) => m.slice(0, 7)),
  );
  const asOfDate = new Date(asOf);
  return bookings
    .filter((row) => {
      const monthPrefix = row.month.substring(0, 7); // "YYYY-MM"
      if (!activeMonths.has(monthPrefix)) return false;
      const bookingStart = new Date(`${monthPrefix}-01`);
      return bookingStart <= asOfDate;
    })
    .reduce((sum, row) => sum + row.total, 0);
}
