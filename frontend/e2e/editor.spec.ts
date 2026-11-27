import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { usdShort } from "../src/screens/__tests__/independent";
import { BAD_TEXT, COMPANIES, STRETCH, collectBrowserIssues, unboundDigits } from "./support";

/**
 * The plan editor in a real browser, against the built site: the same Python core, in a worker, computing the
 * visitor's plan. Most cases share one page (so Pyodide starts once); the cases that need a page of their own
 * (a phone, a blocked download) take one.
 */
type Plan = {
  hires: Array<{ segment: string; start: string; count: number }>;
  programs: Array<{ name: string; pipeline: number; start: string; cost?: number; ramp_months?: number }>;
};

// The committed demo plans (engine/config/profiles/<company>/plan.yaml), typed in through the form below.
const DEMO: Record<(typeof COMPANIES)[number], Plan> = {
  "sprout-labs": {
    hires: [
      { segment: "mid_market", start: "2026-10", count: 1 },
      { segment: "commercial", start: "2026-12", count: 1 },
    ],
    programs: [{ name: "Partner referrals", pipeline: 600000, start: "2026-10", ramp_months: 3 }],
  },
  "sapling-industries": {
    hires: [
      { segment: "mid_market", start: "2026-10", count: 2 },
      { segment: "enterprise", start: "2026-11", count: 1 },
    ],
    programs: [{ name: "Partner referrals", pipeline: 6000000, start: "2026-10", ramp_months: 3 }],
  },
  "mighty-oak-holdings": {
    hires: [
      { segment: "Mid-Market", start: "2026-10", count: 4 },
      { segment: "Enterprise", start: "2026-11", count: 2 },
    ],
    programs: [{ name: "Channel partner program", pipeline: 20000000, start: "2026-10", ramp_months: 3 }],
  },
};

const ROOT = resolve(import.meta.dirname, "..");
const committed = (company: string, scenario: string) => readFileSync(resolve(ROOT, `public/data/reports/${company}/${scenario}.json`), "utf8");
const fixture = (name: string) => readFileSync(resolve(ROOT, `src/screens/__tests__/fixtures/your-plan/${name}`), "utf8");

/** The committed demo-plan report as the browser's core must write it: only the report's identity and the plan's name differ. */
function asYourPlan(company: string): string {
  let text = committed(company, "demo-plan");
  for (const [from, to] of [
    ['"scenario": "demo-plan"', '"scenario": "your-plan"'],
    [`"file": "engine/config/profiles/${company}/plan.yaml"`, '"file": "your-plan"'],
  ]) {
    expect(text.split(from).length - 1, `${from} appears once in ${company}'s demo-plan.json`).toBe(1);
    text = text.replace(from, to);
  }
  return text;
}

/** Every report the worker hands the page, in order: the test's own record of what the browser's core wrote. */
const RECORD = `(() => {
  const Original = window.Worker;
  window.__reports = [];
  window.__requests = [];
  window.Worker = class extends Original {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (e) => { if (e.data && e.data.type === "applied" && e.data.report) window.__reports.push(e.data.report); });
    }
  };
})();`;

const reports = (page: Page) => page.evaluate(() => (window as unknown as { __reports: string[] }).__reports);
const lastReport = async (page: Page) => (await reports(page)).slice(-1)[0];

async function newPage(context: BrowserContext, search = "") {
  await context.addInitScript(RECORD);
  const page = await context.newPage();
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  await page.goto(`/plan?company=sapling-industries&scenario=as-signed${search}`, { waitUntil: "networkidle" });
  return { page, requests };
}

const editorRequests = (requests: string[]) => requests.filter((u) => /\/editor\/|pyodide/i.test(u));
const nav = (page: Page) => page.getByRole("navigation", { name: "Screens" });
const heading = (page: Page) => page.locator("main h2").first();

async function goTo(page: Page, screen: string) {
  await nav(page).getByRole("link", { name: screen }).click();
  await expect(heading(page)).toHaveText(screen);
}

async function enter(page: Page, plan: Plan) {
  for (const kind of ["hire", "program"]) {
    while ((await page.getByRole("button", { name: `Remove ${kind}` }).count()) > 0) await page.getByRole("button", { name: `Remove ${kind}` }).first().click();
  }
  for (const h of plan.hires) {
    await page.getByRole("button", { name: "Add a hire" }).click();
    const row = page.getByTestId("hire-row").last();
    await row.getByLabel("Segment").selectOption(h.segment);
    await row.getByLabel("How many").fill(String(h.count));
    await row.getByLabel("Starts").selectOption(h.start);
  }
  for (const p of plan.programs) {
    await page.getByRole("button", { name: "Add a program" }).click();
    const row = page.getByTestId("program-row").last();
    await row.getByLabel("Program name").fill(p.name);
    await row.getByLabel("Created pipeline").fill(String(p.pipeline));
    await row.getByLabel("Starts").selectOption(p.start);
    if (p.cost !== undefined) await row.getByLabel("Cost (optional)").fill(String(p.cost));
    if (p.ramp_months !== undefined) await row.getByLabel("Ramp in months (optional)").fill(String(p.ramp_months));
  }
}

async function apply(page: Page) {
  const before = (await reports(page)).length;
  await page.getByRole("button", { name: "Apply" }).click();
  await expect.poll(async () => (await reports(page)).length, { timeout: 60_000 }).toBe(before + 1);
  await expect(page.getByRole("button", { name: "Apply" })).toBeEnabled();
}

const sideways = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test.describe("the plan editor, one shared page @smoke", () => {
  test.describe.configure({ mode: "serial", timeout: 120_000 });
  let context: BrowserContext;
  let page: Page;
  let requests: string[];
  let issues: string[];
  const visited = new Set<string>(["sapling-industries"]);

  test.beforeAll(async ({ browser }, info) => {
    context = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: { width: 1440, height: 900 }, locale: "en-US", timezoneId: "America/Los_Angeles", colorScheme: "light", reducedMotion: "reduce" });
    ({ page, requests } = await newPage(context));
    issues = collectBrowserIssues(page);
  });
  test.afterAll(async () => {
    await context.close();
  });

  test("nothing of the editor is fetched until Your plan is opened, whichever screen or scenario is shown @smoke", async () => {
    for (const screen of ["Forecast", "Capacity", "Pipeline", "Trust", "Plan"]) {
      await goTo(page, screen);
      // the foot-of-screen links point at the editor without starting it; the Plan screen has the button and the notice instead
      if (screen !== "Plan") await expect(page.getByTestId("build-your-own").getByRole("link", { name: "Build your own plan" })).toBeVisible();
    }
    await expect(page.getByTestId("no-plan").getByRole("button", { name: "Build a plan" })).toBeVisible();
    for (const scenario of ["demo-plan", "hires-only", "as-signed"]) {
      await page.locator(`[data-scenario-id='${scenario}']`).click();
      await expect(page.locator(`[data-scenario-id='${scenario}']`)).toHaveAttribute("aria-pressed", "true");
    }
    expect(editorRequests(requests)).toEqual([]);
    await expect(page.getByRole("button", { name: "Edit plan", exact: true })).toBeVisible();
  });

  test("opening Your plan starts the core, shows the demo plan's figures as a report identical to the committed one, and marks the page @smoke", async () => {
    await page.getByRole("button", { name: "Edit plan", exact: true }).click();
    await expect(page.getByTestId("plan-form")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByTestId("plan-form").getByRole("heading", { name: "Your plan" })).toBeFocused();
    expect(await lastReport(page)).toBe(asYourPlan("sapling-industries"));
    await expect(page.getByTestId("your-plan-mark")).toHaveText("Your plan, computed in your browser; ranges unvalidated.");
    expect(editorRequests(requests).some((u) => u.includes("pyodide.asm.wasm"))).toBe(true);
    expect(editorRequests(requests).every((u) => new URL(u).origin === new URL(page.url()).origin), "nothing from another site").toBe(true);
  });

  for (const company of COMPANIES) {
    test(`${company}: the demo plan's items entered through the form give the committed demo-plan report, but for its name @smoke`, async () => {
      if ((await page.locator("#company-selector").inputValue()) !== company) {
        const seen = (await reports(page)).length;
        await page.locator("#company-selector").selectOption(company);
        await expect(page.locator("#scenario-selector")).toHaveValue("your-plan");
        await expect(page.getByTestId("plan-form")).toBeVisible({ timeout: 90_000 });
        if (!visited.has(company)) {
          expect((await reports(page)).length, "a company's first load computes its demo plan, once").toBe(seen + 1);
          expect(await lastReport(page), "the first load of a company is its demo plan").toBe(asYourPlan(company));
        }
      }
      visited.add(company);
      await enter(page, DEMO[company]);
      await apply(page);
      expect(await lastReport(page)).toBe(asYourPlan(company));
      await expect(page.getByTestId("plan-item-row")).toHaveCount(DEMO[company].hires.length + DEMO[company].programs.length);
    });
  }

  test("an edited plan equals a native run of the same plan, on the screen as well as in the report @smoke", async () => {
    await page.locator("#company-selector").selectOption("sapling-industries");
    await expect(page.getByTestId("plan-form")).toBeVisible({ timeout: 90_000 });
    const plan = JSON.parse(fixture("plan.json")) as Plan;
    await enter(page, plan);
    await apply(page);
    expect(await lastReport(page)).toBe(fixture("report.json"));
    const native = JSON.parse(fixture("report.json")) as { plan: { gap: { fiscal_year: { gap_with_plan: string } } } };
    await expect(page.locator("[data-binding='worksheet.summary.remaining-gap']")).toHaveText(usdShort(native.plan.gap.fiscal_year.gap_with_plan));
    await expect(page.locator("[data-binding='worksheet.summary.remaining-gap']")).toHaveAttribute("data-scenario", "your-plan");
    await expect(page.getByTestId("compare-row")).toHaveCount(5);
  });

  test("every screen shows the visitor's plan with the mark, and no digit outside a bound figure @smoke", async () => {
    for (const screen of ["Forecast", "Capacity", "Pipeline", "Trust", "Plan"]) {
      await goTo(page, screen);
      await expect(page.getByTestId("your-plan-mark")).toBeVisible();
      for (let pass = 0; pass < 4; pass++) await page.evaluate(() => document.querySelectorAll<HTMLElement>("[aria-expanded='false']").forEach((el) => el.click()));
      expect(await page.locator("body").innerText(), screen).not.toMatch(BAD_TEXT);
      expect(await page.locator("[data-binding]").evaluateAll((els) => els.filter((e) => !(e.textContent ?? "").trim()).length), `${screen}: empty bound elements`).toBe(0);
      const digits = await unboundDigits(page, periodLabelsOf(await lastReport(page)));
      expect(digits, `${screen}: digits outside a bound element`).toEqual([]);
    }
    expect(issues).toEqual([]);
  });

  test("the form keeps what was entered while the visitor looks at other screens @smoke", async () => {
    await goTo(page, "Plan");
    const before = await page.getByTestId("program-row").first().getByLabel("Created pipeline").inputValue();
    await goTo(page, "Forecast");
    await goTo(page, "Plan");
    expect(await page.getByTestId("program-row").first().getByLabel("Created pipeline").inputValue()).toBe(before);
  });

  test("the core's own words appear beside the field it refuses, and the last good figures stay @smoke", async () => {
    const shown = await page.locator("[data-binding='worksheet.summary.remaining-gap']").innerText();
    await page.getByTestId("hire-row").first().getByLabel("How many").fill("0");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByTestId("hire-row").first().getByRole("alert")).toContainText("count must be a whole number of at least 1");
    expect(await page.locator("[data-binding='worksheet.summary.remaining-gap']").innerText()).toBe(shown);
    await page.getByTestId("hire-row").first().getByLabel("How many").fill("1");
  });

  test("the Plan screen with the form open does not scroll sideways at desktop widths, even with the text spread; its tables stay tables @smoke", async () => {
    await goTo(page, "Plan");
    for (const width of [1024, 1280, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => document.fonts.ready);
      const style = await page.addStyleTag({ content: STRETCH });
      expect(await sideways(page), `${width}: the page does not scroll sideways`).toBeLessThanOrEqual(0);
      const scrolling = await page.evaluate(() => Array.from(document.querySelectorAll(".overflow-x-auto")).filter((el) => el.scrollWidth > el.clientWidth + 1).length);
      expect(scrolling, `${width}: no table scrolls sideways inside its card`).toBe(0);
      const wide = await page.evaluate(() =>
        Array.from(document.querySelectorAll("main *"))
          .filter((el) => el.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
          .map((el) => `${el.tagName}.${String(el.className).slice(0, 40)}`)
          .slice(0, 5),
      );
      expect(wide, `${width}: nothing runs past the right edge`).toEqual([]);
      await style.evaluate((el) => el.remove());
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    const stacked = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main table"))
        .filter((t) => getComputedStyle(t).display !== "table" || getComputedStyle(t.querySelector("thead")!).display !== "table-header-group")
        .map((t) => (t.textContent ?? "").slice(0, 40)),
    );
    expect(stacked, "no table on the page is laid out as stacked rows").toEqual([]);
  });

  test("choosing a named scenario leaves the worker warm and the plan is still there when the visitor comes back @smoke", async () => {
    const before = (await reports(page)).length;
    await page.locator("[data-scenario-id='demo-plan']").click();
    await expect(page.getByTestId("plan-form")).toHaveCount(0);
    await expect(page.getByTestId("your-plan-mark")).toHaveCount(0);
    await page.getByRole("button", { name: "Edit plan", exact: true }).click();
    await expect(page.getByTestId("plan-form")).toBeVisible();
    expect((await reports(page)).length, "no new computation to show what was applied").toBe(before);
    expect(await lastReport(page)).toBe(fixture("report.json"));
  });
});

/** The month and quarter labels a report names (the period labels a tooltip or an axis may show). */
function periodLabelsOf(text: string): string[] {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const out = new Set<string>();
  for (const m of text.match(/"\d{4}-\d{2}"/g) ?? []) {
    const [y, mm] = m.slice(1, -1).split("-");
    out.add(`${months[Number(mm) - 1]} '${y.slice(2)}`);
  }
  for (const q of text.match(/Q[1-4]FY\d{2}/g) ?? []) out.add(q);
  return [...out];
}

test.describe("a blocked download and a phone @smoke", () => {
  test("a blocked Pyodide download ends in the timeout state, and Try again works once it is unblocked @smoke", async ({ browser }, info) => {
    test.setTimeout(120_000);
    const context = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: { width: 1440, height: 900 } });
    const { page } = await newPage(context, "&editorTimeout=short");
    await page.route("**/pyodide.asm.wasm", (route) => route.abort());
    await page.getByRole("button", { name: "Edit plan", exact: true }).click();
    const status = page.getByTestId("session-status");
    await expect(status).toContainText("no answer within the time allowed", { timeout: 20_000 });
    await expect(status).toContainText("Choose another company or scenario");
    await page.unroute("**/pyodide.asm.wasm");
    await status.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByTestId("plan-form")).toBeVisible({ timeout: 90_000 });
    expect(await lastReport(page)).toBe(asYourPlan("sapling-industries"));
    await context.close();
  });

  test("a phone gets no editor: no choice, one line, and not a single request for Pyodide on any path @smoke", async ({ browser }, info) => {
    const context = await browser.newContext({
      baseURL: info.project.use.baseURL,
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
      userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    });
    const { page, requests } = await newPage(context);
    await expect(page.getByRole("button", { name: "Edit plan", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Add to plan" })).toHaveCount(0);
    await expect(page.getByTestId("worksheet-summary")).toContainText("Editing your own plan needs a larger screen.");
    await expect(page.locator("#scenario-selector option")).toHaveText(["As signed", "Demo plan", "Hires only", "Program only"]);
    for (const screen of ["forecast", "capacity", "pipeline", "plan", "trust"]) {
      await page.goto(`/${screen}?company=sapling-industries&scenario=your-plan`, { waitUntil: "networkidle" });
      await expect(page.getByText(/build your own plan/i), "no pointer to an editor that is not there").toHaveCount(0);
    }
    await expect(page.locator("#scenario-selector")).toHaveValue("as-signed");
    expect(editorRequests(requests)).toEqual([]);
    await context.close();
  });
});
