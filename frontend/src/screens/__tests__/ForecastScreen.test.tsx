import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { ChartTooltip } from "../../binding/ChartKit";
import { checkBindings, checkPlotted, openAll, unboundDigits } from "../../binding/__tests__/harness";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { B, MONTHLY_SERIES, QUARTER_SERIES } from "../forecast/bindings";
import ForecastScreen from "../forecast/ForecastScreen";
import { expectations, plotted } from "./forecastExpectations";
import type { Case } from "./forecastExpectations";
import * as files from "./files";
import * as fmt from "./independent";

afterEach(cleanup);

const LISTED = Object.values(B).map((b) => b.id);

interface Shown {
  container: HTMLElement;
}

/** Render the screen on `shown` files while the test expects `expected` (they differ only in a mutation). */
function mount(shown: { report: TieoutReport; index: ReportIndex; comparison: ScenarioComparison }, company: string, scenario: string): Shown {
  const { container } = render(
    <BindingProvider company={company} scenario={scenario} files={shown}>
      <ForecastScreen />
    </BindingProvider>,
  );
  openAll(container);
  return { container };
}

function allFailures(c: HTMLElement, expected: Case): string[] {
  const { expected: want, absent } = expectations(expected);
  return [
    ...checkBindings(c, want, absent, LISTED),
    ...unboundDigits(c).map((t) => `digits outside a bound element: ${t}`),
    ...checkPlotted(c, plotted(expected.report)),
  ];
}

const caseOf = (company: string, scenario: string): Case => ({
  company,
  scenario,
  report: files.report(company, scenario),
  index: files.index(),
  comparison: files.comparison(company),
});

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

describe("Forecast: every binding, every digit, every chart", () => {
  it.each(CASES)("%s / %s", (company, scenario) => {
    const c = caseOf(company, scenario);
    const { container } = mount(c, company, scenario);
    expect(allFailures(container, c)).toEqual([]);
  });

  it("the committed list and the independent expectations name the same bindings", () => {
    const c = caseOf("sprout-labs", "demo-plan");
    const { expected, absent } = expectations(c);
    const named = [...expected.map((e) => e.id), ...absent.map((a) => a.id)];
    expect([...new Set(named)].sort()).toEqual([...LISTED].sort());
    expect(new Set(LISTED).size).toBe(LISTED.length);
  });

  it("the list covers the inventory in the spec's Forecast row", () => {
    const ids = new Set(LISTED);
    for (const id of [
      "year.target", "year.actual", "year.expected", "year.gap", // the year and its gap
      "year.range80.low", "year.range80.high", "year.range95.low", "year.range95.high", // both bands
      "year.range.status", "next12.range.status", "cell.label", // their validation label
      "quarter.gap", "next12.gap", // the gap by quarter, and both windows
      "verdict.software", "verdict.software.summary", "verdict.better", "verdict.better.reason", // both verdicts, with reasons
    ]) expect(ids.has(id), id).toBe(true);
  });

  it("shows the baselines as point forecasts with no range, and the booked months to date", () => {
    const { container } = mount(caseOf("sapling-industries", "as-signed"), "sapling-industries", "as-signed");
    expect(container.textContent).toContain("Stage-weighted (point forecast, no range)");
    expect(container.textContent).toContain("Trailing run-rate (point forecast, no range)");
    const rows = JSON.parse(container.querySelector("[data-chart='monthly']")!.getAttribute("data-plotted")!) as Array<Record<string, unknown>>;
    expect(rows.filter((r) => r.booked !== null).length).toBe(Object.keys(files.report("sapling-industries", "as-signed").reconciliation.bookings_by_month).length);
    // only the fitted model has bands; the baselines have a value per month and no range of any kind
    expect(new Set(rows.flatMap((r) => Object.keys(r)))).toEqual(new Set(["period", "booked", "band95", "band80", "fitted", "stage", "runRate"]));
    expect(rows.some((r) => r.fitted !== null && Array.isArray(r.band80) && Array.isArray(r.band95))).toBe(true);
  });
});

describe("Forecast: tooltips and expanded rows are held to the same rule", () => {
  it("every row of every chart's tooltip shows the file's figure and nothing else", () => {
    for (const [company, scenario] of [["sapling-industries", "demo-plan"], ["mighty-oak-holdings", "as-signed"]] as const) {
      const r = files.report(company, scenario);
      const fitted = r.forecasts.methods.find((m) => m.method === "fitted model")!;
      const monthly = Object.values(MONTHLY_SERIES);
      for (const period of r.forecasts.windows) {
        const { container } = render(
          <BindingProvider company={company} scenario={scenario} files={{ report: r, index: files.index(), comparison: files.comparison(company) }}>
            <ChartTooltip
              chartId="monthly"
              specs={monthly}
              active
              label={period}
              payload={monthly
                .filter((s) => (plotted(r).monthly as Array<Record<string, unknown>>).find((row) => row.period === period)?.[s.key] != null)
                .map((s) => ({ dataKey: s.key, value: 1 }))}
              periodFormat={(p) => fmt.month(p)}
            />
          </BindingProvider>,
        );
        expect(unboundDigits(container)).toEqual([]);
        const text = (key: string) => container.querySelector(`[data-tooltip-row="${key}"] .font-medium`)?.textContent;
        const ranges = r.forecasts.fitted_ranges.by_window as Record<string, { range80: [string, string]; range95: [string, string] }>;
        expect(text("fitted")).toBe(fmt.usdShort((fitted.by_window as Record<string, string>)[period]));
        expect(text("band80")).toBe(`${fmt.usdShort(ranges[period].range80[0])} to ${fmt.usdShort(ranges[period].range80[1])}`);
        expect(text("band95")).toBe(`${fmt.usdShort(ranges[period].range95[0])} to ${fmt.usdShort(ranges[period].range95[1])}`);
        expect(container.querySelector("[data-exempt='period-label']")?.textContent).toBe(fmt.month(period));
        cleanup();
      }
      const quarters = Object.values(QUARTER_SERIES);
      for (const q of r.gap.quarters) {
        const { container } = render(
          <BindingProvider company={company} scenario={scenario} files={{ report: r, index: files.index(), comparison: files.comparison(company) }}>
            <ChartTooltip chartId="quarters" specs={quarters} active label={q.quarter} payload={quarters.map((s) => ({ dataKey: s.key, value: 1 }))} periodFormat={(p) => p} />
          </BindingProvider>,
        );
        expect(unboundDigits(container)).toEqual([]);
        const text = (key: string) => container.querySelector(`[data-tooltip-row="${key}"] .font-medium`)?.textContent;
        expect(text("target")).toBe(fmt.usdShort(q.target));
        expect(text("expected")).toBe(fmt.usdShort(q.expected!));
        expect(text("range80")).toBe(`${fmt.usdShort(q.expected_range80![0])} to ${fmt.usdShort(q.expected_range80![1])}`);
        cleanup();
      }
    }
  });

  it("opening a quarter row shows its 80% range, and it is bound", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const { container } = render(
      <BindingProvider company="sprout-labs" scenario="as-signed" files={c}>
        <ForecastScreen />
      </BindingProvider>,
    );
    expect(container.querySelectorAll("[data-binding='quarter.range80.low']").length).toBe(0);
    const toggles = container.querySelectorAll<HTMLButtonElement>("button[aria-label='Show the range of this quarter']");
    expect(toggles.length).toBe(c.report.gap.quarters.length);
    fireEvent.click(toggles[1]);
    const low = container.querySelectorAll("[data-binding='quarter.range80.low']");
    const high = container.querySelectorAll("[data-binding='quarter.range80.high']");
    expect([low.length, high.length]).toEqual([1, 1]);
    const range = c.report.gap.quarters[1].expected_range80!;
    expect(low[0].textContent).toBe(fmt.usdShort(range[0]));
    expect(high[0].textContent).toBe(fmt.usdShort(range[1]));
    expect(unboundDigits(container)).toEqual([]);
    fireEvent.click(toggles[1]);
    expect(container.querySelectorAll("[data-binding='quarter.range80.low']").length).toBe(0);
  });
});

describe("Forecast: a report that cannot forecast says so in words, never as zero", () => {
  it.each([["short-history.report.json", "as-signed"], ["short-history-plan.report.json", "demo-plan"]] as const)(
    "%s",
    (name, scenario) => {
      const shown = { report: files.fixture(name), index: files.index(), comparison: files.comparison("sprout-labs") };
      const c: Case = { company: "sprout-labs", scenario, ...shown };
      const { container } = mount(shown, "sprout-labs", scenario);
      expect(allFailures(container, c)).toEqual([]);
      const text = container.textContent ?? "";
      expect(text).toContain("The fitted forecast is unavailable");
      expect(text).toMatch(/unavailable: /);
      // no fitted figure is drawn or shown as a zero
      for (const id of ["year.expected", "year.gap", "year.range80.low"]) {
        const el = container.querySelector(`[data-binding="${id}"]`)!;
        expect(el.getAttribute("data-unavailable")).toBe("true");
        expect(el.textContent).not.toMatch(/\$0/);
      }
      expect(container.querySelector("[data-chart='monthly']")!.getAttribute("data-plotted")).not.toContain("fitted");
    },
  );
});

describe("Forecast: the checks fail when the screen is wrong (mutations)", () => {
  it("a swapped path is caught", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const original = B.yearExpected.path;
    (B.yearExpected as { path: string }).path = B.yearTarget.path;
    try {
      const { container } = mount(c, c.company, c.scenario);
      const failures = allFailures(container, c);
      expect(failures.some((f) => f.startsWith("year.expected"))).toBe(true);
    } finally {
      (B.yearExpected as { path: string }).path = original;
    }
  });

  it("a swapped chart series path is caught in the plotted data", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const original = MONTHLY_SERIES.fitted.path;
    (MONTHLY_SERIES.fitted as { path: string }).path = MONTHLY_SERIES.stage.path;
    try {
      const { container } = mount(c, c.company, c.scenario);
      expect(allFailures(container, c).some((f) => f.startsWith("monthly: plotted data differs"))).toBe(true);
    } finally {
      (MONTHLY_SERIES.fitted as { path: string }).path = original;
    }
  });

  it("another company's file is caught, in the figures and in the charts", () => {
    const expected = caseOf("sapling-industries", "as-signed");
    const other = caseOf("sprout-labs", "as-signed");
    const { container } = mount(other, "sapling-industries", "as-signed");
    const failures = allFailures(container, expected);
    expect(failures.some((f) => f.startsWith("year.expected"))).toBe(true);
    expect(failures.some((f) => f.startsWith("monthly: plotted data differs"))).toBe(true);
    expect(failures.some((f) => f.startsWith("quarters: plotted data differs"))).toBe(true);
  });

  it("a flipped sign is caught", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const flipped = structuredClone(c.report);
    flipped.gap.fiscal_year.gap = `-${flipped.gap.fiscal_year.gap}`;
    flipped.gap.quarters[0].gap = flipped.gap.quarters[0].gap!.startsWith("-") ? flipped.gap.quarters[0].gap!.slice(1) : `-${flipped.gap.quarters[0].gap}`;
    const { container } = mount({ ...c, report: flipped }, c.company, c.scenario);
    const failures = allFailures(container, c);
    expect(failures.some((f) => f.startsWith("year.gap"))).toBe(true);
    expect(failures.some((f) => f.startsWith("quarter.gap"))).toBe(true);
  });

  it("a chart series with a flipped sign is caught in the plotted data", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const flipped = structuredClone(c.report);
    const fitted = flipped.forecasts.methods.find((m) => m.method === "fitted model")!;
    const key = Object.keys(fitted.by_window)[0];
    (fitted.by_window as Record<string, string>)[key] = `-${(fitted.by_window as Record<string, string>)[key]}`;
    const { container } = mount({ ...c, report: flipped }, c.company, c.scenario);
    expect(allFailures(container, c).some((f) => f.startsWith("monthly: plotted data differs"))).toBe(true);
  });

  it("a digit outside any bound element is caught", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const { container } = mount(c, c.company, c.scenario);
    const stray = document.createElement("p");
    stray.textContent = "Revenue is up 12% on last year";
    container.appendChild(stray);
    expect(unboundDigits(container)).toEqual(["Revenue is up 12% on last year"]);
  });

  it("a bound element that is not on the committed list is caught", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const { container } = mount(c, c.company, c.scenario);
    const extra = document.createElement("span");
    extra.setAttribute("data-binding", "sneaky");
    container.appendChild(extra);
    expect(allFailures(container, c).some((f) => f.startsWith("sneaky"))).toBe(true);
  });
});
