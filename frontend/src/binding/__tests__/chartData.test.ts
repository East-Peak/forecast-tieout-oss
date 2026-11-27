import { describe, expect, it } from "vitest";
import { buildChart, plotExtent, plotPoint } from "../chartData";
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

describe("rows plotted by position, spans and gaps (the worksheet's charts)", () => {
  const sheet = {
    rows: [
      { id: "z", kind: "a", to: "30.00", from: null, low: { change: "-5.50" } },
      { id: "a", kind: "b", to: "40.00", from: "30.00", low: null },
      { id: "m", kind: "a", to: "50.00", from: "40.00", low: { change: "7.25" } },
    ],
    target: { value: "60" },
  };
  const at = { indexesAt: "/rows" } as const;

  it("keeps the file's own order: nothing is sorted by name", () => {
    const spec: SeriesSpec = { key: "to", label: "To", kind: "decimal", path: "/rows/{period}/to", periods: at };
    expect(buildChart(sheet, [spec]).rows.map((r) => r.period)).toEqual(["0", "1", "2"]);
    const named: SeriesSpec = { ...spec, path: "/rows/{id={period}}/to", periods: { rowsAt: "/rows", property: "id" } };
    expect(buildChart(sheet, [named]).rows.map((r) => r.period)).toEqual(["a", "m", "z"]);
  });

  it("a span is [start, value] from two pointers, or the bare value where the file has no start", () => {
    const span: SeriesSpec = { key: "move", label: "Move", kind: "span", path: "/rows/{period}/to", from: "/rows/{period}/from", periods: at };
    expect(buildChart(sheet, [span]).rows).toEqual([
      { period: "0", move: 30 },
      { period: "1", move: [30, 40] },
      { period: "2", move: [40, 50] },
    ]);
  });

  it("a series can take only the rows whose property is one of the values; the series together lay out every row in the file's order", () => {
    const b: SeriesSpec = { key: "b", label: "B", kind: "decimal", path: "/rows/{period}/to", periods: { indexesAt: "/rows", where: ["kind", ["b"]] } };
    const a: SeriesSpec = { key: "a", label: "A", kind: "decimal", path: "/rows/{period}/to", periods: { indexesAt: "/rows", where: ["kind", ["a"]] } };
    expect(buildChart(sheet, [b]).rows).toEqual([{ period: "1", b: 40 }]);
    expect(buildChart(sheet, [b, a]).rows).toEqual([
      { period: "0", b: null, a: 30 },
      { period: "1", b: 40, a: null },
      { period: "2", b: null, a: 50 },
    ]);
  });

  it("a path through a null is a gap when the series says it may be, and an error otherwise", () => {
    const low: SeriesSpec = { key: "low", label: "Low", kind: "decimal", path: "/rows/{period}/low/change", periods: at };
    expect(() => buildChart(sheet, [low])).toThrow(/unbound path/);
    expect(buildChart(sheet, [{ ...low, nullable: true }]).rows.map((r) => r.low)).toEqual([-5.5, null, 7.25]);
  });

  it("the shared scale runs over every series' values, with zero and padding only when asked", () => {
    const { rows } = buildChart(sheet, [
      { key: "low", label: "Low", kind: "decimal", path: "/rows/{period}/low/change", periods: at, nullable: true },
      { key: "move", label: "Move", kind: "span", path: "/rows/{period}/to", from: "/rows/{period}/from", periods: at },
    ]);
    expect(plotExtent(rows, ["low", "move"], { zero: false, padding: 0 })).toEqual([-5.5, 50]);
    expect(plotExtent(rows, ["move"], { zero: true, padding: 0 })).toEqual([0, 50]);
    expect(plotExtent(rows, ["move"], { zero: false, padding: 0.1 })).toEqual([28, 52]);
  });

  it("a bar stands on zero: [0, value] above it and [value, 0] below it, and a gap stays a gap", () => {
    const bar: SeriesSpec = { key: "bar", label: "Bar", kind: "bar", path: "/rows/{period}/low/change", periods: at, nullable: true };
    const { rows } = buildChart(sheet, [bar]);
    expect(rows.map((r) => r.bar)).toEqual([[-5.5, 0], null, [0, 7.25]]);
    expect(plotExtent(rows, ["bar"], { zero: true, padding: 0 })).toEqual([-5.5, 7.25]);
  });

  it("a reference point is one decimal read from the file", () => {
    expect(plotPoint(sheet, "/target/value")).toBe(60);
    expect(() => plotPoint(sheet, "/target/nope")).toThrow(/unbound path/);
  });
});
