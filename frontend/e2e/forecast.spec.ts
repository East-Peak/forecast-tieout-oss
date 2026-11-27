import { expect, test, type Page } from "@playwright/test";

/**
 * Browser smoke for the report-backed app: every company and scenario on Forecast, the four
 * screens not built yet, and a phone-sized window. The checks are the ones a unit test cannot make:
 * a real page with a real console, charts that have drawn geometry, tooltips opened by hovering,
 * and no NaN, blank or unbound output. A report-backed zero ($0) is fine; "unavailable" is words.
 */
const COMPANIES = ["sprout-labs", "sapling-industries", "mighty-oak-holdings"] as const;
const SCENARIOS = ["as-signed", "demo-plan", "hires-only", "programme-only"] as const;
const PLACEHOLDERS = ["capacity", "pipeline", "plan", "trust"] as const;
const BAD_TEXT = /\bNaN\b|\bundefined\b|\[object|\bInfinity\b|\bnull\b/;

function collectBrowserIssues(page: Page): string[] {
  const issues: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") issues.push(`${m.type()}: ${m.text()}`);
  });
  page.on("pageerror", (e) => issues.push(`pageerror: ${e.message}`));
  page.on("response", (r) => {
    if (r.status() >= 400) issues.push(`HTTP ${r.status()}: ${r.url()}`);
  });
  return issues;
}

/** Text nodes with a digit that sit in no bound element, no chart axis and no period label (see harness.ts for the stated exceptions). */
async function unboundDigits(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      if (!el || ["SCRIPT", "STYLE"].includes(el.tagName)) continue;
      if (el.closest("[data-binding], .recharts-cartesian-axis, [data-exempt='period-label'], #recharts_measurement_span")) continue;
      let text = node.textContent ?? "";
      text = text.split("80% range").join("").split("95% range").join("");
      if (/\d/.test(text)) out.push(text.trim());
    }
    return out;
  });
}

async function expectCleanPage(page: Page, label: string) {
  const text = (await page.locator("body").innerText()) ?? "";
  expect(text, `${label}: NaN, undefined or null on the page`).not.toMatch(BAD_TEXT);
  const empties = await page.evaluate(() =>
    Array.from(document.querySelectorAll("[data-binding]"))
      .filter((el) => !(el.textContent ?? "").trim())
      .map((el) => el.getAttribute("data-binding")),
  );
  expect(empties, `${label}: bound elements with no text`).toEqual([]);
  expect(await unboundDigits(page), `${label}: digits outside a bound element`).toEqual([]);
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

async function hoverCharts(page: Page, label: string) {
  for (const chart of ["monthly", "quarters"]) {
    const area = page.locator(`[data-chart='${chart}'] .recharts-wrapper`);
    await area.scrollIntoViewIfNeeded();
    const box = (await area.boundingBox())!;
    let opened = 0;
    for (const share of [0.12, 0.3, 0.5, 0.7, 0.88]) {
      await page.mouse.move(box.x + box.width * share, box.y + box.height * 0.5);
      const tip = page.locator(`[data-testid='chart-tooltip'][data-chart='${chart}']`);
      await tip.waitFor({ state: "visible", timeout: 1500 }).catch(() => undefined);
      if (await tip.isVisible()) {
        opened += 1;
        const text = await tip.innerText();
        expect(text, `${label} ${chart} tooltip`).not.toMatch(BAD_TEXT);
        expect(await unboundDigits(page), `${label} ${chart} tooltip: digits outside a bound element`).toEqual([]);
      }
    }
    expect(opened, `${label}: the ${chart} chart shows a tooltip when hovered`).toBeGreaterThan(0);
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
        await expectCleanPage(page, `${company}/${scenario}`);

        // open what is closed: a quarter row, the range check
        await page.getByRole("button", { name: "Show the range of this quarter" }).first().click();
        await page.getByRole("button", { name: /How the ranges were checked/ }).click();
        await expect(page.getByTestId("quarter-detail")).toBeVisible();
        await expect(page.getByTestId("range-cell-row").first()).toBeVisible();
        await expectCleanPage(page, `${company}/${scenario} opened`);

        await hoverCharts(page, `${company}/${scenario}`);
        expect(issues, `${company}/${scenario} console hygiene`).toEqual([]);
      });
    }
  }
});

test.describe("the screens not built yet @smoke", () => {
  for (const screen of PLACEHOLDERS) {
    test(`${screen} says so and shows no numbers @smoke`, async ({ page }) => {
      const issues = collectBrowserIssues(page);
      await page.goto(`/${screen}?company=sapling-industries&scenario=as-signed`, { waitUntil: "networkidle" });
      await expect(page.getByTestId("not-built")).toContainText("Not built yet");
      expect(await page.locator("main").innerText()).not.toMatch(/\d/);
      expect(issues).toEqual([]);
    });
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
    await expectCleanPage(page, "after switching");
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
        await expectCleanPage(page, `${company} phone`);
        expect(issues).toEqual([]);
      });
    }
  });
});
