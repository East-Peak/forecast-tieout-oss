import type { TieoutReport } from "../generated/report";

/**
 * What a draft action starts from, read from the worksheet's win-rate driver as the core wrote it: the pooled baseline rate
 * and the favorable end of the worksheet's historical settings (for a win rate, the high), both as the report's own text.
 * `present` is whether the worksheet has the driver at all (its figures can then be bound); the two readings are null where it
 * has no figure, or offers no settings.
 */
export function winRateReading(report: TieoutReport): { present: boolean; baseline: string | null; favorable: string | null } {
  const sheet = report.worksheet;
  const driver = "drivers" in sheet ? sheet.drivers.find((d) => d.driver === "win_rate") : undefined;
  return { present: driver !== undefined, baseline: driver?.current.value ?? null, favorable: driver?.historical?.high.setting ?? null };
}
