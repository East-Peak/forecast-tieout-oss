import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { percentText } from "../src/editor/percent";
import { decimal2, percent1, usdShort } from "../src/screens/__tests__/independent";
import { BAD_TEXT, COMPANIES, STRETCH, collectBrowserIssues, unboundDigits } from "./support";

/**
 * The plan editor in a real browser, against the built site: the same Python core, in a worker, computing the
 * visitor's plan. Most cases share one page (so Pyodide starts once); the cases that need a page of their own
 * (a phone, a blocked download) take one.
 */
type Driver = "win_rate" | "won_arr" | "productivity";
type Action = { id: string; name: string; driver: Driver; slice: string; start: string; ramp_months: number; target: string };
type Plan = {
  hires: Array<{ segment: string; start: string; count: number }>;
  programs: Array<{ name: string; pipeline: number; start: string; cost?: number; ramp_months?: number }>;
  actions?: Action[];
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
/** The as-signed lanes as committed: what the grid must not show for a plan whose lanes are the edited ones, and whose goals and actuals it must. */
type LanesFile = { periods: Array<{ key: string; rows: Array<{ path: string[]; cells: Record<string, { forecast: string | null; goal: string | null; actual: string | null }> }> }> };
type OwnersFile = LanesFile;
const signedLanes = (company = "sapling-industries") => JSON.parse(readFileSync(resolve(ROOT, `public/data/reports/${company}/lanes-as-signed.json`), "utf8")) as LanesFile;
const fixture = (name: string, dir = "your-plan") => readFileSync(resolve(ROOT, `src/screens/__tests__/fixtures/${dir}/${name}`), "utf8");
/** The core's own output for the same plan with a win-rate action on Enterprise: its report, its grid. */
const withActions = (name: string) => fixture(name, "your-plan-actions");
/** The form gives an action an id of its own ("action-0", "action-1", in the order they are added); the fixture's is named for what it is. */
const FIXTURE_ACTION_IDS = ["enterprise-win-rate", "company-deal-size", "mid-market-creation"];
const asFormIds = (text: string, ids: string[] = FIXTURE_ACTION_IDS.slice(0, 1)) =>
  ids.reduce((made, id, i) => {
    expect(made.split(`"${id}"`).length - 1, "the fixture names its action once or more").toBeGreaterThan(0);
    return made.split(`"${id}"`).join(`"action-${i}"`);
  }, text);

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
  window.__lanes = [];
  window.__requests = [];
  window.Worker = class extends Original {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (e) => {
        if (e.data && e.data.type === "applied" && e.data.report) window.__reports.push(e.data.report);
        if (e.data && e.data.type === "lanes") window.__lanes.push(e.data.lanes);
      });
    }
    postMessage(m, ...rest) {
      if (m && m.type === "apply") window.__requests.push(m.plan);
      return super.postMessage(m, ...rest);
    }
  };
})();`;

const reports = (page: Page) => page.evaluate(() => (window as unknown as { __reports: string[] }).__reports);
/** Every answer the worker gave to a request for lanes, in order, as JSON text: what the browser's core wrote for each Apply's grid. */
const lanesAnswers = (page: Page) => page.evaluate(() => (window as unknown as { __lanes: string[] }).__lanes);
const lastReport = async (page: Page) => (await reports(page)).slice(-1)[0];
/** The plan of the last Apply the page sent to the worker, as the worker received it. */
const lastRequestedPlan = async (page: Page) => JSON.parse(((await page.evaluate(() => (window as unknown as { __requests: string[] }).__requests)).slice(-1)[0]) ?? "null") as Plan | null;

/** The items the form holds right now, read from its fields, in the form of `describe`. */
const formItems = (page: Page) =>
  page.evaluate(() => ({
    hires: Array.from(document.querySelectorAll("[data-testid='hire-row']")).map((r) => Array.from(r.querySelectorAll("select, input")).map((e) => (e as HTMLInputElement).value).join("/")),
    programs: Array.from(document.querySelectorAll("[data-testid='program-row']")).map((r) => Array.from(r.querySelectorAll("input")).map((e) => (e as HTMLInputElement).value).join("/")),
    actions: Array.from(document.querySelectorAll("[data-testid='action-row']")).map((r) => Array.from(r.querySelectorAll("select, input")).map((e) => (e as HTMLInputElement).value).join("/")),
  }));
const describe_ = (plan: Plan) => ({
  hires: plan.hires.map((h) => `${h.segment}/${h.count}/${h.start}`),
  programs: plan.programs.map((p) => `${p.name}/${p.pipeline}/${p.cost ?? ""}/${p.ramp_months ?? ""}`),
  actions: (plan.actions ?? []).map((a) => `${a.name}/${a.driver}/${a.slice}/${a.start}/${a.ramp_months}/${a.driver === "win_rate" ? percentText(a.target) : a.target}`),
});
/** The plan as the form will send it: each action under the id the form gives it. */
const asSent = (plan: Plan): Plan => ({ ...plan, actions: (plan.actions ?? []).map((a, i) => ({ ...a, id: `action-${i}` })) });

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

/**
 * Show a company's form the way a visitor waits for it: the old company's form is still on screen when the selector
 * changes (and is gone for a moment while the new one loads), so "a form is visible" proves nothing; the screen itself
 * must be the new company's.
 */
async function switchCompany(page: Page, company: string) {
  await page.locator("#company-selector").selectOption(company);
  await expect(page.locator("#scenario-selector")).toHaveValue("your-plan");
  await expect(page.locator("main [data-binding]").first()).toHaveAttribute("data-company", company, { timeout: 90_000 });
  await expect(page.getByTestId("plan-form")).toBeVisible({ timeout: 90_000 });
}

/** Empty the form through its own buttons, one row at a time, waiting for each row to go before the next click. */
async function clearForm(page: Page) {
  for (const kind of ["hire", "program", "action"] as const) {
    const rows = page.getByTestId(`${kind}-row`);
    for (let left = await rows.count(); left > 0; left--) {
      await page.getByRole("button", { name: `Remove ${kind}`, exact: true }).first().click();
      await expect(rows).toHaveCount(left - 1);
    }
  }
}

/** Set the form to exactly `plan`, and say so: a form that holds anything else fails here, naming what it holds. */
async function enter(page: Page, plan: Plan) {
  await expect(page.getByTestId("plan-form")).toBeVisible();
  await clearForm(page);
  expect(await formItems(page), "the form is empty before the plan is entered").toEqual({ hires: [], programs: [], actions: [] });
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
  for (const a of plan.actions ?? []) await addAction(page, a);
  expect(await formItems(page), "the form holds exactly the plan about to be applied").toEqual(describe_(plan));
}

/** What the form calls each driver's target field. */
const TARGET_LABEL: Record<Driver, string> = { win_rate: "Target win rate (percent)", won_arr: "Target won ARR per win (dollars)", productivity: "Target creation productivity (deals)" };
const DRIVER_CHOICE: Record<Driver, string> = { win_rate: "Win rate", won_arr: "Won ARR per win", productivity: "Creation productivity" };

/** Add an action through the form's own fields: the form picks the driver and slice it starts on, and the visitor sets the rest. */
async function addAction(page: Page, given: Omit<Action, "id" | "driver"> & { driver?: Driver }) {
  const a = { driver: "win_rate" as Driver, ...given };
  const rows = page.getByTestId("action-row");
  const before = await rows.count();
  await page.getByRole("button", { name: "Add an action" }).click();
  await expect(rows).toHaveCount(before + 1);
  const row = rows.last();
  await row.getByLabel("Changes").selectOption(a.driver);
  await row.getByLabel("Action name").fill(a.name);
  await row.getByLabel("Slice").selectOption(a.slice);
  await row.getByLabel("Starts").selectOption(a.start);
  await row.getByLabel("Ramp in months (zero is immediate)").fill(String(a.ramp_months));
  await row.getByLabel(TARGET_LABEL[a.driver]).fill(a.driver === "win_rate" ? percentText(a.target) : a.target);
}

async function apply(page: Page, plan?: Plan) {
  const before = (await reports(page)).length;
  await page.getByRole("button", { name: "Apply" }).click();
  await expect.poll(async () => (await reports(page)).length, { timeout: 60_000 }).toBe(before + 1);
  await expect(page.getByRole("button", { name: "Apply" })).toBeEnabled();
  // what the worker was asked to compute is the plan that was meant, so a wrong plan fails here in a line, not as a diff of two reports
  if (plan) expect(await lastRequestedPlan(page), "the plan sent to the core is the plan entered").toEqual(plan.actions ? asSent(plan) : plan);
}

const sideways = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** The Plan screen at the desktop widths, with the text spread: nothing scrolls sideways or runs past the edge, and its tables stay tables. */
async function fitsAtDesktopWidths(page: Page) {
  for (const width of [1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => document.fonts.ready);
    const style = await page.addStyleTag({ content: STRETCH });
    expect(await sideways(page), `${width}: the page does not scroll sideways`).toBeLessThanOrEqual(0);
    const scrolling = await page.evaluate(() => Array.from(document.querySelectorAll(".overflow-x-auto")).filter((el) => !el.matches("[data-testid='grid-scroll']") && el.scrollWidth > el.clientWidth + 1).length);
    expect(scrolling, `${width}: no table scrolls sideways inside its card`).toBe(0);
    const wide = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .filter((el) => !el.closest("[data-testid='grid-scroll']") && el.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
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
}

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
        await switchCompany(page, company);
        if (!visited.has(company)) {
          expect((await reports(page)).length, "a company's first load computes its demo plan, once").toBe(seen + 1);
          expect(await lastReport(page), "the first load of a company is its demo plan").toBe(asYourPlan(company));
        }
      }
      visited.add(company);
      await enter(page, DEMO[company]);
      await apply(page, DEMO[company]);
      expect(await lastReport(page)).toBe(asYourPlan(company));
      await expect(page.getByTestId("plan-item-row")).toHaveCount(DEMO[company].hires.length + DEMO[company].programs.length);
    });
  }

  test("an edited plan equals a native run of the same plan, on the screen as well as in the report @smoke", async () => {
    await switchCompany(page, "sapling-industries");
    const plan = JSON.parse(fixture("plan.json")) as Plan;
    await enter(page, plan);
    await apply(page, plan);
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

  test("on Plan the grid shows the edited plan's lanes: the company's forecast is the edited report's expected bookings, a goal is as signed, and the as-signed forecast is never shown for it @smoke", async () => {
    await goTo(page, "Plan");
    const edited = JSON.parse(fixture("report.json")) as { plan: { expected_fiscal_year: string } };
    const signed = signedLanes();
    const forecast = page.locator("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.forecast']");
    // wait on content only the edited plan's lanes can show: the as-signed forecast is a different figure, and "pending" has none
    await expect(forecast).toHaveText(usdShort(edited.plan.expected_fiscal_year), { timeout: 60_000 });
    expect(usdShort(signed.periods[0].rows[0].cells.bookings.forecast!), "the edit moves the forecast").not.toBe(usdShort(edited.plan.expected_fiscal_year));
    await expect(forecast).toHaveAttribute("data-scenario", "your-plan");
    await expect(page.getByTestId("cell-total-bookings").locator("[data-binding='lanes.bookings.goal']")).toHaveText(usdShort(signed.periods[0].rows[0].cells.bookings.goal!));
    await expect(page.getByTestId("your-plan-note")).toHaveCount(0);
    await expect(page.getByTestId("lanes-pending")).toHaveCount(0);
    await expect(page.getByTestId("forecast-pending")).toHaveCount(0);
    // the browser's core wrote, for this Apply, exactly the lanes and owners a native run of the plan wrote (the fixture is checked against one by the generator's --verify)
    const answer = JSON.parse((await lanesAnswers(page)).slice(-1)[0]) as { stale: boolean; problems: string[]; lanes: unknown; owners: Record<string, unknown> };
    expect(answer.stale).toBe(false);
    expect(answer.problems).toEqual([]);
    expect(answer.lanes).toEqual(JSON.parse(fixture("lanes.json")));
    expect(answer.owners.enterprise).toEqual(JSON.parse(fixture("owners-enterprise.json")));
    expect(answer.owners.commercial).toEqual(JSON.parse(fixture("owners-commercial.json")));
    // a quarter, from the file the native run wrote: the grid is that file's, not just its first figure
    const native = JSON.parse(fixture("lanes.json")) as LanesFile;
    await page.getByTestId("period-Q4FY26").click();
    await expect(page.locator("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.forecast']")).toHaveText(usdShort(native.periods[4].rows[0].cells.bookings.forecast!));
    await page.getByTestId("period-FY26").click();
  });

  test("a segment opens to the edited plan's owners, the planned hires' bucket among them, from the worker and not from a file @smoke", async () => {
    const fetched: string[] = [];
    const note = (r: { url(): string }) => fetched.push(r.url());
    page.on("request", note);
    await page.getByTestId("expand-segment/enterprise").click();
    const bucket = page.getByTestId("cell-segment/enterprise/owner/planned-hires-bookings");
    await expect(bucket).toBeVisible();
    const owners = JSON.parse(fixture("owners-enterprise.json")) as OwnersFile;
    const hires = owners.periods[0].rows.find((r) => r.path.at(-1) === "planned-hires")!;
    await expect(bucket.locator("[data-binding='owners.bookings.forecast']")).toHaveText(usdShort(hires.cells.bookings.forecast!));
    page.off("request", note);
    expect(fetched.filter((u) => u.includes("lanes-owners")), "no owners file is fetched for your plan").toEqual([]);
    await page.getByTestId("expand-segment/enterprise").click();
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
    await fitsAtDesktopWidths(page);
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

  test("another company's grid shows its own plan's lanes, and coming back shows this company's edited ones, never another's or the as-signed @smoke", async () => {
    const forecast = (company: string) => page.locator(`[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.forecast'][data-company='${company}']`);
    const demoOf = (company: string) => usdShort((JSON.parse(readFileSync(resolve(ROOT, `public/data/reports/${company}/lanes-demo-plan.json`), "utf8")) as LanesFile).periods[0].rows[0].cells.bookings.forecast!);
    const editedBookings = usdShort((JSON.parse(fixture("lanes.json")) as LanesFile).periods[0].rows[0].cells.bookings.forecast!);
    await goTo(page, "Plan");
    await switchCompany(page, "sprout-labs");
    // the content that proves the new state: a figure drawn for sprout-labs, whose plan is its demo plan until edited
    await expect(forecast("sprout-labs")).toHaveText(demoOf("sprout-labs"), { timeout: 60_000 });
    await expect(page.locator("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.forecast'][data-company='sapling-industries']")).toHaveCount(0);
    expect(demoOf("sprout-labs")).not.toBe(editedBookings);
    await switchCompany(page, "sapling-industries");
    await expect(forecast("sapling-industries")).toHaveText(editedBookings, { timeout: 60_000 });
    expect(editedBookings).not.toBe(usdShort(signedLanes().periods[0].rows[0].cells.bookings.forecast!));
    await expect(page.getByTestId("forecast-pending")).toHaveCount(0);
  });

  // ---- win-rate actions: the same page, the same worker, in this order (each test starts from what the one before left) ----

  const ENTERPRISE_PUSH = JSON.parse(withActions("plan.json")) as Plan;
  const driverActions = (report: string) => JSON.parse(report).driver_actions as {
    items: Array<{ id: string; name: string; driver: Driver; removal_value: Record<string, string>; evidence: { change_points: string; resulting_rate: string; baseline: string; change_percent: string; resulting: string; label: string; position: string } }>;
    joint_gain: Record<string, string>;
    with_actions: { expected_fiscal_year: string; bookings: Record<string, string> };
    without_actions: { expected_fiscal_year: string; bookings: Record<string, string> };
    reconciliation: { values: Record<string, string>; material: Record<string, boolean>; sentences: Record<string, string> };
  };
  const REST = "rest of fiscal year";
  const TWELVE = "next twelve months";
  const actionRows = (p: Page) => p.getByTestId("action-row");
  const bound = (p: Page, id: string) => p.locator(`[data-binding='${id}']`);

  test("a segment action entered through the form gives the core's own report, the Actions block says its values, and the bridge has its joint step @smoke", async () => {
    await switchCompany(page, "sapling-industries");
    await enter(page, ENTERPRISE_PUSH);
    await apply(page, ENTERPRISE_PUSH);
    // the browser's core wrote the native run's report, but for the id the form gave the action
    expect(await lastReport(page)).toBe(asFormIds(withActions("report.json")));
    const native = driverActions(withActions("report.json"));
    // wait on content only this Apply can show: the block, with the removal value of the action
    await expect(bound(page, "driver-actions.item.removal.rest")).toHaveText(usdShort(native.items[0].removal_value[REST]), { timeout: 30_000 });
    await expect(bound(page, "driver-actions.item.removal.next12")).toHaveText(usdShort(native.items[0].removal_value[TWELVE]));
    await expect(bound(page, "driver-actions.joint.rest")).toHaveText(usdShort(native.joint_gain[REST]));
    await expect(bound(page, "driver-actions.joint.next12")).toHaveText(usdShort(native.joint_gain[TWELVE]));
    await expect(bound(page, "driver-actions.with.year")).toHaveText(usdShort(native.with_actions.expected_fiscal_year));
    await expect(bound(page, "driver-actions.without.year")).toHaveText(usdShort(native.without_actions.expected_fiscal_year));
    await expect(bound(page, "driver-actions.without.next12")).toHaveText(usdShort(native.without_actions.bookings[TWELVE]));
    await expect(bound(page, "driver-actions.removal-label").first()).toHaveText("Bookings lost if removed");
    // no interaction between actions here: the reconciliation line is not said
    await expect(page.getByTestId("driver-actions-reconciliation")).toHaveCount(0);
    // beside the target: the core's change in points and resulting rate for this action as applied, and its label, in its words
    const row = actionRows(page).first();
    await expect(row.locator("[data-binding='driver-actions.item.change-points']")).toHaveText(decimal2(native.items[0].evidence.change_points));
    await expect(row.locator("[data-binding='driver-actions.item.resulting']")).toHaveText(percent1(native.items[0].evidence.resulting_rate));
    await expect(row.locator("[data-binding='driver-actions.item.label']")).toHaveText("outside the worksheet's historical settings");
    await expect(row.locator("[data-binding='driver-actions.form.baseline']")).toBeVisible();
    // the bridge: its steps are the report's, the joint actions step among them
    await expect(page.locator("[data-testid='bridge-row'][data-kind='actions']")).toHaveCount(1);
    await expect(page.getByTestId("plan-item-row")).toHaveCount(4);
    // win rate "needed alone" is not solved under actions: the core's sentence stands in its place
    await expect(page.getByTestId("needed-stacked")).toContainText("no setting is solved for");
    const digits = await unboundDigits(page, periodLabelsOf(await lastReport(page)));
    expect(digits, "digits outside a bound element").toEqual([]);
    await fitsAtDesktopWidths(page);
    expect(issues).toEqual([]);
  });

  test("the grid under the action: the browser's core wrote the native run's lanes, the action's segment forecasts a different win rate and the others do not @smoke", async () => {
    const native = JSON.parse(withActions("lanes.json")) as LanesFile;
    const signed = signedLanes();
    const rate = (lanes: LanesFile, lane: string) => lanes.periods[0].rows.find((r) => r.path.join("/") === (lane === "total" ? lane : `segment/${lane}`))!.cells.win_rate.forecast!;
    const forecast = (segment: string) => page.locator(`[data-testid='cell-segment/${segment}-win_rate'] [data-binding='lanes.win_rate.forecast']`);
    // wait on the edited plan's own figure for the action's segment: the as-signed rate is a different one
    await expect(forecast("enterprise")).toHaveText(percent1(rate(native, "enterprise")), { timeout: 60_000 });
    // the worker's answer for this Apply, read once the grid shows it (the answer comes after the report)
    const answer = JSON.parse((await lanesAnswers(page)).slice(-1)[0]) as { stale: boolean; problems: string[]; lanes: unknown; owners: Record<string, unknown> };
    expect(answer.stale).toBe(false);
    expect(answer.problems).toEqual([]);
    expect(answer.lanes).toEqual(JSON.parse(withActions("lanes.json")));
    expect(answer.owners.enterprise).toEqual(JSON.parse(withActions("owners-enterprise.json")));
    expect(percent1(rate(signed, "enterprise")), "the action moves the segment's forecast").not.toBe(percent1(rate(native, "enterprise")));
    for (const other of ["mid_market", "commercial"]) {
      await expect(forecast(other)).toHaveText(percent1(rate(signed, other)));
      expect(rate(native, other), `${other} is not touched`).toBe(rate(signed, other));
    }
    await expect(page.locator("[data-testid='cell-total-win_rate'] [data-binding='lanes.win_rate.forecast']")).toHaveText(percent1(rate(native, "total")));
    // its panel says what the core says about a win-rate action, and offers to plan another
    await page.getByTestId("cell-segment/enterprise-win_rate").click();
    await expect(page.getByTestId("panel-actions-caveat")).toContainText("entered change to a pooled rate");
    await page.getByRole("button", { name: "Close panel" }).click();
  });

  test("Add to plan on the win-rate bar opens a draft company action at the worksheet's favorable end, and applies nothing @smoke", async () => {
    const applied = (await reports(page)).length;
    const high = (JSON.parse(withActions("report.json")) as { worksheet: { drivers: Array<{ driver: string; historical: { high: { setting: string } } }> } }).worksheet.drivers.find((d) => d.driver === "win_rate")!.historical.high.setting;
    const drivers = page.locator("[data-testid='driver-row']");
    await expect(page.locator("[data-testid='driver-row'][data-driver='cycle_days'] button", { hasText: "Add to plan" }), "the cycle bar has no button").toHaveCount(0);
    expect(await drivers.evaluateAll((els) => els.map((e) => e.getAttribute("data-driver")).sort())).toEqual(["cycle_days", "productivity", "win_rate", "won_arr"]);
    await page.locator("[data-testid='driver-row'][data-driver='win_rate']").getByRole("button", { name: "Add to plan" }).click();
    await expect(actionRows(page)).toHaveCount(2);
    const draft = actionRows(page).last();
    await expect(draft.getByLabel("Slice")).toHaveValue("company");
    await expect(draft.getByLabel("Starts")).toHaveValue("2026-09");
    await expect(draft.getByLabel("Ramp in months (zero is immediate)")).toHaveValue("0");
    await expect(draft.getByLabel("Target win rate (percent)")).toHaveValue(percentText(high));
    await expect(draft.getByTestId("action-origin")).toContainText("will differ from the bar's figure");
    await expect(draft.getByTestId("action-origin")).toContainText("immediate company-wide change from the as-of date");
    await expect(draft.getByLabel("Action name")).toBeFocused();
    await expect(page.getByTestId("plan-unapplied")).toBeVisible();
    expect((await reports(page)).length, "nothing was computed for the draft").toBe(applied);
    await draft.getByRole("button", { name: "Remove action" }).click();
    await expect(actionRows(page)).toHaveCount(1);
  });

  test("Plan an action here, on a segment's win-rate cell, opens a draft with that slice and the pooled baseline as its target, and applies nothing @smoke", async () => {
    const applied = (await reports(page)).length;
    const baseline = (JSON.parse(withActions("report.json")) as { worksheet: { drivers: Array<{ driver: string; current: { value: string } }> } }).worksheet.drivers.find((d) => d.driver === "win_rate")!.current.value;
    const cellNumber = (JSON.parse(withActions("lanes.json")) as LanesFile).periods[0].rows.find((r) => r.path.join("/") === "segment/mid_market")!.cells.win_rate.actual!;
    await page.getByTestId("cell-segment/mid_market-win_rate").click();
    const entry = page.getByTestId("plan-action");
    await expect(entry).toContainText("dated cohort rate");
    await entry.getByRole("button", { name: "Plan an action here" }).click();
    await expect(actionRows(page)).toHaveCount(2);
    const draft = actionRows(page).last();
    await expect(draft.getByLabel("Slice")).toHaveValue("mid_market");
    await expect(draft.getByLabel("Target win rate (percent)")).toHaveValue(percentText(baseline));
    expect(percentText(baseline), "the cell's own number is not the target").not.toBe(percentText(cellNumber));
    await expect(draft.getByTestId("action-origin")).toContainText("pooled baseline");
    await expect(page.getByTestId("cell-panel"), "the panel steps aside").toHaveCount(0);
    await expect(page.getByTestId("plan-unapplied")).toBeVisible();
    expect((await reports(page)).length, "nothing was computed for the draft").toBe(applied);
    // not offered on an owner's rate, nor on another column
    await page.getByTestId("expand-segment/enterprise").click();
    await page.getByTestId("cell-segment/enterprise/owner/AE-010-win_rate").click();
    await expect(page.getByTestId("cell-panel")).toBeVisible();
    await expect(page.getByTestId("plan-action")).toHaveCount(0);
    await page.getByTestId("cell-segment/enterprise-bookings").click();
    await expect(page.getByTestId("plan-action")).toHaveCount(0);
    await page.getByRole("button", { name: "Close panel" }).click();
    await page.getByTestId("expand-segment/enterprise").click();
    await draft.getByRole("button", { name: "Remove action" }).click();
    await expect(actionRows(page)).toHaveCount(1);
  });

  test("a company action replaces the segment's, and the block says the worker's own values; an overlapping action is refused beside the item in the core's words @smoke", async () => {
    await actionRows(page).first().getByRole("button", { name: "Remove action" }).click();
    await expect(actionRows(page)).toHaveCount(0);
    await addAction(page, { name: "Company win-rate push", slice: "company", start: "2026-10", ramp_months: 0, target: "0.2300" });
    await apply(page);
    const report = await lastReport(page);
    const mine = driverActions(report);
    expect(mine.items).toHaveLength(1);
    await expect(bound(page, "driver-actions.item.removal.rest")).toHaveText(usdShort(mine.items[0].removal_value[REST]), { timeout: 30_000 });
    await expect(bound(page, "driver-actions.item.removal.next12")).toHaveText(usdShort(mine.items[0].removal_value[TWELVE]));
    await expect(bound(page, "driver-actions.joint.next12")).toHaveText(usdShort(mine.joint_gain[TWELVE]));
    await expect(bound(page, "driver-actions.with.next12")).toHaveText(usdShort(mine.with_actions.bookings[TWELVE]));
    await expect(bound(page, "driver-actions.without.year")).toHaveText(usdShort(mine.without_actions.expected_fiscal_year));
    await expect(bound(page, "driver-actions.item.change-points")).toHaveText(decimal2(mine.items[0].evidence.change_points));
    expect(mine.items[0].evidence.position, "23 percent is above the worksheet's high").toBe("above");
    await expect(bound(page, "driver-actions.item.label")).toHaveText(mine.items[0].evidence.label);
    // the gain is the company's: the three segments' win-rate forecasts all moved, none by the segment's alone
    const shown = await page.locator("[data-testid='driver-actions-joint'] [data-binding='driver-actions.joint.rest']").innerText();
    // a second action on a segment overlaps the company's: refused, with the last good figures left as they were
    await page.getByRole("button", { name: "Add an action" }).click();
    await expect(actionRows(page)).toHaveCount(2);
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(actionRows(page).last().getByRole("alert")).toContainText("Overlaps 'Company win-rate push'", { timeout: 30_000 });
    await expect(actionRows(page).last().getByRole("alert")).toContainText("so the change would be counted twice");
    await expect(actionRows(page).last().getByRole("alert")).not.toContainText(/actions\[|win_rate/);
    await expect(actionRows(page).first().getByRole("alert")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Apply" })).toBeEnabled();
    expect(await page.locator("[data-testid='driver-actions-joint'] [data-binding='driver-actions.joint.rest']").innerText(), "the last good figures stay").toBe(shown);
    await actionRows(page).last().getByRole("button", { name: "Remove action" }).click();
    await expect(actionRows(page)).toHaveCount(1);
  });

  test("two actions on two segments: the block lists both with their values, and the reconciliation line is the core's @smoke", async () => {
    await actionRows(page).first().getByRole("button", { name: "Remove action" }).click();
    await addAction(page, { name: "Enterprise push", slice: "enterprise", start: "2026-10", ramp_months: 2, target: "0.2600" });
    await addAction(page, { name: "Commercial push", slice: "commercial", start: "2026-11", ramp_months: 3, target: "0.2400" });
    await apply(page);
    const mine = driverActions(await lastReport(page));
    expect(mine.items).toHaveLength(2);
    await expect(page.getByTestId("driver-action-row")).toHaveCount(2, { timeout: 30_000 });
    await expect(bound(page, "driver-actions.item.removal.next12").nth(0)).toHaveText(usdShort(mine.items[0].removal_value[TWELVE]));
    await expect(bound(page, "driver-actions.item.removal.next12").nth(1)).toHaveText(usdShort(mine.items[1].removal_value[TWELVE]));
    await expect(bound(page, "driver-actions.joint.next12")).toHaveText(usdShort(mine.joint_gain[TWELVE]));
    // the reconciliation line is said for a window only where the core calls its figure material (a residue that rounds to zero is not said)
    for (const [window, id] of [[REST, "rest"], [TWELVE, "next12"]] as const) {
      await expect(bound(page, `driver-actions.reconciliation.${id}`)).toHaveCount(mine.reconciliation.material[window] ? 1 : 0);
    }
    expect(await unboundDigits(page, periodLabelsOf(await lastReport(page)))).toEqual([]);
  });

  // ---- the size of a win and creation: one action each through the form, then all three, then the entry points ----

  const PLAIN = JSON.parse(fixture("plan.json")) as Plan;
  const THREE = JSON.parse(fixture("plan.json", "your-plan-three-drivers")) as Plan;
  const withDrivers = (name: string) => fixture(name, "your-plan-three-drivers");
  const sizeAction = (over: Partial<Action> = {}): Action => ({ id: "x", name: "Company deal size", driver: "won_arr", slice: "company", start: "2026-10", ramp_months: 1, target: "450000", ...over });
  const creationAction = (over: Partial<Action> = {}): Action => ({ id: "x", name: "Mid Market creation", driver: "productivity", slice: "mid_market", start: "2026-11", ramp_months: 2, target: "2.6", ...over });
  const worksheetRow = (report: string, driver: Driver) =>
    (JSON.parse(report) as { worksheet: { drivers: Array<{ driver: string; unit_label: string; current: { value: string }; historical: { low: { setting: string }; high: { setting: string } } }> } }).worksheet.drivers.find((d) => d.driver === driver)!;

  test("a won-ARR action entered through the form: the Actions block says the core's figures, the evidence line the core's percent and label, and the bridge has its joint step @smoke", async () => {
    const plan = { ...PLAIN, actions: [sizeAction()] };
    await enter(page, plan);
    await apply(page, plan);
    const report = await lastReport(page);
    const mine = driverActions(report);
    expect(mine.items).toHaveLength(1);
    expect(mine.items[0].removal_value, "one action: what removing it loses is the joint gain").toEqual(mine.joint_gain);
    await expect(bound(page, "driver-actions.item.removal.rest")).toHaveText(usdShort(mine.items[0].removal_value[REST]), { timeout: 30_000 });
    await expect(bound(page, "driver-actions.joint.rest")).toHaveText(usdShort(mine.joint_gain[REST]));
    await expect(bound(page, "driver-actions.joint.next12")).toHaveText(usdShort(mine.joint_gain[TWELVE]));
    await expect(page.getByTestId("driver-action-driver")).toHaveText(DRIVER_CHOICE.won_arr);
    const row = actionRows(page).first();
    const sheet = worksheetRow(report, "won_arr");
    await expect(row.getByLabel("Changes")).toHaveValue("won_arr");
    await expect(row.locator("[data-binding='driver-actions.form.won_arr.baseline']")).toHaveText(usdShort(sheet.current.value));
    await expect(row.locator("[data-binding='driver-actions.form.won_arr.low']")).toHaveText(usdShort(sheet.historical.low.setting));
    await expect(row.locator("[data-binding='driver-actions.form.won_arr.unit']")).toHaveText("dollars of ARR per won deal");
    await expect(row.locator("[data-binding='driver-actions.item.change-percent']")).toHaveText(decimal2(mine.items[0].evidence.change_percent));
    await expect(row.locator("[data-binding='driver-actions.item.resulting.won_arr']")).toHaveText(usdShort(mine.items[0].evidence.resulting));
    expect(mine.items[0].evidence.position).toBe("inside");
    await expect(row.locator("[data-binding='driver-actions.item.label']")).toHaveCount(0);
    await expect(page.locator("[data-testid='bridge-row'][data-kind='actions']")).toHaveCount(1);
    // a size action does not stack on any other driver's flex: the win rate is still solved for
    await expect(page.getByTestId("needed-stacked")).toHaveCount(0);
    expect(await unboundDigits(page, periodLabelsOf(report))).toEqual([]);
    expect(issues).toEqual([]);
  });

  test("a creation-productivity action entered through the form says its unit from the report, and the core's percent and label @smoke", async () => {
    const plan = { ...PLAIN, actions: [creationAction()] };
    const created = page.locator("[data-testid='cell-segment/mid_market-created'] [data-binding='lanes.created.forecast']");
    await expect(created).toBeVisible({ timeout: 60_000 });
    const createdBefore = await created.innerText();
    await enter(page, plan);
    await apply(page, plan);
    const report = await lastReport(page);
    const mine = driverActions(report);
    expect(mine.items[0].removal_value).toEqual(mine.joint_gain);
    await expect(bound(page, "driver-actions.item.removal.next12")).toHaveText(usdShort(mine.items[0].removal_value[TWELVE]), { timeout: 30_000 });
    await expect(bound(page, "driver-actions.joint.rest")).toHaveText(usdShort(mine.joint_gain[REST]));
    const row = actionRows(page).first();
    const sheet = worksheetRow(report, "productivity");
    expect(sheet.unit_label, "Sapling's capacity term is in use").toBe("created deals per ramped AE-month");
    await expect(row.locator("[data-binding='driver-actions.form.productivity.unit']")).toHaveText(sheet.unit_label);
    await expect(row.locator("[data-binding='driver-actions.form.productivity.baseline']")).toHaveText(decimal2(sheet.current.value));
    await expect(row.locator("[data-binding='driver-actions.item.change-percent']")).toHaveText(decimal2(mine.items[0].evidence.change_percent));
    await expect(row.locator("[data-binding='driver-actions.item.resulting.productivity']")).toHaveText(decimal2(mine.items[0].evidence.resulting));
    expect(mine.items[0].evidence.position).toBe("above");
    await expect(row.locator("[data-binding='driver-actions.item.label']")).toHaveText("outside the worksheet's historical settings");
    // the grid follows: Mid Market is expected to create more deals than under the size action before it
    await expect(created).not.toHaveText(createdBefore, { timeout: 60_000 });
    expect(Number((await created.innerText()).replace(/,/g, ""))).toBeGreaterThan(Number(createdBefore.replace(/,/g, "")));
    expect(await unboundDigits(page, periodLabelsOf(report))).toEqual([]);
    expect(issues).toEqual([]);
  });

  test("an action on each driver entered through the form gives the native run's report, the block lists all three, and the material reconciliation line is the core's, with its sentence @smoke", async () => {
    await enter(page, THREE);
    await apply(page, THREE);
    expect(await lastReport(page)).toBe(asFormIds(withDrivers("report.json"), FIXTURE_ACTION_IDS));
    const mine = driverActions(withDrivers("report.json"));
    await expect(page.getByTestId("driver-action-row")).toHaveCount(3, { timeout: 30_000 });
    await expect(page.getByTestId("driver-action-driver")).toHaveText([DRIVER_CHOICE.win_rate, DRIVER_CHOICE.won_arr, DRIVER_CHOICE.productivity]);
    for (const [i, item] of mine.items.entries()) {
      await expect(bound(page, "driver-actions.item.removal.next12").nth(i)).toHaveText(usdShort(item.removal_value[TWELVE]));
    }
    await expect(bound(page, "driver-actions.joint.next12")).toHaveText(usdShort(mine.joint_gain[TWELVE]));
    expect(mine.reconciliation.material).toEqual({ [REST]: true, [TWELVE]: true });
    await expect(page.getByTestId("driver-actions-reconciliation")).toBeVisible();
    await expect(bound(page, "driver-actions.reconciliation.rest")).toHaveText(usdShort(mine.reconciliation.values[REST]));
    await expect(bound(page, "driver-actions.reconciliation.next12")).toHaveText(usdShort(mine.reconciliation.values[TWELVE]));
    await expect(bound(page, "driver-actions.reconciliation.sentence.rest")).toHaveText(mine.reconciliation.sentences[REST]);
    await expect(bound(page, "driver-actions.reconciliation.sentence.next12")).toHaveText(mine.reconciliation.sentences[TWELVE]);
    expect(Number(mine.reconciliation.values[REST])).toBeLessThan(0);
    // the native run's grid: Mid Market's creation and Enterprise's win rate are the file's
    const lanes = JSON.parse(withDrivers("lanes.json")) as LanesFile;
    const cell = (path: string, column: string) => lanes.periods[0].rows.find((r) => r.path.join("/") === path)!.cells[column].forecast!;
    await expect(page.locator("[data-testid='cell-segment/mid_market-avg_won_arr'] [data-binding='lanes.avg_won_arr.forecast']")).toHaveText(usdShort(cell("segment/mid_market", "avg_won_arr")), { timeout: 60_000 });
    await expect(page.locator("[data-testid='cell-segment/enterprise-win_rate'] [data-binding='lanes.win_rate.forecast']")).toHaveText(percent1(cell("segment/enterprise", "win_rate")));
    if (process.env.SCREENSHOTS) {
      // an element capture scrolls it under the page's sticky header: let the header sit where it is in the flow for the capture
      await page.addStyleTag({ content: ".sticky, [class*='sticky'] { position: static !important; }" });
      await page.getByTestId("plan-form").screenshot({ path: `${process.env.SCREENSHOTS}/form-three-drivers.png` });
      await page.getByTestId("driver-actions").screenshot({ path: `${process.env.SCREENSHOTS}/results-material-reconciliation.png` });
      await page.getByTestId("driver-row").first().locator("xpath=ancestor::*[contains(@class,'rounded')][1]").screenshot({ path: `${process.env.SCREENSHOTS}/tornado.png` });
    }
    expect(await unboundDigits(page, periodLabelsOf(await lastReport(page)))).toEqual([]);
    expect(issues).toEqual([]);
  });

  test("a second action on the same driver and slice is refused beside the item in the core's words, with the last good figures left, while another driver on that slice is not @smoke", async () => {
    const shown = await page.locator("[data-testid='driver-actions-joint'] [data-binding='driver-actions.joint.next12']").innerText();
    await page.getByRole("button", { name: "Add an action" }).click();
    await expect(actionRows(page)).toHaveCount(4);
    const draft = actionRows(page).last();
    await draft.getByLabel("Changes").selectOption("won_arr");
    await draft.getByLabel("Slice").selectOption("company");
    await draft.getByLabel("Target won ARR per win (dollars)").fill("430000");
    await page.getByRole("button", { name: "Apply" }).click();
    const refusal = draft.getByRole("alert");
    await expect(refusal).toContainText("Overlaps 'Company deal size'", { timeout: 30_000 });
    await expect(refusal).toContainText("both change the size of a won deal for Company");
    await expect(refusal).not.toContainText(/actions\[|won_arr|driver/);
    await expect(page.getByRole("button", { name: "Apply" })).toBeEnabled();
    expect(await page.locator("[data-testid='driver-actions-joint'] [data-binding='driver-actions.joint.next12']").innerText(), "the last good figures stay").toBe(shown);
    await draft.getByRole("button", { name: "Remove action" }).click();
    await expect(actionRows(page)).toHaveCount(3);
  });

  test("Add to plan on the size and creation bars opens a draft company action on that driver at the favorable end, and applies nothing @smoke", async () => {
    await enter(page, PLAIN); // a slice with an action on a driver is shown that one, not given a second: start with none
    const applied = (await reports(page)).length;
    const report = await lastReport(page);
    for (const driver of ["won_arr", "productivity"] as const) {
      const high = worksheetRow(report, driver).historical.high.setting;
      const before = await actionRows(page).count();
      await page.locator(`[data-testid='driver-row'][data-driver='${driver}']`).getByRole("button", { name: "Add to plan" }).click();
      await expect(actionRows(page)).toHaveCount(before + 1);
      const draft = actionRows(page).last();
      await expect(draft.getByLabel("Changes")).toHaveValue(driver);
      await expect(draft.getByLabel("Slice")).toHaveValue("company");
      await expect(draft.getByLabel("Starts")).toHaveValue("2026-09");
      await expect(draft.getByLabel(TARGET_LABEL[driver])).toHaveValue(high);
      await expect(draft.getByTestId("action-origin")).toContainText("will differ from the bar's figure");
      await expect(page.getByTestId("plan-unapplied")).toBeVisible();
      expect((await reports(page)).length, "nothing was computed for the draft").toBe(applied);
      await draft.getByRole("button", { name: "Remove action" }).click();
      await expect(actionRows(page)).toHaveCount(before);
    }
  });

  test("Plan an action here on the Average won ARR and Created deals cells of the company and a segment opens a draft on that driver, slice and pooled baseline, and applies nothing @smoke", async () => {
    await enter(page, PLAIN);
    const applied = (await reports(page)).length;
    const report = await lastReport(page);
    for (const [column, driver, says] of [["avg_won_arr", "won_arr", "average won ARR of the lane's wins"], ["created", "productivity", "deals created in the period"]] as const) {
      for (const [row, slice] of [["total", "company"], ["segment/commercial", "commercial"]] as const) {
        const before = await actionRows(page).count();
        await page.getByTestId(`cell-${row}-${column}`).click();
        const entry = page.getByTestId("plan-action");
        await expect(entry).toContainText(says);
        await expect(entry).toContainText("pooled baseline");
        await entry.getByRole("button", { name: "Plan an action here" }).click();
        await expect(actionRows(page)).toHaveCount(before + 1);
        const draft = actionRows(page).last();
        await expect(draft.getByLabel("Changes")).toHaveValue(driver);
        await expect(draft.getByLabel("Slice")).toHaveValue(slice);
        await expect(draft.getByLabel(TARGET_LABEL[driver])).toHaveValue(worksheetRow(report, driver).current.value);
        await expect(page.getByTestId("cell-panel"), "the panel steps aside").toHaveCount(0);
        expect((await reports(page)).length, "nothing was computed for the draft").toBe(applied);
        await draft.getByRole("button", { name: "Remove action" }).click();
        await expect(actionRows(page)).toHaveCount(before);
      }
    }
    // not on an owner's cell
    await page.getByTestId("expand-segment/enterprise").click();
    await page.getByTestId("cell-segment/enterprise/owner/AE-010-created").click();
    await expect(page.getByTestId("plan-action")).toHaveCount(0);
    await page.getByRole("button", { name: "Close panel" }).click();
    await page.getByTestId("expand-segment/enterprise").click();
  });

  test("removing every action returns the no-action figures, and the Actions block goes @smoke", async () => {
    const plain = JSON.parse(fixture("plan.json")) as Plan;
    await enter(page, plain);
    await apply(page, plain);
    expect(await lastReport(page)).toBe(fixture("report.json"));
    await expect(page.getByTestId("driver-actions")).toHaveCount(0, { timeout: 30_000 });
    await expect(page.locator("[data-testid='bridge-row'][data-kind='actions']")).toHaveCount(0);
    await expect(page.getByTestId("needed-stacked")).toHaveCount(0);
    const native = JSON.parse(fixture("report.json")) as { plan: { gap: { fiscal_year: { gap_with_plan: string } } } };
    await expect(page.locator("[data-binding='worksheet.summary.remaining-gap']")).toHaveText(usdShort(native.plan.gap.fiscal_year.gap_with_plan));
    // and the grid is the no-action plan's again
    await expect(page.locator("[data-testid='cell-segment/enterprise-win_rate'] [data-binding='lanes.win_rate.forecast']")).toHaveText(
      percent1((JSON.parse(fixture("lanes.json")) as LanesFile).periods[0].rows.find((r) => r.path.join("/") === "segment/enterprise")!.cells.win_rate.forecast!),
      { timeout: 60_000 },
    );
    expect(issues).toEqual([]);
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
    await expect(page.getByRole("button", { name: "Add an action" })).toHaveCount(0);
    await page.getByTestId("cell-total-win_rate").click();
    await expect(page.getByTestId("cell-panel")).toBeVisible();
    await expect(page.getByRole("button", { name: "Plan an action here" }), "a phone's panel offers no editor").toHaveCount(0);
    await page.getByRole("button", { name: "Close panel" }).click();
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
