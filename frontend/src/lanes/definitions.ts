import type { ColumnKey } from "./types";

/** What the two numbers a rate, a duration or a size is made of are, column by column. */
export const PARTS: Partial<Record<ColumnKey, { top: string; bottom: string }>> = {
  win_rate: { top: "won", bottom: "deals in the cohort" },
  cycle: { top: "days from creation to close", bottom: "wins" },
  avg_won_arr: { top: "bookings", bottom: "wins" },
};
