import { expect, test, type Page } from "@playwright/test";
import { month, quantity, usdShort } from "../src/screens/__tests__/independent";
import { BAD_TEXT, COMPANIES, collectBrowserIssues, unboundDigits } from "./support";

/**
 * Browser smoke for the screens beyond Forecast: Capacity, Pipeline, Plan and Trust for every company, as
 * signed and with the demo plan, with every expandable thing opened; chart geometry and real hovers; scenario
 * switching on Plan; and no sideways overflow on all five screens under phone device emulation.
 */
const NEW_SCREENS = ["capacity", "pipeline", "plan", "trust"] as const;
const ALL_SCREENS = ["forecast", ...NEW_SCREENS] as const;

type Json = Record<string, unknown>;
const reportOf = async (page: Page, company: string, scenario: string) =>
  (await (await page.request.get(`/data/reports/${company}/${scenario}.json`)).json()) as Json & {
    roster_capacity: { months?: Array<{ month: string; heads: number | string; ramped: string; headcount_target: number | null }> };
    required_pipeline: { quarters?: Array<{ quarter: string; expected_created_pipeline: string; required_extra_pipeline: string | null }> };
    plan?: { gap?: { fiscal_year?: { gap_with_plan: string } }; items?: unknown[] };
  };

/** Every month and quarter label the report itself names: the period labels a tooltip or an axis may show. */
function periodLabels(doc: unknown, out = new Set<string>()): string[] {
  if (typeof doc === "string") {
    if (/^\d{4}-\d{2}$/.test(doc)) out.add(month(doc));
    else if (/^Q[1-4]FY\d{2}$/.test(doc)) out.add(doc);
  } else if (Array.isArray(doc)) doc.forEach((d) => periodLabels(d, out));
  else if (doc && typeof doc === "object") {
    for (const [k, v] of Object.entries(doc)) {
      periodLabels(k, out);
      periodLabels(v, out);
    }
  }
  return [...out];
}

async function open(page: Page, screen: string, company: string, scenario: string) {
  const response = await page.goto(`/${screen}?company=${company}&scenario=${scenario}`, { waitUntil: "networkidle" });
  expect(response?.ok(), `${screen} ${company}/${scenario}`).toBe(true);
  await expect(page.locator("main h2").first()).toBeVisible();
  await expect(page.locator("#scenario-selector")).toHaveValue(scenario);
}

/** Click every collapsed row toggle and disclosure, until nothing is collapsed. */
async function openAll(page: Page) {
  for (let pass = 0; pass < 5; pass++) {
    const closed = await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll<HTMLElement>("[aria-expanded='false']"));
      els.forEach((el) => el.click());
      return els.length;
    });
    if (closed === 0) return;
    await page.waitForTimeout(50);
  }
}

async function expectClean(page: Page, label: string, labels: string[]) {
  const text = await page.locator("body").innerText();
  expect(text, `${label}: NaN, undefined or null on the page`).not.toMatch(BAD_TEXT);
  const empties = await page.evaluate(() =>
    Array.from(document.querySelectorAll("[data-binding]"))
      .filter((el) => !(el.textContent ?? "").trim())
      .map((el) => el.getAttribute("data-binding")),
  );
  expect(empties, `${label}: bound elements with no text`).toEqual([]);
  expect(await unboundDigits(page, labels), `${label}: digits outside a bound element`).toEqual([]);
}

async function drawn(page: Page, chart: string, parts: string[]) {
  const box = await page.locator(`[data-chart='${chart}'] svg.recharts-surface`).boundingBox();
  expect(box && box.width > 200 && box.height > 120, `${chart}: the chart has a size`).toBe(true);
  for (const part of parts) {
    const n = await page.locator(`[data-chart='${chart}'] ${part}`).evaluateAll((els) =>
      els.filter((el) => {
        const d = el.getAttribute("d");
        return (d === null || d.length > 5) && el.getBoundingClientRect().width > 0;
      }).length,
    );
    expect(n, `${chart}: ${part} is drawn`).toBeGreaterThan(0);
  }
}

test.describe("Capacity, Pipeline, Plan and Trust, every company @smoke", () => {
  for (const company of COMPANIES) {
    for (const scenario of ["as-signed", "demo-plan"] as const) {
      for (const screen of NEW_SCREENS) {
        test(`${screen}: ${company} / ${scenario} @smoke`, async ({ page }) => {
          const issues = collectBrowserIssues(page);
          const report = await reportOf(page, company, scenario);
          await open(page, screen, company, scenario);
          if (screen === "capacity") await drawn(page, "capacity-months", [".recharts-bar-rectangle path", ".recharts-line-curve"]);
          if (screen === "pipeline") await drawn(page, "pipeline-quarters", [".recharts-bar-rectangle path"]);
          await openAll(page);
          await expectClean(page, `${screen} ${company}/${scenario}`, periodLabels(report));
          expect(issues, `${screen} ${company}/${scenario} console hygiene`).toEqual([]);
        });
      }
    }
  }
});

test.describe("hovering the charts reads the report @smoke", () => {
  test("Capacity: each hover shows the report's heads, ramped equivalents and target for that month @smoke", async ({ page }) => {
    for (const company of COMPANIES) {
      const report = await reportOf(page, company, "as-signed");
      await open(page, "capacity", company, "as-signed");
      await page.locator("[data-testid='chart-container'][data-chart='capacity-months']").scrollIntoViewIfNeeded();
      const box = (await page.locator("[data-chart='capacity-months'] svg.recharts-surface").boundingBox())!;
      for (const fraction of [0.1, 0.4, 0.6, 0.9]) {
        await page.mouse.move(box.x + box.width * fraction, box.y + box.height / 2);
        const tooltip = page.getByTestId("chart-tooltip");
        await expect(tooltip).toBeVisible();
        const label = (await tooltip.locator("[data-exempt='period-label']").innerText()).trim();
        const row = report.roster_capacity.months!.find((m) => month(m.month) === label);
        expect(row, `${company}: ${label} is a month of the report`).toBeDefined();
        const read = async (key: string) => (await tooltip.locator(`[data-tooltip-row='${key}'] .font-medium`).count()) === 0 ? undefined : (await tooltip.locator(`[data-tooltip-row='${key}'] .font-medium`).innerText()).trim();
        expect(await read("heads")).toBe(quantity(row!.heads));
        expect(await read("ramped")).toBe(quantity(row!.ramped));
        expect(await read("target")).toBe(row!.headcount_target === null ? undefined : quantity(row!.headcount_target));
      }
    }
  });

  test("Pipeline: each hover shows the report's expected and required pipeline for that quarter @smoke", async ({ page }) => {
    for (const company of COMPANIES) {
      const report = await reportOf(page, company, "as-signed");
      await open(page, "pipeline", company, "as-signed");
      await page.locator("[data-testid='chart-container'][data-chart='pipeline-quarters']").scrollIntoViewIfNeeded();
      const box = (await page.locator("[data-chart='pipeline-quarters'] svg.recharts-surface").boundingBox())!;
      for (const fraction of [0.3, 0.8]) {
        await page.mouse.move(box.x + box.width * fraction - 5, box.y + box.height / 2);
        await page.mouse.move(box.x + box.width * fraction, box.y + box.height / 2);
        const tooltip = page.getByTestId("chart-tooltip");
        await expect(tooltip).toBeVisible();
        const label = (await tooltip.locator("[data-exempt='period-label']").innerText()).trim();
        const row = report.required_pipeline.quarters!.find((q) => q.quarter === label)!;
        expect(row, `${company}: ${label}`).toBeDefined();
        const read = async (key: string) => (await tooltip.locator(`[data-tooltip-row='${key}'] .font-medium`).count()) === 0 ? undefined : (await tooltip.locator(`[data-tooltip-row='${key}'] .font-medium`).innerText()).trim();
        expect(await read("expected")).toBe(usdShort(row.expected_created_pipeline));
        expect(await read("required")).toBe(row.required_extra_pipeline === null ? undefined : usdShort(row.required_extra_pipeline));
      }
    }
  });
});

test.describe("Plan: switching scenario @smoke", () => {
  test("picking a scenario on the page reloads the report, moves the URL and the whole screen @smoke", async ({ page }) => {
    const issues = collectBrowserIssues(page);
    await open(page, "plan", "sapling-industries", "as-signed");
    await expect(page.getByTestId("no-plan")).toContainText("There is no plan in this scenario");
    for (const scenario of ["demo-plan", "hires-only", "program-only"] as const) {
      await page.locator(`[data-scenario-id='${scenario}']`).click();
      await expect(page).toHaveURL(new RegExp(`scenario=${scenario}`));
      await expect(page.locator(`[data-scenario-id='${scenario}']`)).toHaveAttribute("aria-pressed", "true");
      const report = await reportOf(page, "sapling-industries", scenario);
      await expect(page.locator("[data-binding='plan.gap']")).toHaveText(usdShort(report.plan!.gap!.fiscal_year!.gap_with_plan));
      await expect(page.locator("[data-binding='plan.gap']")).toHaveAttribute("data-scenario", scenario);
      await expect(page.getByTestId("plan-item-row")).toHaveCount(report.plan!.items!.length);
    }
    await page.locator("[data-scenario-id='as-signed']").click();
    await expect(page.getByTestId("no-plan")).toBeVisible();
    expect(issues).toEqual([]);
  });
});

test.describe("at phone width, with device emulation @smoke", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });

  // No font is relied on: the page must fit as shipped, and again with a deliberately wide fallback face
  // and extra letter spacing, so whether a web font has loaded can never decide the result.
  const FONTS = {
    "as shipped": "",
    "a wide fallback font": `* { font-family: Verdana, "DejaVu Sans", sans-serif !important; letter-spacing: 0.04em !important; }`,
  } as const;
  for (const [fontName, css] of Object.entries(FONTS)) {
    for (const company of COMPANIES) {
      for (const screen of ALL_SCREENS) {
        test(`${screen}: ${company} does not scroll sideways in ${fontName}, opened or closed @smoke`, async ({ page }) => {
          const issues = collectBrowserIssues(page);
          await open(page, screen, company, "demo-plan");
          if (css) await page.addStyleTag({ content: css });
          const sideways = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          expect(await sideways(), "the page does not scroll sideways").toBeLessThanOrEqual(0);
          await openAll(page);
          expect(await sideways(), "nor with everything opened").toBeLessThanOrEqual(0);
          const scrolling = await page.evaluate(() => Array.from(document.querySelectorAll(".overflow-x-auto")).filter((el) => el.scrollWidth > el.clientWidth + 1).length);
          expect(scrolling, "no table scrolls sideways inside its card").toBe(0);
          const wide = await page.evaluate(() =>
            Array.from(document.querySelectorAll("main *"))
              .filter((el) => el.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
              .map((el) => `${el.tagName}.${String(el.className).slice(0, 40)}`)
              .slice(0, 5),
          );
          expect(wide, "nothing in the page runs past the right edge").toEqual([]);
          expect(issues).toEqual([]);
        });
      }
    }
  }
});

test.describe("at tablet widths, with a wide fallback font @smoke", () => {
  for (const width of [768, 1024]) {
    test.describe(`${width} wide`, () => {
      test.use({ viewport: { width, height: 900 } });
      for (const company of COMPANIES) {
        for (const screen of ["forecast", "trust"] as const) {
          test(`${screen}: ${company} does not scroll sideways @smoke`, async ({ page }) => {
            await open(page, screen, company, "demo-plan");
            await page.addStyleTag({ content: `* { font-family: Verdana, "DejaVu Sans", sans-serif !important; letter-spacing: 0.04em !important; }` });
            await openAll(page);
            const sideways = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
            expect(sideways, "the page does not scroll sideways").toBeLessThanOrEqual(0);
            const scrolling = await page.evaluate(() => Array.from(document.querySelectorAll(".overflow-x-auto")).filter((el) => el.scrollWidth > el.clientWidth + 1).length);
            expect(scrolling, "no table scrolls sideways inside its card").toBe(0);
          });
        }
      }
    });
  }
});

test.describe("the old app's addresses @smoke", () => {
  const MOVED = [
    ["/bookings", "/forecast"],
    ["/scenario", "/plan"],
    ["/targets", "/plan"],
    ["/inventory", "/pipeline"],
    ["/funnel", "/pipeline"],
    ["/audit", "/trust"],
    ["/methodology", "/trust"],
    ["/export", "/trust"],
    ["/capacity", "/capacity"],
  ] as const;

  for (const [from, to] of MOVED) {
    test(`${from} lands on ${to} with the company kept`, async ({ page }) => {
      const issues = collectBrowserIssues(page);
      await page.goto(`${from}?profile=sprout-labs`, { waitUntil: "networkidle" });
      await expect(page.locator("main h2").first()).toBeVisible();
      const url = new URL(page.url());
      expect(url.pathname).toBe(to);
      expect(url.searchParams.get("company")).toBe("sprout-labs");
      expect(url.searchParams.has("profile")).toBe(false);
      await expect(page.locator("#company-selector")).toHaveValue("sprout-labs");
      expect(issues).toEqual([]);
    });
  }
});
