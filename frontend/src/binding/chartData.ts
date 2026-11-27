import { decimalToNumber } from "../lib/format";
import { resolvePointer } from "./pointer";

/**
 * Chart series are built here from declared paths into a core-produced file, and only here:
 * a series says which pointer (with {period} for the x value) gives each point. Values are
 * parsed from the file's decimal strings once (decimalToNumber); a null stays null, so a gap is
 * drawn as a gap. A range is the pair [low, high] the file holds, never low plus a width.
 */
export type SeriesKind = "decimal" | "range";

export type PeriodsFrom =
  | { keysAt: string } // the keys of an object
  | { arrayAt: string } // an array of strings
  | { rowsAt: string; property: string }; // a property of each row of an array of objects

export interface SeriesSpec {
  key: string;
  label: string;
  kind: SeriesKind;
  /** pointer to each point's value; "{period}" stands for the x value */
  path: string;
  periods: PeriodsFrom;
}

export type PlotValue = number | [number, number] | null;
export type PlotRow = { period: string } & Record<string, PlotValue | string>;

function periodsOf(doc: unknown, from: PeriodsFrom): string[] {
  if ("keysAt" in from) return Object.keys(resolvePointer(doc, from.keysAt) as Record<string, unknown>);
  if ("arrayAt" in from) return (resolvePointer(doc, from.arrayAt) as unknown[]).map(String);
  const rows = resolvePointer(doc, from.rowsAt) as Array<Record<string, unknown>>;
  return rows.map((row) => String(row[from.property]));
}

export function pointFor(spec: SeriesSpec, period: string): string {
  return spec.path.replace(/\{period\}/g, period);
}

export function buildChart(doc: unknown, specs: SeriesSpec[]): { periods: string[]; rows: PlotRow[] } {
  const own = specs.map((s) => new Set(periodsOf(doc, s.periods)));
  const periods = [...new Set(own.flatMap((set) => [...set]))].sort();
  const rows = periods.map((period) => {
    const row: PlotRow = { period };
    specs.forEach((spec, i) => {
      if (!own[i].has(period)) {
        row[spec.key] = null;
        return;
      }
      const raw = resolvePointer(doc, pointFor(spec, period));
      if (raw === null) row[spec.key] = null;
      else if (spec.kind === "range") {
        const [low, high] = raw as [string, string];
        row[spec.key] = [decimalToNumber(low), decimalToNumber(high)];
      } else row[spec.key] = decimalToNumber(raw as string);
    });
    return row;
  });
  return { periods, rows };
}
