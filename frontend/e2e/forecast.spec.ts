import { expect, test, type Page } from "@playwright/test";
import { month, usdShort } from "../src/screens/__tests__/independent";
import { BAD_TEXT, COMPANIES, SCENARIOS, collectBrowserIssues, unboundDigits } from "./support";

/**
 * Browser smoke for the report-backed app: every company and scenario on Forecast, and a phone-sized window. The checks are the ones a unit test cannot make:
 * a real page with a real console, charts that have drawn geometry, tooltips opened by hovering,
 * and no NaN, blank or unbound output. A report-backed zero ($0) is fine; "unavailable" is words.
 */

interface Report {
  forecasts: { windows: string[]; methods: Array<{ method: string; available: boolean; by_window: Record<string, string> }> };
  reconciliation: { bookings_by_month: Record<string, string> };
  gap: { quarters: Array<{ quarter: string; status: string; target: string; expected: string | null; expected_range80: [string, string] | null }> };
  plan?: { with_plan_by_window?: Record<string, string>; with_plan_quarters?: Array<{ quarter: string; status: string; expected: string; expected_range80: [string, string] }> };
}

async function reportOf(page: Page, company: string, scenario: string): Promise<Report> {
  return (await (await page.request.get(`/data/reports/${company}/${scenario}.json`)).json()) as Report;
}

function periodLabelsOf(r: Report): string[] {
  const months = new Set([...Object.keys(r.reconciliation.bookings_by_month), ...r.forecasts.windows]);
  return [...[...months].map(month), ...r.gap.quarters.map((q) => q.quarter)];
}

async function expectCleanPage(page: Page, label: string, periodLabels: string[] = []) {
  const text = (await page.locator("body").innerText()) ?? "";
  expect(text, `${label}: NaN, undefined or null on the page`).not.toMatch(BAD_TEXT);
  const empties = await page.evaluate(() =>
    Array.from(document.querySelectorAll("[data-binding]"))
      .filter((el) => !(el.textContent ?? "").trim())
      .map((el) => el.getAttribute("data-binding")),
  );
  expect(empties, `${label}: bound elements with no text`).toEqual([]);
  expect(await unboundDigits(page, periodLabels), `${label}: digits outside a bound element`).toEqual([]);
}

async function openForecast(page: Page, company: string, scenario: string) {
  const response = await page.goto(`/forecast?company=${company}&scenario=${scenario}`, { waitUntil: "networkidle" });
  expect(response?.ok(), `${company}/${scenario} HTTP ${response?.status()}`).toBe(true);
  await expect(page.locator("[data-chart='monthly'] svg.recharts-surface")).toBeVisible();
  await expect(page.locator("#company-selector")).toHaveValue(company);
  await expect(page.locator("#scenario-selector")).toHaveValue(scenario);
}

async function expectChartGeometry(page: Page, chart: string, parts: string[]) {
  const box = await page.locator(`[data-chart='${chart}'] svg.recharts-surface`).boundingBox();
  expect(box && box.width > 200 && box.height > 120, `${chart}: the chart has a size`).toBe(true);
  for (const part of parts) {
    const drawn = await page.locator(`[data-chart='${chart}'] ${part}`).evaluateAll((els) =>
      els.filter((el) => {
        const d = el.getAttribute("d");
        const r = el.getBoundingClientRect();
        return (d === null || d.length > 5) && r.width > 0 && r.height >= 0;
      }).length,
    );
    expect(drawn, `${chart}: ${part} is drawn`).toBeGreaterThan(0);
  }
}

/** The chart's y axis as pixels to dollars, read from its own tick labels and their positions. */
async function yScale(page: Page, chart: string): Promise<(pixel: number) => number> {
  const ticks = await page.locator(`[data-chart='${chart}'] .recharts-yAxis .recharts-cartesian-axis-tick`).evaluateAll((els) =>
    els.map((g) => ({ text: g.querySelector("text")?.textContent ?? "", y: Number(g.querySelector("text")?.getAttribute("y")) })),
  );
  const dollars = (t: string) => {
    const m = /^(-?)\$(\d+(?:\.\d+)?)([KM]?)$/.exec(t)!;
    return (m[1] ? -1 : 1) * Number(m[2]) * ({ "": 1, K: 1e3, M: 1e6 } as Record<string, number>)[m[3]];
  };
  const zero = ticks.find((t) => dollars(t.text) === 0)!;
  const top = ticks.reduce((a, b) => (dollars(b.text) > dollars(a.text) ? b : a));
  const perPixel = dollars(top.text) / (zero.y - top.y);
  return (pixel: number) => (zero.y - pixel) * perPixel;
}

/** Pixel coordinates of a path's vertices (a monotone line's segment ends), in the svg's own units. */
function vertices(d: string): Array<[number, number]> {
  const pairs = (d.match(/-?\d+(?:\.\d+)?(?:e-?\d+)?,-?\d+(?:\.\d+)?(?:e-?\d+)?/g) ?? []).map((p) => p.split(",").map(Number) as [number, number]);
  return pairs.filter((_, i) => i === 0 || i % 3 === 0);
}

const barCenters = (page: Page, chart: string) =>
  page.locator(`[data-chart='${chart}'] .recharts-bar-rectangle path`).evaluateAll((els) =>
    els.map((el) => {
      const b = (el as unknown as SVGGraphicsElement).getBBox();
      return { x: b.x + b.width / 2, top: b.y };
    }),
  );

/**
 * What is DRAWN equals what the file holds: every booked bar's top, and every point of the fitted line, maps
 * back through the chart's own axis to the bound value within a pixel and a half, and sits at its period's x.
 */
async function expectDrawnMatchesReport(page: Page, r: Report, planned: boolean, label: string) {
  const months = [...new Set([...Object.keys(r.reconciliation.bookings_by_month), ...r.forecasts.windows])].sort();
  const booked = Object.keys(r.reconciliation.bookings_by_month).sort();
  const toDollars = await yScale(page, "monthly");
  const tolerance = Math.abs(toDollars(0) - toDollars(1)) * 1.5 + 1;

  const bars = await barCenters(page, "monthly");
  expect(bars.length, `${label}: one bar per booked month`).toBe(booked.length);
  bars.forEach((bar, i) => {
    const want = Number(r.reconciliation.bookings_by_month[booked[i]]);
    expect(Math.abs(toDollars(bar.top) - want), `${label}: the ${booked[i]} bar maps to its booked value`).toBeLessThanOrEqual(tolerance);
  });
  const step = bars[1].x - bars[0].x;

  const lines = await page.locator("[data-chart='monthly'] .recharts-line .recharts-line-curve").evaluateAll((els) => els.map((el) => el.getAttribute("d") ?? ""));
  const fitted = r.forecasts.methods.find((m) => m.method === "fitted model")!;
  const wanted = (planned ? r.plan!.with_plan_by_window! : fitted.by_window) as Record<string, string>;
  const points = vertices(lines[planned ? 1 : 0]);
  expect(points.length, `${label}: the fitted line has a point per forecast month`).toBe(r.forecasts.windows.length);
  points.forEach(([x, y], k) => {
    const period = r.forecasts.windows[k];
    expect(Math.abs(x - (bars[0].x + months.indexOf(period) * step)), `${label}: ${period} point is at its month`).toBeLessThanOrEqual(2);
    expect(Math.abs(toDollars(y) - Number(wanted[period])), `${label}: ${period} point maps to its bound value`).toBeLessThanOrEqual(tolerance);
  });
}

/** Hover the chart at x (svg units) and return the tooltip's header and rows. */
async function hoverAt(page: Page, chart: string, x: number): Promise<{ header: string; rows: Array<[string, string]> }> {
  const wrapper = page.locator(`[data-chart='${chart}'] .recharts-wrapper`);
  await wrapper.scrollIntoViewIfNeeded();
  const box = (await wrapper.boundingBox())!;
  const svg = (await page.locator(`[data-chart='${chart}'] svg.recharts-surface`).boundingBox())!;
  await page.mouse.move(svg.x + x, box.y + box.height * 0.45);
  const tip = page.locator(`[data-testid='chart-tooltip'][data-chart='${chart}']`);
  await tip.waitFor({ state: "visible", timeout: 2000 });
  const header = (await tip.locator("[data-exempt='period-label']").innerText()).trim();
  const rows = await tip.locator("[data-tooltip-row]").evaluateAll((els) =>
    els.map((el) => [(el.children[0].textContent ?? "").trim(), (el.children[1].textContent ?? "").trim()] as [string, string]),
  );
  return { header, rows };
}

type Spread = { range80: [string, string]; range95: [string, string] };

/** Real hovering over the real charts: a historical month, a forecast month, and every quarter (closed and open). */
async function expectTooltipsMatchReport(page: Page, r: Report, spreads: Record<string, Spread>, planned: boolean, label: string, periodLabels: string[]) {
  const months = [...new Set([...Object.keys(r.reconciliation.bookings_by_month), ...r.forecasts.windows])].sort();
  const booked = Object.keys(r.reconciliation.bookings_by_month).sort();
  const bars = await barCenters(page, "monthly");
  const step = bars[1].x - bars[0].x;
  const method = (name: string) => r.forecasts.methods.find((m) => m.method === name)!;

  const past = booked[2];
  const hp = await hoverAt(page, "monthly", bars[0].x + months.indexOf(past) * step);
  expect(hp.header, `${label} ${past}`).toBe(month(past));
  expect(hp.rows, `${label} ${past}: only the booked figure`).toEqual([["Booked", usdShort(r.reconciliation.bookings_by_month[past])]]);

  const future = r.forecasts.windows[3];
  const hf = await hoverAt(page, "monthly", bars[0].x + months.indexOf(future) * step);
  const spread = spreads[future];
  const fittedValue = planned ? r.plan!.with_plan_by_window![future] : method("fitted model").by_window[future];
  const want: Array<[string, string]> = [
    ["95% range", `${usdShort(spread.range95[0])} to ${usdShort(spread.range95[1])}`],
    ["80% range", `${usdShort(spread.range80[0])} to ${usdShort(spread.range80[1])}`],
    ...(planned ? [["Fitted model, as signed", usdShort(method("fitted model").by_window[future])] as [string, string]] : []),
    [planned ? "Fitted model, with this scenario" : "Fitted model", usdShort(fittedValue)],
    ["Stage-weighted (point forecast, no range)", usdShort(method("stage-weighted pipeline").by_window[future])],
    ["Trailing run-rate (point forecast, no range)", usdShort(method("trailing run-rate").by_window[future])],
  ];
  expect(hf.header, `${label} ${future}`).toBe(month(future));
  expect(hf.rows, `${label} ${future}: every forecast, with its value`).toEqual(want);
  expect(await unboundDigits(page, periodLabels), `${label}: tooltip digits`).toEqual([]);

  const quarters = (planned ? r.plan!.with_plan_quarters! : r.gap.quarters) as Array<{ quarter: string; status: string; expected: string; expected_range80: [string, string] }>;
  const plot = (await page.locator("[data-chart='quarters'] .recharts-cartesian-grid").boundingBox())!;
  const svgBox = (await page.locator("[data-chart='quarters'] svg.recharts-surface").boundingBox())!;
  for (const [i, q] of quarters.entries()) {
    const h = await hoverAt(page, "quarters", plot.x - svgBox.x + (plot.width / quarters.length) * (i + 0.5));
    expect(h.header, `${label} ${q.quarter}`).toBe(q.quarter);
    expect(h.rows, `${label} ${q.quarter}`).toEqual([
      ["Expected (booked plus forecast)", usdShort(q.expected)],
      ...(q.status === "closed" ? [] : [["80% range", `${usdShort(q.expected_range80[0])} to ${usdShort(q.expected_range80[1])}`] as [string, string]]),
      ["Target", usdShort(r.gap.quarters[i].target)],
    ]);
  }
}

test.describe("Forecast, every company and scenario @smoke", () => {
  for (const company of COMPANIES) {
    for (const scenario of SCENARIOS) {
      test(`${company} / ${scenario} @smoke`, async ({ page }) => {
        const issues = collectBrowserIssues(page);
        await openForecast(page, company, scenario);

        await expectChartGeometry(page, "monthly", [".recharts-bar-rectangle path", ".recharts-line-curve", ".recharts-area-area"]);
        await expectChartGeometry(page, "quarters", [".recharts-bar-rectangle path", ".recharts-line-curve"]);
        const body = await reportOf(page, company, scenario);
        const r = body as Report & { forecasts: { fitted_ranges: { by_window: Record<string, Spread> } }; plan?: { ranges?: { by_window: Record<string, Spread> } } };
        const planned = r.plan !== undefined && !("unavailable" in r.plan);
        const spreads = planned ? r.plan!.ranges!.by_window : r.forecasts.fitted_ranges.by_window;
        const labels = periodLabelsOf(r);
        await expectCleanPage(page, `${company}/${scenario}`, labels);
        await expectDrawnMatchesReport(page, r, planned, `${company}/${scenario}`);

        // open what is closed: a quarter row, the range check
        await page.getByRole("button", { name: "Show the range of this quarter" }).first().click();
        await page.getByRole("button", { name: /How the ranges were checked/ }).click();
        await expect(page.getByTestId("quarter-detail")).toBeVisible();
        await expect(page.getByTestId("range-cell-row").first()).toBeVisible();
        await expectCleanPage(page, `${company}/${scenario} opened`, labels);

        await expectTooltipsMatchReport(page, r, spreads, planned, `${company}/${scenario}`, labels);
        expect(issues, `${company}/${scenario} console hygiene`).toEqual([]);
      });
    }
  }
});

test.describe("switching, and a phone @smoke", () => {
  test("choosing another company and scenario reloads the report and the URL follows @smoke", async ({ page }) => {
    const issues = collectBrowserIssues(page);
    await openForecast(page, "sprout-labs", "as-signed");
    await page.locator("#company-selector").selectOption("mighty-oak-holdings");
    await expect(page).toHaveURL(/company=mighty-oak-holdings/);
    await expect(page.locator("[data-binding='year.target']").first()).toHaveAttribute("data-company", "mighty-oak-holdings");
    await page.locator("#scenario-selector").selectOption("hires-only");
    await expect(page).toHaveURL(/scenario=hires-only/);
    await expect(page.locator("[data-binding='scenario.label']")).toHaveText("Hires only");
    await expectCleanPage(page, "after switching", periodLabelsOf(await reportOf(page, "mighty-oak-holdings", "hires-only")));
    expect(issues).toEqual([]);
  });

  test.describe("at phone width, with device emulation", () => {
    test.use({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
      userAgent:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    });

    for (const company of COMPANIES) {
      test(`${company}: nothing overflows sideways @smoke`, async ({ page }) => {
        const issues = collectBrowserIssues(page);
        await openForecast(page, company, "demo-plan");
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, "the page does not scroll sideways").toBeLessThanOrEqual(0);
        await expectChartGeometry(page, "monthly", [".recharts-bar-rectangle path", ".recharts-line-curve"]);
        await expectCleanPage(page, `${company} phone`, periodLabelsOf(await reportOf(page, company, "demo-plan")));
        const scrolling = await page.evaluate(() => Array.from(document.querySelectorAll(".overflow-x-auto")).filter((el) => el.scrollWidth > el.clientWidth + 1).length);
        expect(scrolling, "no table scrolls sideways inside its card").toBe(0);
        expect(issues).toEqual([]);
      });
    }
  });
});
