import { cleanup, render } from "@testing-library/react";
import { Children, Fragment, cloneElement, createElement, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { checkChart } from "../../binding/__tests__/harness";
import type { CapturedChart } from "../../binding/__tests__/harness";
import ForecastScreen from "../forecast/ForecastScreen";
import { expectedCharts } from "./forecastExpectations";
import * as files from "./files";

/**
 * The charts' real props. recharts is wrapped, not replaced: ResponsiveContainer is given a size
 * (jsdom has none) and ComposedChart records the data and the series elements it is handed before
 * drawing them. What is checked is what the chart component received, not a copy serialised beside it.
 */
const captured = vi.hoisted(() => [] as unknown[]);

vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  const flatten = (node: ReactNode): ReactElement[] =>
    Children.toArray(node).flatMap((child) =>
      isValidElement(child)
        ? child.type === Fragment
          ? flatten((child.props as { children?: ReactNode }).children)
          : [child as ReactElement]
        : [],
    );
  const nameOf = (el: ReactElement) => (el.type as { displayName?: string }).displayName ?? "";
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) => cloneElement(children, { width: 900, height: 320 } as object),
    ComposedChart: (props: { data: unknown; children: ReactNode }) => {
      const parts = flatten(props.children);
      captured.push({
        data: props.data,
        xKey: (parts.find((p) => nameOf(p) === "XAxis")?.props as { dataKey?: string } | undefined)?.dataKey,
        series: parts
          .filter((p) => ["Bar", "Area", "Line"].includes(nameOf(p)))
          .map((p) => ({ type: nameOf(p), dataKey: (p.props as { dataKey: string }).dataKey, stackId: (p.props as { stackId?: unknown }).stackId })),
        referenceX: parts.filter((p) => nameOf(p) === "ReferenceLine").map((p) => String((p.props as { x: unknown }).x)),
      } satisfies CapturedChart);
      return createElement(actual.ComposedChart, props as never);
    },
  };
});

beforeEach(() => {
  captured.length = 0;
});
afterEach(cleanup);

function draw(company: string, scenario: string, report = files.report(company, scenario)) {
  captured.length = 0;
  render(
    <BindingProvider company={company} scenario={scenario} files={{ report, index: files.index(), comparison: files.comparison(company) }}>
      <ForecastScreen />
    </BindingProvider>,
  );
  const [monthly, quarters] = captured as CapturedChart[];
  return { monthly, quarters };
}

const failuresFor = (got: { monthly: CapturedChart; quarters: CapturedChart }, want: ReturnType<typeof expectedCharts>) => [
  ...checkChart("monthly", got.monthly, want.monthly),
  ...checkChart("quarters", got.quarters, want.quarters),
];

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

describe("Forecast charts: the data and series each chart is given", () => {
  it.each(CASES)("%s / %s", (company, scenario) => {
    expect(failuresFor(draw(company, scenario), expectedCharts(files.report(company, scenario)))).toEqual([]);
  });

  it("an unavailable forecast is drawn with no fitted series and no zeros", () => {
    for (const [name, scenario] of [["short-history.report.json", "as-signed"], ["short-history-plan.report.json", "demo-plan"]] as const) {
      const report = files.fixture(name);
      const got = draw("sprout-labs", scenario, report);
      expect(failuresFor(got, expectedCharts(report))).toEqual([]);
      expect(got.monthly.series.map((s) => s.dataKey)).not.toContain("fitted");
    }
  });

  it("a plan's charts are the with-plan series, and also show the as-signed fitted line", () => {
    const got = draw("sprout-labs", "demo-plan");
    expect(got.monthly.series.map((s) => s.dataKey)).toEqual(["booked", "band95", "band80", "signed", "fitted", "stage", "runRate"]);
    const rows = got.monthly.data as Array<Record<string, unknown>>;
    const withPlan = files.report("sprout-labs", "demo-plan").plan as { with_plan_by_window: Record<string, string> };
    const first = [...rows].reverse().find((r) => r.fitted !== null && r.fitted !== undefined)!; // a month after the plan starts
    expect(first.fitted).toBe(Number(withPlan.with_plan_by_window[first.period as string]));
    expect(first.fitted).not.toBe(first.signed);
  });

  it("a closed quarter has no range plotted", () => {
    const got = draw("sapling-industries", "as-signed");
    const rows = got.quarters.data as Array<Record<string, unknown>>;
    expect(rows[0].range80).toBeNull();
    expect(rows[rows.length - 1].range80).toEqual(expect.any(Array));
  });
});

describe("Forecast charts: the checks fail when the chart is wrong (mutations at the chart's boundary)", () => {
  const good = () => {
    const got = draw("sapling-industries", "demo-plan");
    return { got, want: expectedCharts(files.report("sapling-industries", "demo-plan")) };
  };

  it("passes when nothing is changed", () => {
    const { got, want } = good();
    expect(failuresFor(got, want)).toEqual([]);
  });

  it("a series drawn from a different dataKey is caught", () => {
    const { got, want } = good();
    got.monthly.series.find((s) => s.dataKey === "fitted")!.dataKey = "stage";
    expect(failuresFor(got, want).some((f) => f.startsWith("monthly: series"))).toBe(true);
  });

  it("data transformed on its way into the chart is caught", () => {
    const { got, want } = good();
    got.monthly.data = (got.monthly.data as Array<Record<string, unknown>>).map((r) => ({ ...r, fitted: typeof r.fitted === "number" ? r.fitted * 1.1 : r.fitted }));
    expect(failuresFor(got, want).some((f) => f.includes("data given to the chart"))).toBe(true);
  });

  it("stacking, which would draw sums the file does not hold, is caught", () => {
    const { got, want } = good();
    got.monthly.series.find((s) => s.dataKey === "band80")!.stackId = "1";
    expect(failuresFor(got, want).some((f) => f.includes("stacked"))).toBe(true);
  });

  it("a dropped series, a moved reference line and the wrong x axis are caught", () => {
    const { got, want } = good();
    got.quarters.series.pop();
    got.monthly.referenceX = ["2026-01"];
    got.monthly.xKey = "month";
    const failures = failuresFor(got, want);
    expect(failures.some((f) => f.startsWith("quarters: series"))).toBe(true);
    expect(failures.some((f) => f.includes("reference lines"))).toBe(true);
    expect(failures.some((f) => f.includes("x axis"))).toBe(true);
  });

  it("another company's file is caught", () => {
    const got = draw("sprout-labs", "demo-plan", files.report("sapling-industries", "demo-plan"));
    expect(failuresFor(got, expectedCharts(files.report("sprout-labs", "demo-plan"))).length).toBeGreaterThan(0);
  });

  it("a flipped sign in a plotted series is caught", () => {
    const report = structuredClone(files.report("sapling-industries", "as-signed"));
    const fitted = report.forecasts.methods.find((m) => m.method === "fitted model")!;
    const key = Object.keys(fitted.by_window)[0];
    (fitted.by_window as Record<string, string>)[key] = `-${(fitted.by_window as Record<string, string>)[key]}`;
    const got = draw("sapling-industries", "as-signed", report);
    expect(failuresFor(got, expectedCharts(files.report("sapling-industries", "as-signed"))).some((f) => f.includes("data given"))).toBe(true);
  });
});
