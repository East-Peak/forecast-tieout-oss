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
    // a billion or more: one decimal and B
    ["1000000000", "$1.0B"],
    ["2018192885.26", "$2.0B"],
    ["6609519382.53", "$6.6B"],
    ["3007281482.38", "$3.0B"],
    ["999949999.99", "$999.9M"],
    ["999950000.00", "$1.0B"], // would round to $1000.0M: it is $1.0B
    ["999999999.99", "$1.0B"],
    ["-2018192885.26", "-$2.0B"],
    ["-999950000", "-$1.0B"],
    ["-999949999", "-$999.9M"],
    ["12345678901.00", "$12.3B"],
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

describe("quantity: a count or a decimal at the report's own places, grouped", () => {
  const cases: Array<[string | number, string]> = [
    [99, "99"],
    [1234567, "1,234,567"],
    ["93.60", "93.60"],
    ["74.2", "74.2"],
    ["0.12", "0.12"],
    ["1234.5000", "1,234.5000"],
    ["113", "113"],
    ["-0.05", "-0.05"],
    ["-0.00", "0.00"], // a zero has no sign
  ];
  it.each(cases)("%s -> %s", (raw, shown) => {
    expect(formatValue("quantity", raw)).toBe(shown);
  });
  it("refuses what is not a number", () => {
    expect(() => formatValue("quantity", "ten")).toThrow();
    expect(() => formatValue("quantity", null)).toThrow();
  });
});

describe("multiple and cents: a quantity with its unit", () => {
  it("multiple", () => {
    expect(formatValue("multiple", "1.31")).toBe("1.31x");
    expect(formatValue("multiple", "10.00")).toBe("10.00x");
  });
  it("cents", () => {
    expect(formatValue("cents", "0.50")).toBe("0.50\u00a2");
    expect(formatValue("cents", "13.98")).toBe("13.98\u00a2");
  });
});

describe("passed and yesno: a true or false in words", () => {
  it("passed", () => {
    expect(formatValue("passed", true)).toBe("passed");
    expect(formatValue("passed", false)).toBe("failed");
  });
  it("yesno", () => {
    expect(formatValue("yesno", true)).toBe("yes");
    expect(formatValue("yesno", false)).toBe("no");
  });
  it("refuse what is not true or false", () => {
    expect(() => formatValue("passed", "yes")).toThrow();
    expect(() => formatValue("yesno", null)).toThrow();
  });
});

describe("decimal2: a decimal to two places, half away from zero", () => {
  const cases: Array<[string, string]> = [
    ["2.066174", "2.07"],
    ["8.183581", "8.18"],
    ["0.005", "0.01"],
    ["0.004999", "0.00"],
    ["1234.5", "1,234.50"],
    ["54.13", "54.13"],
    ["-0.004", "0.00"],
    ["-2.066", "-2.07"],
    ["113", "113.00"],
  ];
  it.each(cases)("%s -> %s", (raw, shown) => {
    expect(formatValue("decimal2", raw)).toBe(shown);
  });
});
