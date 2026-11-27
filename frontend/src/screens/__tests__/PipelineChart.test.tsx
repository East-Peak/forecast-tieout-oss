import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { ChartTooltip } from "../../binding/ChartKit";
import { checkChart, unboundDigits } from "../../binding/__tests__/harness";
import type { CapturedChart, ExpectedChart } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { SERIES } from "../pipeline/bindings";
import PipelineScreen from "../pipeline/PipelineScreen";
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
  const rp = r.required_pipeline;
  if ("unavailable" in rp) throw new Error("no chart expected");
  return {
    data: rp.quarters
      .map((q) => ({
        period: q.quarter,
        expected: Number(q.expected_created_pipeline),
        required: q.required_extra_pipeline === null ? null : Number(q.required_extra_pipeline),
      }))
      .sort((a, b) => a.period.localeCompare(b.period)),
    xKey: "period",
    series: [{ type: "Bar", dataKey: "expected" }, { type: "Bar", dataKey: "required" }],
  };
}

function draw(company: string, scenario: string, report = files.report(company, scenario)): CapturedChart | undefined {
  captured.length = 0;
  render(
    <BindingProvider company={company} scenario={scenario} files={{ report, index: files.index(), comparison: files.comparison(company) }}>
      <PipelineScreen />
    </BindingProvider>,
  );
  return captured[0] as CapturedChart | undefined;
}

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

describe("Pipeline chart: the data and series it is given", () => {
  it.each(CASES)("%s / %s", (company, scenario) => {
    expect(checkChart("pipeline", draw(company, scenario), expectedChart(files.report(company, scenario)))).toEqual([]);
  });

  it("a quarter where no amount helps has no bar for the extra, never a zero", () => {
    const got = draw("sprout-labs", "as-signed")!;
    const rows = got.data as Array<Record<string, unknown>>;
    expect(rows.find((r) => r.period === "Q3FY26")!.required).toBeNull();
    expect(rows.find((r) => r.period === "Q4FY26")!.required).toEqual(expect.any(Number));
  });

  it("no chart is drawn when the requirement cannot be computed", () => {
    const report = structuredClone(files.report("sprout-labs", "as-signed"));
    report.required_pipeline = { unavailable: "the fitted forecast is unavailable" };
    expect(draw("sprout-labs", "as-signed", report)).toBeUndefined();
  });
});

describe("Pipeline chart: the checks fail when the chart is wrong", () => {
  const want = () => expectedChart(files.report("sapling-industries", "as-signed"));
  const got = () => draw("sapling-industries", "as-signed")!;

  it("passes when nothing is changed", () => {
    expect(checkChart("pipeline", got(), want())).toEqual([]);
  });

  it("a series drawn from another key, stacking, and transformed data are caught", () => {
    const a = got();
    a.series[1].dataKey = "expected";
    expect(checkChart("pipeline", a, want()).some((f) => f.includes("series"))).toBe(true);
    const b = got();
    b.series[0].stackId = "1";
    expect(checkChart("pipeline", b, want()).some((f) => f.includes("stacked"))).toBe(true);
    const c = got();
    c.data = (c.data as Array<Record<string, number>>).map((r) => ({ ...r, expected: r.expected * 2 })); // test-side corruption
    expect(checkChart("pipeline", c, want()).some((f) => f.includes("data given"))).toBe(true);
  });

  it("another company's file and a flipped value are caught", () => {
    expect(checkChart("pipeline", draw("sprout-labs", "as-signed", files.report("sapling-industries", "as-signed")), expectedChart(files.report("sprout-labs", "as-signed"))).length).toBeGreaterThan(0);
    const report = structuredClone(files.report("sapling-industries", "as-signed"));
    const rp = report.required_pipeline;
    if ("unavailable" in rp) throw new Error("unavailable");
    rp.quarters[0].expected_created_pipeline = `-${rp.quarters[0].expected_created_pipeline}` as never;
    expect(checkChart("pipeline", draw("sapling-industries", "as-signed", report), want()).length).toBeGreaterThan(0);
  });
});

describe("Pipeline chart: a hover's rows are read back from the file", () => {
  it("each bar shows the report's own value for the quarter, and its label is the report's", () => {
    for (const company of files.COMPANIES) {
      const r = files.report(company, "as-signed");
      const rp = r.required_pipeline;
      if ("unavailable" in rp) throw new Error("unavailable");
      const q = rp.quarters[1];
      const { container } = render(
        <BindingProvider company={company} scenario="as-signed" files={{ report: r, index: files.index(), comparison: files.comparison(company) }}>
          <ChartTooltip
            chartId="pipeline-quarters"
            specs={Object.values(SERIES)}
            active
            label={q.quarter}
            payload={Object.keys(SERIES).map((key) => ({ dataKey: key, value: key === "required" && q.required_extra_pipeline === null ? null : 1 }))}
            periodFormat={(p) => p}
          />
        </BindingProvider>,
      );
      expect(unboundDigits(container, [q.quarter])).toEqual([]);
      const text = (key: string) => container.querySelector(`[data-tooltip-row="${key}"] .font-medium`)?.textContent;
      expect(text("expected")).toBe(fmt.usdShort(q.expected_created_pipeline));
      expect(text("required")).toBe(q.required_extra_pipeline === null ? undefined : fmt.usdShort(q.required_extra_pipeline));
      cleanup();
    }
  });
});
