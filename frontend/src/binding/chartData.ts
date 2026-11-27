import { decimalToNumber } from "../lib/format";
import { resolvePointer } from "./pointer";

/**
 * Chart series are built here from declared paths into a core-produced file, and only here:
 * a series says which pointer (with {period} for the x value) gives each point. Values are
 * parsed from the file's decimal strings once (decimalToNumber); a null stays null, so a gap is
 * drawn as a gap. A range is the pair [low, high] the file holds, never low plus a width.
 */
type SeriesKind = "decimal" | "range" | "span";

type PeriodsFrom =
  | { keysAt: string } // the keys of an object
  | { arrayAt: string } // an array of strings
  | { rowsAt: string; property: string; unless?: readonly [string, string] } // a property of each row of an array of objects, skipping rows where unless[0] equals unless[1]
  | { indexesAt: string; where?: readonly [string, readonly string[]] }; // the position of each row of an array, in the file's own order (never sorted), only rows whose property is one of the values

export interface SeriesSpec {
  key: string;
  label: string;
  kind: SeriesKind;
  /** how the tooltip shows a value: dollars (the default) or a quantity at the report's own places */
  format?: "usd-short" | "quantity";
  /** pointer to each point's value; "{period}" stands for the x value */
  path: string;
  periods: PeriodsFrom;
  /** a "span": pointer to where the bar starts; the point is [start, value], or just the value where the file has no start (null) */
  from?: string;
  /** a path that runs through a null the file holds gives a gap, not an error (a driver whose history failed its gate) */
  nullable?: boolean;
}

type PlotValue = number | [number, number] | null;
export type PlotRow = { period: string } & Record<string, PlotValue | string>;

function periodsOf(doc: unknown, from: PeriodsFrom): string[] {
  if ("keysAt" in from) return Object.keys(resolvePointer(doc, from.keysAt) as Record<string, unknown>);
  if ("arrayAt" in from) return (resolvePointer(doc, from.arrayAt) as unknown[]).map(String);
  if ("indexesAt" in from) {
    const all = resolvePointer(doc, from.indexesAt) as Array<Record<string, unknown>>;
    const [property, values] = from.where ?? [];
    return all.flatMap((row, i) => (property === undefined || values!.includes(String(row[property])) ? [String(i)] : []));
  }
  const rows = resolvePointer(doc, from.rowsAt) as Array<Record<string, unknown>>;
  const [skip, value] = from.unless ?? [];
  return rows.filter((row) => skip === undefined || row[skip] !== value).map((row) => String(row[from.property]));
}

export function pointFor(spec: SeriesSpec, period: string): string {
  return spec.path.replace(/\{period\}/g, period);
}

export function buildChart(doc: unknown, specs: SeriesSpec[]): { periods: string[]; rows: PlotRow[] } {
  const own = specs.map((s) => new Set(periodsOf(doc, s.periods)));
  const ordered = specs.some((spec) => "indexesAt" in spec.periods);
  const union = [...new Set(own.flatMap((set) => [...set]))];
  const periods = ordered ? union.sort((a, b) => Number(a) - Number(b)) : union.sort(); // by position in the file, or by period name
  const rows = periods.map((period) => {
    const row: PlotRow = { period };
    specs.forEach((spec, i) => {
      if (!own[i].has(period)) {
        row[spec.key] = null;
        return;
      }
      const raw = resolvePointer(doc, pointFor(spec, period), { nullBelowNull: spec.nullable === true });
      if (raw === null) row[spec.key] = null;
      else if (spec.kind === "span") {
        const start = resolvePointer(doc, spec.from!.replace(/\{period\}/g, period), { nullBelowNull: spec.nullable === true });
        const end = typeof raw === "number" ? raw : decimalToNumber(raw as string);
        row[spec.key] = start === null ? end : [decimalToNumber(start as string), end];
      } else if (spec.kind === "range") {
        const [low, high] = raw as [string, string];
        row[spec.key] = [decimalToNumber(low), decimalToNumber(high)];
      } else row[spec.key] = typeof raw === "number" ? raw : decimalToNumber(raw as string);
    });
    return row;
  });
  return { periods, rows };
}

/**
 * The span of numbers a set of rows plots, for a scale shared by charts drawn one per row: from the least to
 * the greatest value any series holds, widened to include zero when `zero` is asked for and by `padding` of its
 * own length on each side. A gap contributes nothing.
 */
export function plotExtent(rows: readonly PlotRow[], keys: readonly string[], options: { zero: boolean; padding: number }): [number, number] {
  const values = rows.flatMap((row) => keys.flatMap((key) => [row[key]].flat())).filter((v): v is number => typeof v === "number");
  const least = Math.min(...values, ...(options.zero ? [0] : []));
  const greatest = Math.max(...values, ...(options.zero ? [0] : []));
  const margin = (greatest - least) * options.padding;
  return [least - margin, greatest + margin];
}

/** One report decimal at a pointer, as a number for a chart's reference line. */
export function plotPoint(doc: unknown, pointer: string): number {
  return decimalToNumber(resolvePointer(doc, pointer) as string);
}
