import { formatValue } from "../lib/format";
import type { FormatName } from "../lib/format";

/** How each column's figures read: the actual and the goal and forecast may differ (deal counts are whole). */
const FORMATS: Record<string, FormatName> = {
  opening: "whole",
  created: "whole",
  created_arr: "usd-short",
  win_rate: "percent1",
  cycle: "whole",
  won: "decimal1",
  avg_won_arr: "usd-short",
  bookings: "usd-short",
};

/** A figure of a column as text; a gap is a dash. Actual counts are whole deals, so the actual column of a count is `whole`. */
export function show(column: string, value: string | null, actual = false): string {
  if (value === null) return "—";
  const format: FormatName = actual && column === "won" ? "whole" : FORMATS[column];
  const text = formatValue(format, value);
  return column === "cycle" ? `${text}d` : text;
}
