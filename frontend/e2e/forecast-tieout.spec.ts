import { expect, test, type Page } from "@playwright/test";

const VISUAL_ENABLED = process.env.VISUAL === "1";
const FIXED_BROWSER_TIME = new Date("2026-07-04T19:00:00-07:00");

const PERSONAS = [
  { id: "sprout-labs", label: "Sprout Labs" },
  { id: "sapling-industries", label: "Sapling Industries" },
  { id: "mighty-oak-holdings", label: "Mighty Oak Holdings" },
] as const;

const ROUTES = [
  { path: "/bookings", label: "Bookings Bridge", expectedCharts: 2 },
  { path: "/capacity", label: "Capacity & Headcount", expectedCharts: 2 },
  { path: "/funnel", label: "Funnel Health", expectedCharts: 0 },
  { path: "/inventory", label: "Pipeline Inventory", expectedCharts: 2 },
  { path: "/audit", label: "Audit", expectedCharts: 0 },
  { path: "/export", label: "Export Pack", expectedCharts: 0 },
  // Methodology is a prose/documentation page — no metric cards by design.
  { path: "/methodology", label: "Methodology", expectedCharts: 0, hasMetrics: false },
  { path: "/targets", label: "Target Setter", expectedCharts: 1 },
  { path: "/scenario", label: "Scenario Planner", expectedCharts: 2 },
] as const;

type PersonaCase = (typeof PERSONAS)[number];
type RouteCase = (typeof ROUTES)[number];

interface BrowserIssue {
  type: "error" | "warning" | "pageerror";
  text: string;
  location?: string;
}

interface ChartInspection {
  title: string;
  primarySeries: string;
  primaryValues: number[];
  hasSvg: boolean;
  hasGeometry: boolean;
  primaryHasData: boolean;
}

test.describe.configure({ mode: "parallel" });

test.describe("browser smoke @smoke", () => {
  for (const persona of PERSONAS) {
    for (const route of ROUTES) {
      test(`${persona.label} / ${route.label} @smoke`, async ({ page }) => {
        const issues = collectBrowserIssues(page);

        await openForecastPage(page, route, persona);

        await expectNoVisibleDegenerateText(page, route, persona);
        await expectHeadlineMetric(page, route, persona);
        await expectChartsToRender(page, route, persona);
        expect(formatBrowserIssues(issues), `${persona.id} ${route.path} console hygiene`).toEqual([]);
      });
    }
  }
});

if (VISUAL_ENABLED) {
  test.describe("visual regression @visual", () => {
    for (const persona of PERSONAS) {
      for (const route of ROUTES) {
        test(`${persona.label} / ${route.label} @visual`, async ({ page }) => {
          await openForecastPage(page, route, persona);

          await expect(page).toHaveScreenshot(screenshotName(route, persona), {
            animations: "disabled",
            fullPage: true,
            mask: [dataFreshnessChip(page)],
          });
        });
      }
    }
  });
}

async function openForecastPage(
  page: Page,
  route: RouteCase,
  persona: PersonaCase,
): Promise<void> {
  await page.clock.setFixedTime(FIXED_BROWSER_TIME);
  const response = await page.goto(`${route.path}?profile=${persona.id}`, {
    waitUntil: "networkidle",
  });

  expect(response?.ok(), `${persona.id} ${route.path} returned HTTP ${response?.status()}`).toBe(
    true,
  );
  await expect(page.locator("main")).toBeVisible();
  if (("hasMetrics" in route ? route.hasMetrics : true) !== false) {
    await expect(page.locator('[data-testid="metric-card"]').first()).toBeVisible();
  }
  await expect(page.locator("#org-profile-selector")).toHaveValue(persona.id);
}

function collectBrowserIssues(page: Page): BrowserIssue[] {
  const issues: BrowserIssue[] = [];

  page.on("console", (message) => {
    if (message.type() !== "error" && message.type() !== "warning") return;
    issues.push({
      type: message.type(),
      text: message.text(),
      location: formatConsoleLocation(message.location()),
    });
  });

  page.on("pageerror", (error) => {
    issues.push({ type: "pageerror", text: error.message });
  });

  return issues;
}

function formatConsoleLocation(location: {
  url: string;
  lineNumber: number;
  columnNumber: number;
}): string | undefined {
  if (!location.url) return undefined;
  return `${location.url}:${location.lineNumber}:${location.columnNumber}`;
}

function formatBrowserIssues(issues: BrowserIssue[]): string[] {
  return issues.map((issue) =>
    [issue.type, issue.text, issue.location].filter(Boolean).join(" | "),
  );
}

async function expectNoVisibleDegenerateText(
  page: Page,
  route: RouteCase,
  persona: PersonaCase,
): Promise<void> {
  const matches = await page.evaluate(() => {
    const text = document.body.innerText;
    const patterns = [
      { label: "$NaN", regex: /\$NaN/g },
      { label: "NaN", regex: /NaN/g },
      { label: "undefined", regex: /undefined/g },
      { label: "Infinity", regex: /Infinity/g },
      { label: "[object Object]", regex: /\[object Object\]/g },
      { label: "--", regex: /(^|[\s([{])--(?=$|[\s)\]},.;:])/g },
    ];

    const found = new Set<string>();
    for (const pattern of patterns) {
      for (const match of text.matchAll(pattern.regex)) {
        const index = match.index ?? 0;
        const context = text
          .slice(Math.max(0, index - 50), Math.min(text.length, index + 80))
          .replace(/\s+/g, " ")
          .trim();
        found.add(`${pattern.label}: ${context}`);
      }
    }
    return Array.from(found);
  });

  expect(matches, `${persona.id} ${route.path} visible degenerate text`).toEqual([]);
}

async function expectHeadlineMetric(
  page: Page,
  route: RouteCase,
  persona: PersonaCase,
): Promise<void> {
  if (("hasMetrics" in route ? route.hasMetrics : true) === false) return;
  const headline = page.locator('[data-testid="metric-card"]').first();
  const label = normalizeText(
    await headline.locator('[data-testid="metric-label"]').textContent(),
  );
  const value = normalizeText(
    await headline.locator('[data-testid="metric-value"]').textContent(),
  );

  expect(label, `${persona.id} ${route.path} headline metric label`).not.toBe("");
  expect(value, `${persona.id} ${route.path} headline metric value`).not.toBe("");
  expect(isDegenerateMetricValue(value), `${persona.id} ${route.path} ${label}`).toBe(false);
}

async function expectChartsToRender(
  page: Page,
  route: RouteCase,
  persona: PersonaCase,
): Promise<void> {
  const charts = await inspectCharts(page);
  expect(
    charts.map((chart) => chart.title),
    `${persona.id} ${route.path} chart count`,
  ).toHaveLength(route.expectedCharts);

  const failures = charts
    .filter((chart) => !chart.hasSvg || !chart.hasGeometry || !chart.primaryHasData)
    .map((chart) => ({
      title: chart.title,
      primarySeries: chart.primarySeries,
      primaryValues: chart.primaryValues,
      hasSvg: chart.hasSvg,
      hasGeometry: chart.hasGeometry,
      primaryHasData: chart.primaryHasData,
    }));

  expect(failures, `${persona.id} ${route.path} chart rendering`).toEqual([]);
}

async function inspectCharts(page: Page): Promise<ChartInspection[]> {
  return page.locator('[data-testid="chart-container"]').evaluateAll((nodes) =>
    nodes.map((node, index) => {
      const parsePrimaryValues = (raw: string): number[] => {
        try {
          const parsed = JSON.parse(raw) as unknown;
          if (!Array.isArray(parsed)) return [];
          return parsed.map((value) => (typeof value === "number" ? value : Number.NaN));
        } catch {
          return [];
        }
      };

      const geometryMagnitude = (element: Element): number => {
        const graphic = element as SVGGraphicsElement & {
          getTotalLength?: () => number;
        };

        let magnitude = 0;
        if (typeof graphic.getTotalLength === "function") {
          try {
            magnitude += graphic.getTotalLength();
          } catch {
            // Non-path SVG elements may expose getTotalLength but throw.
          }
        }

        if (typeof graphic.getBBox === "function") {
          try {
            const box = graphic.getBBox();
            magnitude += Math.abs(box.width) + Math.abs(box.height);
          } catch {
            // Hidden or detached SVG elements can throw; other candidates still count.
          }
        }

        if (element instanceof SVGRectElement) {
          magnitude +=
            Math.abs(element.width.baseVal.value) + Math.abs(element.height.baseVal.value);
        }

        return magnitude;
      };

      const hasDrawableGeometry = (container: Element): boolean => {
        const candidates = Array.from(container.querySelectorAll("svg path, svg rect"));
        return candidates.some((element) => {
          if (element.closest("defs, clipPath, mask")) return false;
          return geometryMagnitude(element) > 0;
        });
      };

      const primaryValues = parsePrimaryValues(
        node.getAttribute("data-primary-values") ?? "[]",
      );

      return {
        title: node.getAttribute("data-chart-title") ?? `chart #${index + 1}`,
        primarySeries: node.getAttribute("data-primary-series") ?? "",
        primaryValues,
        hasSvg: Boolean(node.querySelector("svg")),
        hasGeometry: hasDrawableGeometry(node),
        primaryHasData: primaryValues.some(
          (value) => Number.isFinite(value) && Math.abs(value) > 1e-9,
        ),
      };
    }),
  );
}

function normalizeText(value: string | null): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function isDegenerateMetricValue(value: string): boolean {
  return /^(\$0(?:\.0+)?[KMB]?|--|—|NaN|\$NaN|undefined|null|Infinity|\s*)$/i.test(value);
}

function screenshotName(route: RouteCase, persona: PersonaCase): string {
  return `${persona.id}-${slugify(route.label)}.png`;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function dataFreshnessChip(page: Page) {
  return page.locator("header").getByText(/^Data /);
}
