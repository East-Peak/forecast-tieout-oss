import type { TieoutReport } from "../generated/report";
import type { ActionDriver } from "./protocol";

/**
 * What a draft action starts from, read from the worksheet's row for its driver as the core wrote it: the pooled baseline and
 * the favorable end of the worksheet's historical settings (the high, for the win rate, the size and creation; the low for the cycle, where shorter is better),
 * both as the report's own text. `present` is whether the worksheet has the driver at all (its figures can then be bound); the
 * two readings are null where it has no figure, or offers no settings.
 */
export function driverReading(report: TieoutReport, driver: ActionDriver): { present: boolean; baseline: string | null; favorable: string | null } {
  const sheet = report.worksheet;
  const row = "drivers" in sheet ? sheet.drivers.find((d) => d.driver === driver) : undefined;
  return { present: row !== undefined, baseline: row?.current.value ?? null, favorable: (driver === "cycle_days" ? row?.historical?.low.setting : row?.historical?.high.setting) ?? null };
}

/** The win rate's reading (a probability, as text). */
export const winRateReading = (report: TieoutReport) => driverReading(report, "win_rate");
