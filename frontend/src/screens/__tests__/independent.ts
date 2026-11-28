/**
 * Test-only. How the tests expect values to read, written separately from src/lib/format.ts:
 * these use Number and Intl where the formatter uses exact decimal arithmetic, so a mistake in
 * one is not repeated in the other. (Same declared rules: half away from zero at the shown place.)
 */
const usdWhole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function usdFull(raw: string): string {
  const shown = usdWhole.format(Number(raw));
  return shown === "-$0" ? "$0" : shown;
}

export function usdShort(raw: string): string {
  const n = Number(raw);
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  let body: string;
  let zero = false;
  if (Math.round(a / 100_000) >= 10_000) {
    body = `$${(Math.round(a / 100_000_000) / 10).toFixed(1)}B`;
  } else if (Math.round(a) >= 1_000_000 || Math.round(a / 1000) >= 1000) {
    const tenths = Math.round(a / 100_000);
    body = `$${(tenths / 10).toFixed(1)}M`;
    zero = tenths === 0;
  } else if (Math.round(a) >= 1000) {
    body = `$${Math.round(a / 1000)}K`;
  } else {
    body = `$${Math.round(a)}`;
    zero = Math.round(a) === 0;
  }
  return zero ? body : sign + body;
}

const percentHalfUp = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  roundingMode: "halfExpand",
  useGrouping: false,
} as Intl.NumberFormatOptions);

export function percent1(value: number | string): string {
  const shown = percentHalfUp.format(Math.abs(Number(value)));
  return Number(value) < 0 && Number.parseFloat(shown) !== 0 ? `-${shown}` : shown;
}

export function count(n: number): string {
  return n.toLocaleString("en-US");
}

export function date(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function month(iso: string): string {
  return new Date(`${iso}-01T00:00:00Z`).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

/** A count, or a decimal string at the report's own places, grouped (written with toLocaleString, not the formatter's BigInt). */
export function quantity(raw: string | number): string {
  if (typeof raw === "number") return raw.toLocaleString("en-US");
  const negative = raw.startsWith("-");
  const [whole, fraction] = (negative ? raw.slice(1) : raw).split(".");
  const shown = `${Number(whole).toLocaleString("en-US")}${fraction === undefined ? "" : `.${fraction}`}`;
  return negative && /[1-9]/.test(raw) ? `-${shown}` : shown;
}

export const multiple = (raw: string): string => `${quantity(raw)}x`;
export const cents = (raw: string): string => `${quantity(raw)}¢`;

const twoPlaces = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2, roundingMode: "halfExpand" } as Intl.NumberFormatOptions);
export function decimal2(raw: string): string {
  const shown = twoPlaces.format(Math.abs(Number(raw)));
  return Number(raw) < 0 && Number(shown.split(",").join("")) !== 0 ? `-${shown}` : shown;
}

const wholeHalfUp = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0, roundingMode: "halfExpand", useGrouping: true } as Intl.NumberFormatOptions);
const oneHalfUp = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1, roundingMode: "halfExpand" } as Intl.NumberFormatOptions);

/** A decimal string as a grouped whole number, half away from zero (a rounded zero has no sign). */
export function whole(raw: string): string {
  const shown = wholeHalfUp.format(Math.abs(Number(raw)));
  return Number(raw) < 0 && shown !== "0" ? `-${shown}` : shown;
}

/** A decimal string to one place, half away from zero. */
export function decimal1(raw: string): string {
  const shown = oneHalfUp.format(Math.abs(Number(raw)));
  return Number(raw) < 0 && Number(shown.split(",").join("")) !== 0 ? `-${shown}` : shown;
}

export const days = (raw: string): string => `${whole(raw)}d`;
