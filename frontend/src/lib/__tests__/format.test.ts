import { describe, expect, it } from "vitest";
import { decimalToNumber, formatMonthTick, formatValue } from "../format";

describe("usd-full: whole dollars, grouped, half away from zero", () => {
  const cases: Array<[string, string]> = [
    ["6119924.84", "$6,119,925"],
    ["0.00", "$0"],
    ["1234.50", "$1,235"],
    ["1234.49", "$1,234"],
    ["-1880075.16", "-$1,880,075"],
    ["-0.40", "$0"], // a rounded zero has no sign
    ["8000000", "$8,000,000"],
    ["999.99", "$1,000"],
    ["84000000.00", "$84,000,000"],
  ];
  it.each(cases)("%s -> %s", (raw, shown) => {
    expect(formatValue("usd-full", raw)).toBe(shown);
  });
});

describe("usd-short: one rule, millions to one decimal, thousands to whole, else dollars", () => {
  const cases: Array<[string, string]> = [
    ["58089724.29", "$58.1M"],
    ["1000000", "$1.0M"],
    ["999500.40", "$1.0M"], // rounds into the next unit, never "$1000K"
    ["999499.99", "$999K"],
    ["612345.00", "$612K"],
    ["1500.00", "$2K"],
    ["999.50", "$1K"],
    ["999.40", "$999"],
    ["12.00", "$12"],
    ["-1910275.71", "-$1.9M"],
    ["-400.00", "-$400"],
    ["-0.30", "$0"],
    ["0.00", "$0"],
    ["84000000", "$84.0M"],
  ];
  it.each(cases)("%s -> %s", (raw, shown) => {
    expect(formatValue("usd-short", raw)).toBe(shown);
  });
});

describe("percent1: a fraction as a percent to one decimal", () => {
  const cases: Array<[string | number, string]> = [
    [0.8333, "83.3%"],
    ["0.8214", "82.1%"],
    [1, "100.0%"],
    [0, "0.0%"],
    ["0.05", "5.0%"],
    ["-0.0149", "-1.5%"],
    [0.0004, "0.0%"],
  ];
  it.each(cases)("%s -> %s", (raw, shown) => {
    expect(formatValue("percent1", raw)).toBe(shown);
  });
});

describe("count, date, month and text", () => {
  it("groups counts", () => {
    expect(formatValue("count", 7)).toBe("7");
    expect(formatValue("count", 12345)).toBe("12,345");
    expect(formatValue("count", 0)).toBe("0");
  });
  it("writes dates and months from the ISO text, with no time zone in the way", () => {
    expect(formatValue("date", "2026-08-31")).toBe("Aug 31, 2026");
    expect(formatValue("date", "2027-01-01")).toBe("Jan 1, 2027");
    expect(formatValue("month", "2026-09")).toBe("Sep 2026");
  });
  it("shows text verbatim", () => {
    expect(formatValue("text", "too narrow: judged by the 3-month back-test cell")).toBe(
      "too narrow: judged by the 3-month back-test cell",
    );
  });
  it("short month ticks for chart axes", () => {
    expect(formatMonthTick("2026-09")).toBe("Sep '26");
    expect(formatMonthTick("2027-01")).toBe("Jan '27");
  });
});

describe("refuses what it cannot show truthfully", () => {
  it("rejects a malformed decimal rather than showing NaN", () => {
    expect(() => formatValue("usd-full", "12,3")).toThrow(/decimal/);
    expect(() => formatValue("usd-full", "")).toThrow();
    expect(() => formatValue("usd-short", null)).toThrow(/null/);
    expect(() => formatValue("usd-short", undefined)).toThrow();
    expect(() => formatValue("count", 1.5)).toThrow(/integer/);
    expect(() => formatValue("date", "08/31/2026")).toThrow();
    expect(() => formatValue("percent1", Number.NaN)).toThrow();
  });
});

describe("decimalToNumber: the one place a report decimal becomes a plottable number", () => {
  it("parses decimal strings", () => {
    expect(decimalToNumber("6119924.84")).toBe(6119924.84);
    expect(decimalToNumber("-12.50")).toBe(-12.5);
    expect(decimalToNumber("8000000")).toBe(8000000);
  });
  it("refuses anything that is not a decimal string", () => {
    expect(() => decimalToNumber("1e7")).toThrow();
    expect(() => decimalToNumber(5 as unknown as string)).toThrow();
  });
});
