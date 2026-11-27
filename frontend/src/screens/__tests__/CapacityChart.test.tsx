import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { ChartTooltip } from "../../binding/ChartKit";
import { checkChart, unboundDigits } from "../../binding/__tests__/harness";
import type { CapturedChart, ExpectedChart } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { SERIES } from "../capacity/bindings";
import CapacityScreen from "../capacity/CapacityScreen";
import * as files from "./files";
import * as fmt from "./independent";

const captured = vi.hoisted(() => [] as unknown[]);
vi.mock("recharts", async (importOriginal) => {
  const { withCapture } = await import("./rechartsCapture");
  return withCapture(await importOriginal<typeof import("recharts")>(), captured);
});

beforeEach(() => {
  captured.length = 0;
});
afterEach(cleanup);

/** What the chart must have been given, from typed accessors (not from the screen's declared paths). */
function expectedChart(r: TieoutReport): ExpectedChart {
  const rows = (r.roster_capacity.months ?? []).map((m) => ({
    period: m.month,
    ramped: Number(m.ramped),
    heads: Number(m.heads),
    target: m.headcount_target,
  }));
  return {
    data: [...rows].sort((a, b) => a.period.localeCompare(b.period)),
    xKey: "period",
    series: [{ type: "Bar", dataKey: "ramped" }, { type: "Line", dataKey: "heads" }, { type: "Line", dataKey: "target" }],
    referenceX: [r.inputs.as_of.slice(0, 7)],
  };
}

function draw(company: string, scenario: string, report = files.report(company, scenario)): CapturedChart | undefined {
  captured.length = 0;
  render(
    <BindingProvider company={company} scenario={scenario} files={{ report, index: files.index(), comparison: files.comparison(company) }}>
      <CapacityScreen />
    </BindingProvider>,
  );
  return captured[0] as CapturedChart | undefined;
}

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

describe("Capacity chart: the data and series it is given", () => {
  it.each(CASES)("%s / %s", (company, scenario) => {
    expect(checkChart("capacity", draw(company, scenario), expectedChart(files.report(company, scenario)))).toEqual([]);
  });

  it("a month with no headcount target is a gap in the target line, never a zero", () => {
    const report = structuredClone(files.report("sapling-industries", "as-signed"));
    report.roster_capacity.months![0].headcount_target = null;
    const got = draw("sapling-industries", "as-signed", report)!;
    expect((got.data as Array<Record<string, unknown>>)[0].target).toBeNull();
  });
});

describe("Capacity chart: the checks fail when the chart is wrong", () => {
  const want = () => expectedChart(files.report("sapling-industries", "as-signed"));
  const got = () => draw("sapling-industries", "as-signed")!;

  it("passes when nothing is changed", () => {
    expect(checkChart("capacity", got(), want())).toEqual([]);
  });

  it("a series drawn from another key is caught", () => {
    const g = got();
    g.series.find((s) => s.dataKey === "heads")!.dataKey = "ramped";
    expect(checkChart("capacity", g, want()).some((f) => f.includes("series"))).toBe(true);
  });

  it("data transformed on its way into the chart is caught", () => {
    const g = got();
    g.data = (g.data as Array<Record<string, number>>).map((r) => ({ ...r, heads: r.heads * 1.1 })); // test-side corruption
    expect(checkChart("capacity", g, want()).some((f) => f.includes("data given"))).toBe(true);
  });

  it("another company's file and a flipped value are caught", () => {
    expect(checkChart("capacity", draw("sprout-labs", "as-signed", files.report("sapling-industries", "as-signed")), expectedChart(files.report("sprout-labs", "as-signed"))).length).toBeGreaterThan(0);
    const report = structuredClone(files.report("sapling-industries", "as-signed"));
    report.roster_capacity.months![3].ramped = `-${report.roster_capacity.months![3].ramped}` as never;
    expect(checkChart("capacity", draw("sapling-industries", "as-signed", report), want()).length).toBeGreaterThan(0);
  });

  it("a moved reference line is caught", () => {
    const g = got();
    g.referenceX = ["2026-01"];
    expect(checkChart("capacity", g, want()).some((f) => f.includes("reference"))).toBe(true);
  });
});

describe("Capacity chart: a hover's rows are read back from the file", () => {
  it("each series shows the report's own value at the month, and its period label is the report's", () => {
    for (const [company, index] of [["sapling-industries", 3], ["sprout-labs", 15], ["mighty-oak-holdings", 20]] as const) {
      const r = files.report(company, "as-signed");
      const m = r.roster_capacity.months![index];
      const { container } = render(
        <BindingProvider company={company} scenario="as-signed" files={{ report: r, index: files.index(), comparison: files.comparison(company) }}>
          <ChartTooltip
            chartId="capacity-months"
            specs={Object.values(SERIES)}
            active
            label={m.month}
            payload={Object.keys(SERIES).map((key) => ({ dataKey: key, value: key === "target" && m.headcount_target === null ? null : 1 }))}
            periodFormat={(p) => fmt.month(p)}
          />
        </BindingProvider>,
      );
      expect(unboundDigits(container, [fmt.month(m.month)])).toEqual([]);
      const text = (key: string) => container.querySelector(`[data-tooltip-row="${key}"] .font-medium`)?.textContent;
      expect(text("heads")).toBe(fmt.quantity(m.heads));
      expect(text("ramped")).toBe(fmt.quantity(m.ramped));
      expect(text("target")).toBe(m.headcount_target === null ? undefined : fmt.quantity(m.headcount_target));
      cleanup();
    }
  });
});
