import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { ChartTooltip } from "../../binding/ChartKit";
import { checkBindings, openAll, unboundDigits } from "../../binding/__tests__/harness";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { B, LISTED_BINDINGS, PLANNED, SIGNED, STRETCH, monthlySeries, quarterSeries } from "../forecast/bindings";
import ForecastScreen from "../forecast/ForecastScreen";
import { expectations, listFor } from "./forecastExpectations";
import type { Case } from "./forecastExpectations";
import * as files from "./files";
import * as fmt from "./independent";

afterEach(cleanup);

type Shown = { report: TieoutReport; index: ReportIndex; comparison: ScenarioComparison };

/** Render the screen on `shown` files, with every expandable thing opened. */
function mount(shown: Shown, company: string, scenario: string): HTMLElement {
  const { container } = render(
    <BindingProvider company={company} scenario={scenario} files={shown}>
      <ForecastScreen />
    </BindingProvider>,
  );
  openAll(container);
  return container;
}

/** Every failure of checks 1 and 2 for what is on the page against what the case calls for. */
function allFailures(container: HTMLElement, expected: Case): string[] {
  const { expected: want, absent, badge, periodLabels } = expectations(expected);
  const failures = [
    ...checkBindings(container, want, absent, listFor(expected.report), expected),
    ...unboundDigits(container, periodLabels).map((t) => `digits outside a bound element: ${t}`),
  ];
  const shown = container.querySelector<HTMLElement>("[data-testid='gap-badge']");
  if (badge === null) {
    if (shown) failures.push("a gap badge with no gap");
  } else if (!shown || shown.textContent !== badge.text || shown.getAttribute("data-sign") !== badge.sign) {
    failures.push(`gap badge: expected ${badge.text}, page shows ${shown?.textContent ?? "none"}`);
  }
  return failures;
}

const caseOf = (company: string, scenario: string): Case => ({
  company,
  scenario,
  report: files.report(company, scenario),
  index: files.index(),
  comparison: files.comparison(company),
});

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

describe("Forecast: every binding (with its provenance), every digit", () => {
  it.each(CASES)("%s / %s", (company, scenario) => {
    const c = caseOf(company, scenario);
    expect(allFailures(mount(c, company, scenario), c)).toEqual([]);
  });

  it("the committed list and the independent expectations name the same bindings", () => {
    const named = new Set<string>();
    for (const [company, scenario] of [["sprout-labs", "as-signed"], ["sprout-labs", "demo-plan"]] as const) {
      const { expected, absent } = expectations(caseOf(company, scenario));
      [...expected, ...absent].forEach((e) => named.add(e.id));
    }
    const listed = new Set(LISTED_BINDINGS.map((b) => b.id));
    expect([...named].sort()).toEqual([...listed].sort());
    expect(Object.values(B).length + Object.values(SIGNED).length).toBe(new Set([...Object.values(B), ...Object.values(SIGNED)].map((b) => b.id)).size);
    // the two views bind the same ids to different places
    expect(Object.values(PLANNED).map((b) => b.id)).toEqual(Object.values(SIGNED).map((b) => b.id));
  });

  it("the list covers the inventory in the spec's Forecast row", () => {
    const ids = new Set(LISTED_BINDINGS.map((b) => b.id));
    for (const id of [
      "year.target", "year.actual", "year.expected", "year.gap", "year.range80.low", "year.range80.high",
      "year.range95.low", "year.range95.high", "year.range.status", "check.next12.status", "cell.label",
      "quarter.gap", "next12.gap", "next12.total", "verdict.software", "verdict.software.summary",
      "verdict.better", "verdict.better.reason", "verdict.better.model", "verdict.better.stage",
    ]) expect(ids.has(id), id).toBe(true);
  });

  it("names the baselines for what they are, with no range", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const container = mount(c, c.company, c.scenario);
    expect(container.textContent).toContain("Stage-weighted pipeline (no range)");
    expect(container.textContent).toContain("Last twelve months' pace (no range)");
    expect(container.textContent).not.toContain("point forecast");
    expect(container.textContent).not.toContain("Trailing run-rate");
  });

  it("says under the monthly chart what the two dotted lines are and why the stage-weighted one falls away", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const note = container.querySelector("[data-testid='baseline-note']");
    expect(note?.textContent).toBe(
      "The two dotted lines are the simple yardsticks the fitted model is scored against. The stage-weighted line falls away because today's open deals close out first and only a thin flow of new pipeline follows them.",
    );
    expect(note?.textContent).not.toMatch(/\d/);
  });
});

describe("Forecast: the selected scenario governs the screen", () => {
  it("a plan's headline, tables and ranges are the with-plan figures, with the as-signed figure beside", () => {
    const c = caseOf("sprout-labs", "demo-plan");
    const container = mount(c, c.company, c.scenario);
    const text = (id: string) => container.querySelector(`[data-binding='${id}']`)!.textContent;
    const plan = c.report.plan as Extract<NonNullable<TieoutReport["plan"]>, { items: unknown }>;
    expect(text("year.gap")).toBe(fmt.usdShort(plan.gap.fiscal_year.gap_with_plan));
    expect(text("year.gap")).not.toBe(fmt.usdShort(c.report.gap.fiscal_year.gap!));
    expect(text("year.gap.signed")).toBe(fmt.usdShort(c.report.gap.fiscal_year.gap!));
    expect(text("year.expected")).toBe(fmt.usdShort(plan.expected_fiscal_year));
    // the same figure the scenario panel reads from comparison.json
    expect(text("scenario.gap")).toBe(text("year.gap"));
    expect(text("scenario.expected")).toBe(text("year.expected"));
    expect(container.querySelector("[data-testid='range-trust']")!.textContent).toContain("include the plan");
  });

  it("a scenario with no plan shows no as-signed comparison, and every scenario's headline equals its comparison row", () => {
    for (const [company, scenario] of CASES) {
      const c = caseOf(company, scenario);
      const container = mount(c, company, scenario);
      const text = (id: string) => container.querySelector(`[data-binding='${id}']`)?.textContent;
      if (scenario === "as-signed") expect(text("year.gap.signed")).toBeUndefined();
      else {
        expect(text("year.gap")).toBe(text("scenario.gap"));
        expect(text("year.expected")).toBe(text("scenario.expected"));
      }
      cleanup();
    }
  });
});

describe("Forecast: the label beside every range, and how the stretch was checked", () => {
  const labelsOf = (container: HTMLElement) => Array.from(container.querySelectorAll("[data-testid='range-label']")).map((el) => el.textContent);

  it("a company whose ranges were stretched says so briefly under both range cards, with no dates and no counts", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const fy = c.report.gap.fiscal_year as unknown as { label_short: string; label95: string };
    expect(c.report.backtest.candidates.ranges.decision).toBe("adopted");
    expect(labelsOf(container)).toEqual([fy.label_short, fy.label95]);
    expect(fy.label_short).toBe("Stretched on the low side by past misses");
    expect(fy.label95).toBe("Stretched the same way; not separately tested; floored at zero");
    for (const text of labelsOf(container)) expect(text).not.toMatch(/\d/);
    expect(container.querySelector("[data-testid='stretch-decision']")!.textContent).toBe("adopted");
  });

  it("the line on how far to trust the ranges says in plain sentences what the evidence is, and that it is thin", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const trust = container.querySelector("[data-testid='range-trust']")!.textContent!;
    expect(trust).toContain("Stretched by the model's own past misses, using what six-month forecasts needed.");
    expect(trust).toContain("Evidence at this length is thin: 1 past six-month forecast could be scored, and the stretched range did not hold it.");
    expect(trust).toContain("This window (Aug 31, 2026 to Jan 31, 2027) is not exactly the six-month forecast that was tested.");
    expect(trust).not.toContain("held 0 of 1");
    expect(trust).not.toContain("simulated range alone");
    expect(trust).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  it("a company whose stretch was not adopted keeps the simulated label and says so with the numbers", () => {
    for (const company of ["sprout-labs", "sapling-industries"]) {
      const c = caseOf(company, "as-signed");
      const container = mount(c, c.company, c.scenario);
      expect(c.report.backtest.candidates.ranges.decision).toBe("not adopted");
      expect(labelsOf(container)).toEqual(["simulated", "simulated, not separately tested"]);
      expect(container.querySelector("[data-testid='range-trust']")!.textContent).not.toContain("stretched");
      expect(container.querySelector("[data-testid='stretch-decision']")!.textContent).toBe("not adopted");
      expect(container.querySelector("[data-binding='stretch.reason']")!.textContent).toBe(c.report.backtest.candidates.ranges.reason);
      cleanup();
    }
  });

  it("a plan's ranges are the plan's, with the plan's label and no stretch claimed beside them", () => {
    const c = caseOf("mighty-oak-holdings", "demo-plan");
    const container = mount(c, c.company, c.scenario);
    expect(labelsOf(container)).toEqual([]);
    const plan = c.report.plan as Extract<NonNullable<TieoutReport["plan"]>, { items: unknown }>;
    expect(container.querySelector("[data-binding='bands.label']")!.textContent).toBe(plan.ranges.status);
    expect(container.querySelector("[data-testid='range-trust']")!.textContent).toContain("include the plan");
  });

  it("the evidence has a row for each tested horizon, with the two factors as the report gives them", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const rows = container.querySelectorAll("[data-testid='stretch-row']");
    expect(rows.length).toBe(3);
    const lower = Array.from(container.querySelectorAll("[data-binding='stretch.factor.lower']")).map((el) => el.textContent);
    expect(lower).toEqual(c.report.backtest.candidates.ranges.horizons.map((h) => fmt.multiple(h.lower_factor!)));
  });

  it("Mighty Oak's fourth quarter says in words, beside its range, that the lower edge was floored at zero", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const details = Array.from(container.querySelectorAll("[data-testid='quarter-detail']")).map((el) => el.textContent ?? "");
    const q4 = details.find((t) => t.includes("$0 to"));
    expect(q4).toBeDefined();
    expect(q4).toContain("Stretched on the low side by past misses; floored at zero");
    expect(container.querySelector("[data-testid='stretch-accepted']")!.textContent).toContain("floored at zero for: Q4FY26");
  });

  it("what the rule accepted and how the factors are chosen are on the page, and absent when nothing was adopted", () => {
    const adopted = caseOf("mighty-oak-holdings", "as-signed");
    const a = mount(adopted, adopted.company, adopted.scenario);
    expect(a.querySelector("[data-binding='stretch.accepted']")!.textContent).toContain("one-sided");
    expect(a.querySelector("[data-binding='stretch.method']")!.textContent).toContain("plain empirical rule, not a finite-sample guarantee");
    cleanup();
    const declined = caseOf("sprout-labs", "as-signed");
    const d = mount(declined, declined.company, declined.scenario);
    expect(d.querySelector("[data-binding='stretch.accepted']")).toBeNull();
    expect(d.querySelector("[data-binding='stretch.method']")!.textContent).toContain("noisier");
  });

  it("a factor with no finite value shows the report's reason on the page, not words of the browser's own", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const edited = structuredClone(c.report);
    const row = edited.backtest.candidates.ranges.horizons[1];
    row.upper_factor = null;
    row.upper_reason = "a reason the report gives";
    const container = mount({ ...c, report: edited }, c.company, c.scenario);
    const cells = container.querySelectorAll("[data-binding='stretch.factor.upper']");
    expect(cells[1].textContent).toBe("unavailable: a reason the report gives");
    expect(cells[1].getAttribute("data-unavailable")).toBe("true");
    expect(container.textContent).not.toContain("no width to stretch");
  });

  it("a label read from the wrong place is caught", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const original = B.rangeLabel80.path;
    (B.rangeLabel80 as { path: string }).path = B.rangeLabel95.path;
    try {
      const failures = allFailures(mount(c, c.company, c.scenario), c);
      expect(failures.some((f) => f.startsWith("year.range80.label"))).toBe(true);
    } finally {
      (B.rangeLabel80 as { path: string }).path = original;
    }
  });

  it("an evidence figure read from the wrong place is caught", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const original = STRETCH.coverageStretched.path;
    (STRETCH.coverageStretched as { path: string }).path = STRETCH.coverageSimulated.path;
    try {
      const failures = allFailures(mount(c, c.company, c.scenario), c);
      expect(failures.some((f) => f.startsWith("stretch.coverage.stretched"))).toBe(true);
    } finally {
      (STRETCH.coverageStretched as { path: string }).path = original;
    }
  });
});

describe("Forecast: tooltip content and expanded rows are held to the same rule", () => {
  it("a tooltip's rows read the file at each series' declared path, and its period label is the report's", () => {
    for (const [company, scenario, planned] of [["sapling-industries", "demo-plan", true], ["mighty-oak-holdings", "as-signed", false]] as const) {
      const r = files.report(company, scenario);
      const fitted = r.forecasts.methods.find((m) => m.method === "fitted model")!;
      const S = monthlySeries(planned);
      const specs = Object.values(S);
      const period = r.forecasts.windows[2];
      const keys = Object.keys(S).filter((k) => k !== "booked" && (planned || k !== "signed"));
      const { container } = render(
        <BindingProvider company={company} scenario={scenario} files={{ report: r, index: files.index(), comparison: files.comparison(company) }}>
          <ChartTooltip chartId="monthly" specs={specs} active label={period} payload={keys.map((k) => ({ dataKey: k, value: 1 }))} periodFormat={(p) => fmt.month(p)} />
        </BindingProvider>,
      );
      expect(unboundDigits(container, [fmt.month(period)])).toEqual([]);
      const text = (key: string) => container.querySelector(`[data-tooltip-row="${key}"] .font-medium`)?.textContent;
      expect(text("stage")).toBe(fmt.usdShort((r.forecasts.methods.find((m) => m.method === "stage-weighted pipeline")!.by_window as Record<string, string>)[period]));
      expect(text("runRate")).toBe(fmt.usdShort((r.forecasts.methods.find((m) => m.method === "trailing run-rate")!.by_window as Record<string, string>)[period]));
      const signed = (fitted.by_window as Record<string, string>)[period];
      expect(text(planned ? "signed" : "fitted")).toBe(fmt.usdShort(signed));
      cleanup();
    }
    void quarterSeries;
  });

  it("opening a quarter row shows its range, bound; a closed quarter has no toggle and says closed", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const { container } = render(
      <BindingProvider company={c.company} scenario={c.scenario} files={c}>
        <ForecastScreen />
      </BindingProvider>,
    );
    const quarters = c.report.gap.quarters;
    const closed = quarters.filter((q) => q.status === "closed").length;
    expect(closed).toBeGreaterThan(0);
    const toggles = container.querySelectorAll<HTMLButtonElement>("button[aria-label='Show the range of this quarter']");
    expect(toggles.length).toBe(quarters.length - closed);
    expect(container.querySelectorAll("[data-state='closed']").length).toBe(closed);
    expect(container.querySelectorAll("[data-binding='quarter.forecast']").length).toBe(quarters.length - closed);
    expect(container.querySelectorAll("[data-binding='quarter.range80.low']").length).toBe(0);
    fireEvent.click(toggles[0]);
    const open = quarters.filter((q) => q.status !== "closed")[0];
    expect(container.querySelector("[data-binding='quarter.range80.low']")!.textContent).toBe(fmt.usdShort(open.expected_range80![0]));
    expect(unboundDigits(container, [])).not.toContain("closed");
    fireEvent.click(toggles[0]);
    expect(container.querySelectorAll("[data-binding='quarter.range80.low']").length).toBe(0);
  });
});

describe("Forecast: a report that cannot forecast says so in words, never as zero", () => {
  it.each([["short-history.report.json", "as-signed"], ["short-history-plan.report.json", "demo-plan"]] as const)("%s", (name, scenario) => {
    const shown = { report: files.fixture(name), index: files.index(), comparison: files.comparison("sprout-labs") };
    const c: Case = { company: "sprout-labs", scenario, ...shown };
    const container = mount(shown, "sprout-labs", scenario);
    expect(allFailures(container, c)).toEqual([]);
    const text = container.textContent ?? "";
    expect(text).toContain("The fitted forecast is unavailable");
    expect(text).toMatch(/unavailable: /);
    for (const id of ["year.expected", "year.gap", "year.range80.low"]) {
      const el = container.querySelector(`[data-binding="${id}"]`)!;
      expect(el.getAttribute("data-unavailable")).toBe("true");
      expect(el.textContent).not.toMatch(/\$0/);
    }
    expect(container.querySelector("[data-testid='gap-badge']")).toBeNull();
  });
});

describe("Forecast: the checks fail when the screen is wrong (mutations)", () => {
  it("a swapped path is caught", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const original = SIGNED.yearExpected.path;
    (SIGNED.yearExpected as { path: string }).path = B.yearTarget.path;
    try {
      const failures = allFailures(mount(c, c.company, c.scenario), c);
      expect(failures.some((f) => f.startsWith("year.expected"))).toBe(true);
    } finally {
      (SIGNED.yearExpected as { path: string }).path = original;
    }
  });

  it("another company's file is caught", () => {
    const expected = caseOf("sapling-industries", "as-signed");
    const failures = allFailures(mount(caseOf("sprout-labs", "as-signed"), "sapling-industries", "as-signed"), expected);
    expect(failures.some((f) => f.startsWith("year.expected"))).toBe(true);
  });

  it("a flipped sign is caught, in the figures and in the badge", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const flipped = structuredClone(c.report);
    flipped.gap.fiscal_year.gap = `-${flipped.gap.fiscal_year.gap}` as never;
    flipped.gap.quarters[0].gap = (flipped.gap.quarters[0].gap!.startsWith("-") ? flipped.gap.quarters[0].gap!.slice(1) : `-${flipped.gap.quarters[0].gap}`) as never;
    const failures = allFailures(mount({ ...c, report: flipped }, c.company, c.scenario), c);
    expect(failures.some((f) => f.startsWith("year.gap"))).toBe(true);
    expect(failures.some((f) => f.startsWith("quarter.gap"))).toBe(true);
    expect(failures.some((f) => f.startsWith("gap badge"))).toBe(true);
  });

  it("a plan screen showing as-signed headline figures is caught", () => {
    const c = caseOf("sprout-labs", "demo-plan");
    const stripped = structuredClone(c.report);
    delete stripped.plan; // the screen then falls back to the as-signed view
    const failures = allFailures(mount({ ...c, report: stripped }, c.company, c.scenario), c);
    expect(failures.some((f) => f.startsWith("year.gap"))).toBe(true);
  });

  it("tampered provenance is caught: the path, the source, the format, the scenario and the company", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const container = mount(c, c.company, c.scenario);
    expect(allFailures(container, c)).toEqual([]);
    const el = container.querySelector("[data-binding='year.target']")!;
    for (const [attribute, value] of [["data-path", "/wrong"], ["data-source", "index"], ["data-format", "usd-full"], ["data-scenario", "nope"], ["data-company", "other"]] as const) {
      const was = el.getAttribute(attribute)!;
      el.setAttribute(attribute, value);
      expect(allFailures(container, c).some((f) => f.includes(attribute)), attribute).toBe(true);
      el.setAttribute(attribute, was);
    }
  });

  it("a digit outside any bound element is caught", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const stray = document.createElement("p");
    stray.textContent = "Revenue is up 12% on last year";
    container.appendChild(stray);
    expect(unboundDigits(container, [])).toEqual(["Revenue is up 12% on last year"]);
  });

  it("an exempt element may hold only what it is exempt for", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const label = document.createElement("div");
    label.setAttribute("data-exempt", "period-label");
    label.textContent = "Profit up 999%";
    container.appendChild(label);
    const axis = document.createElement("div");
    axis.className = "recharts-cartesian-axis";
    axis.innerHTML = "<text>Profit up 999%</text><text>$6.1M</text><text>Sep '26</text>";
    container.appendChild(axis);
    const found = unboundDigits(container, ["Sep 2026"]);
    expect(found).toHaveLength(2);
    expect(found.join("|")).toContain("Profit up 999%");
    label.textContent = "Sep 2026";
    expect(unboundDigits(container, ["Sep 2026"])).toHaveLength(1);
  });

  it("a bound element that is not on the committed list is caught", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const container = mount(c, c.company, c.scenario);
    const extra = document.createElement("span");
    extra.setAttribute("data-binding", "sneaky");
    container.appendChild(extra);
    expect(allFailures(container, c).some((f) => f.startsWith("sneaky"))).toBe(true);
  });
});
