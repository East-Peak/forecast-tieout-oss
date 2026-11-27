/**
 * How report values are shown. A value in a core-produced file is a decimal string
 * (or a count, a date, a sentence); this file turns it into text and, for charts,
 * into a plottable number. It is the only place a report decimal is parsed
 * (`decimalToNumber` is the chart adapter's single entry); nothing else in the
 * browser does arithmetic on report values.
 *
 * The named formats (design call 5):
 *   usd-full   whole dollars, grouped, half away from zero:  $6,119,925
 *   usd-short  one fixed rule: millions to one decimal, thousands to whole,
 *              else whole dollars, rounded into the next unit when it rounds up:  $58.1M  $612K  $12
 *   percent1   a fraction as a percent to one decimal:  83.3%
 *   count      a whole number, grouped
 *   date       ISO date as  Aug 31, 2026
 *   month      ISO month as  Sep 2026
 *   text       verbatim
 */
export type FormatName = "usd-full" | "usd-short" | "percent1" | "count" | "date" | "month" | "text";

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A report decimal string as a number to plot. The one parse of report decimals outside the formatters. */
export function decimalToNumber(raw: string): number {
  if (typeof raw !== "string" || !DECIMAL.test(raw)) {
    throw new Error(`not a decimal string: ${JSON.stringify(raw)}`);
  }
  return Number(raw);
}

interface Scaled {
  negative: boolean;
  /** the value times 10^scale, exact */
  units: bigint;
  scale: number;
}

function parseDecimal(raw: unknown): Scaled {
  if (raw === null || raw === undefined) throw new Error(`no value to show (${String(raw)})`);
  let text: string;
  if (typeof raw === "number") {
    if (!Number.isFinite(raw)) throw new Error(`not a finite number: ${raw}`);
    text = raw.toFixed(12);
  } else if (typeof raw === "string") {
    text = raw;
  } else {
    throw new Error(`not a decimal: ${JSON.stringify(raw)}`);
  }
  const match = DECIMAL.exec(text);
  if (!match) throw new Error(`not a decimal string: ${JSON.stringify(raw)}`);
  const fraction = match[3] ?? "";
  return { negative: match[1] === "-", units: BigInt(match[2] + fraction), scale: fraction.length };
}

/** |value| divided by 10^power (power may be negative), rounded half up, as an integer. */
function roundedAbs(d: Scaled, power: number): bigint {
  const shift = d.scale + power;
  if (shift <= 0) return d.units * 10n ** BigInt(-shift);
  const divisor = 10n ** BigInt(shift);
  const quotient = d.units / divisor;
  return (d.units % divisor) * 2n >= divisor ? quotient + 1n : quotient;
}

function group(n: bigint): string {
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function signed(negative: boolean, magnitude: bigint, body: string): string {
  return negative && magnitude !== 0n ? `-${body}` : body;
}

function usdFull(raw: unknown): string {
  const d = parseDecimal(raw);
  const dollars = roundedAbs(d, 0);
  return signed(d.negative, dollars, `$${group(dollars)}`);
}

function usdShort(raw: unknown): string {
  const d = parseDecimal(raw);
  const dollars = roundedAbs(d, 0);
  const thousands = roundedAbs(d, 3);
  if (dollars >= 1_000_000n || thousands >= 1000n) {
    const tenths = roundedAbs(d, 5);
    return signed(d.negative, tenths, `$${tenths / 10n}.${tenths % 10n}M`);
  }
  if (dollars >= 1000n) return signed(d.negative, thousands, `$${thousands}K`);
  return signed(d.negative, dollars, `$${dollars}`);
}

function percent1(raw: unknown): string {
  const d = parseDecimal(raw);
  const tenths = roundedAbs(d, -3);
  return signed(d.negative, tenths, `${tenths / 10n}.${tenths % 10n}%`);
}

function count(raw: unknown): string {
  if (typeof raw !== "number" || !Number.isInteger(raw)) {
    throw new Error(`not an integer count: ${JSON.stringify(raw)}`);
  }
  const magnitude = BigInt(Math.abs(raw));
  return signed(raw < 0, magnitude, group(magnitude));
}

function parseDate(raw: unknown): [string, string, string] {
  const match = typeof raw === "string" ? /^(\d{4})-(0[1-9]|1[0-2])-(\d{2})$/.exec(raw) : null;
  if (!match) throw new Error(`not an ISO date: ${JSON.stringify(raw)}`);
  return [match[1], match[2], match[3]];
}

function parseMonth(raw: unknown): [string, string] {
  const match = typeof raw === "string" ? /^(\d{4})-(0[1-9]|1[0-2])$/.exec(raw) : null;
  if (!match) throw new Error(`not an ISO month: ${JSON.stringify(raw)}`);
  return [match[1], match[2]];
}

/** Which side of zero a report decimal is on, after the rounding a reader sees is not applied: -1, 0 or 1. */
export function signOf(raw: unknown): -1 | 0 | 1 {
  const d = parseDecimal(raw);
  if (d.units === 0n) return 0;
  return d.negative ? -1 : 1;
}

/** Axis ticks and period labels drawn by a chart: "Sep '26". */
export function formatMonthTick(month: string): string {
  const [year, m] = parseMonth(month);
  return `${MONTHS[Number(m) - 1]} '${year.slice(2)}`;
}

export function formatValue(format: FormatName, raw: unknown): string {
  switch (format) {
    case "usd-full":
      return usdFull(raw);
    case "usd-short":
      return usdShort(raw);
    case "percent1":
      return percent1(raw);
    case "count":
      return count(raw);
    case "date": {
      const [year, m, day] = parseDate(raw);
      return `${MONTHS[Number(m) - 1]} ${Number(day)}, ${year}`;
    }
    case "month": {
      const [year, m] = parseMonth(raw);
      return `${MONTHS[Number(m) - 1]} ${year}`;
    }
    case "text":
      if (typeof raw !== "string") throw new Error(`not text: ${JSON.stringify(raw)}`);
      return raw;
  }
}

// The three below belong to the old pages and go with them (pure-deletion commit).
export function formatMoney(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function formatMonthLabel(m: string): string {
  // Handle both "2026-02" and "2026-02-01" formats
  const normalized = m.length <= 7 ? m + "-01" : m;
  const d = new Date(normalized + "T00:00:00");
  const month = d.toLocaleDateString("en-US", { month: "short" });
  const year = d.toLocaleDateString("en-US", { year: "2-digit" });
  return `${month} '${year}`;
}

export function formatIsoDate(dateIso: string): string {
  return new Date(`${dateIso}T00:00:00`).toLocaleDateString("en-US");
}
