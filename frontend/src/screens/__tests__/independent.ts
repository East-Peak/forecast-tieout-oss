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
  if (Math.round(a) >= 1_000_000 || Math.round(a / 1000) >= 1000) {
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

export function percent1(value: number | string): string {
  const n = Number(value);
  const shown = (Math.abs(n) * 100).toFixed(1);
  return `${n < 0 && Number(shown) !== 0 ? "-" : ""}${shown}%`;
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
