import { describe, expect, it } from "vitest";
import { buildChart } from "../chartData";
import type { SeriesSpec } from "../chartData";

const doc = {
  booked: { "2026-07": "100.50", "2026-08": "200.00" },
  windows: ["2026-09", "2026-10"],
  fitted: { "2026-09": "300.25", "2026-10": "400.00" },
  band: { "2026-09": { range80: ["250.00", "350.00"] }, "2026-10": { range80: ["300.00", "500.00"] } },
  quarters: [
    { quarter: "Q1FY26", expected: "10.00", range80: ["8.00", "12.00"] },
    { quarter: "Q2FY26", expected: "20.00", range80: null },
  ],
};

const booked: SeriesSpec = { key: "booked", label: "Booked", kind: "decimal", path: "/booked/{period}", periods: { keysAt: "/booked" } };
const fitted: SeriesSpec = { key: "fitted", label: "Fitted", kind: "decimal", path: "/fitted/{period}", periods: { arrayAt: "/windows" } };
const band: SeriesSpec = { key: "band", label: "80% range", kind: "range", path: "/band/{period}/range80", periods: { arrayAt: "/windows" } };

describe("buildChart", () => {
  it("lays every series on the union of its periods, in period order, with nothing invented between", () => {
    const { periods, rows } = buildChart(doc, [fitted, booked]);
    expect(periods).toEqual(["2026-07", "2026-08", "2026-09", "2026-10"]);
    expect(rows).toEqual([
      { period: "2026-07", fitted: null, booked: 100.5 },
      { period: "2026-08", fitted: null, booked: 200 },
      { period: "2026-09", fitted: 300.25, booked: null },
      { period: "2026-10", fitted: 400, booked: null },
    ]);
  });

  it("a range is a pair [low, high] read from the file, not computed", () => {
    const { rows } = buildChart(doc, [fitted, band]);
    expect(rows[0]).toEqual({ period: "2026-09", fitted: 300.25, band: [250, 350] });
    expect(rows[1].band).toEqual([300, 500]);
  });

  it("periods can be a property of the rows of an array, and a path can pick a row by it", () => {
    const expected: SeriesSpec = {
      key: "expected",
      label: "Expected",
      kind: "decimal",
      path: "/quarters/{quarter={period}}/expected",
      periods: { rowsAt: "/quarters", property: "quarter" },
    };
    const { rows } = buildChart(doc, [expected]);
    expect(rows).toEqual([
      { period: "Q1FY26", expected: 10 },
      { period: "Q2FY26", expected: 20 },
    ]);
  });

  it("a series can leave out the rows that say they have nothing to plot (a closed quarter has no range)", () => {
    const range: SeriesSpec = {
      key: "range",
      label: "Range",
      kind: "range",
      path: "/quarters/{quarter={period}}/range80",
      periods: { rowsAt: "/quarters", property: "quarter", unless: ["quarter", "Q2FY26"] },
    };
    const { rows } = buildChart(doc, [range]);
    expect(rows).toEqual([{ period: "Q1FY26", range: [8, 12] }]);
  });

  it("a null the file holds stays null (a gap in the line), never zero", () => {
    const range: SeriesSpec = {
      key: "range",
      label: "Range",
      kind: "range",
      path: "/quarters/{quarter={period}}/range80",
      periods: { rowsAt: "/quarters", property: "quarter" },
    };
    const { rows } = buildChart(doc, [range]);
    expect(rows[0].range).toEqual([8, 12]);
    expect(rows[1].range).toBeNull();
  });

  it("a declared path that leads nowhere is an error, not an empty series", () => {
    const wrong: SeriesSpec = { ...fitted, path: "/fitted/{period}/nope" };
    expect(() => buildChart(doc, [wrong])).toThrow(/unbound path/);
  });

  it("a value that is not a decimal string is an error, not NaN", () => {
    const text: SeriesSpec = { key: "x", label: "x", kind: "decimal", path: "/windows/{period}", periods: { arrayAt: "/windows" } };
    expect(() => buildChart({ ...doc }, [{ ...text, path: "/windows/0" }])).toThrow(/decimal/);
  });
});

describe("a value the file holds as a JSON count", () => {
  it("is plotted as that count, beside decimals", () => {
    const monthly = {
      months: [
        { month: "2026-07", heads: 96, ramped: "92.04" },
        { month: "2026-08", heads: "74.2", ramped: "93.96" },
      ],
    };
    const from = { rowsAt: "/months", property: "month" } as const;
    const heads: SeriesSpec = { key: "heads", label: "Heads", kind: "decimal", path: "/months/{month={period}}/heads", periods: from };
    expect(buildChart(monthly, [heads]).rows).toEqual([
      { period: "2026-07", heads: 96 },
      { period: "2026-08", heads: 74.2 },
    ]);
  });
  it("a string that is not a decimal is still refused", () => {
    const bad = { months: [{ month: "2026-07", heads: "many" }] };
    const heads: SeriesSpec = { key: "heads", label: "Heads", kind: "decimal", path: "/months/{month={period}}/heads", periods: { rowsAt: "/months", property: "month" } };
    expect(() => buildChart(bad, [heads])).toThrow(/decimal/);
  });
});
