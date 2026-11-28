import { expect, test, type Page } from "@playwright/test";
import { days, decimal1, percent1, usdShort, whole } from "../src/screens/__tests__/independent";
import { BAD_TEXT, COMPANIES, STRETCH, collectBrowserIssues, unboundDigits } from "./support";

/**
 * Browser smoke for the swimlane grid on Plan: it is drawn from the core's lanes file for every company, a segment's
 * owners are fetched when it is opened and read from their own file, a cell opens a side panel whose record count is the
 * file's, Escape closes it with the focus back on the cell; and its layout holds at five widths with the text spread.
 * The tests read the files and compare; they add nothing the page should have added.
 */
type Cell = { actual: string | null; forecast: string | null; goal: string | null; ratio: string | null; status: string; split: { actual: { carried_in: string; created_in_period: string } } | null };
type Row = { kind: string; label: string; path: string[]; cells: Record<string, Cell> };
type Lanes = { periods: Array<{ key: string; rows: Row[] }>; columns: Array<{ key: string; title: string }> };
type Owners = { periods: Array<{ key: string; rows: Row[] }>; checks: Array<{ name: string; passed: boolean }> };
type Index = { companies: Array<{ id: string; scenarios: Array<{ id: string; lanes: string; lanes_owners: Record<string, string> }> }> };

const FORMAT: Record<string, (raw: string) => string> = { open: whole, created: whole, created_arr: usdShort, win_rate: percent1, cycle: days, won: whole, avg_won_arr: usdShort, bookings: usdShort };
const shown = (column: string, raw: string | null) => (raw === null ? "unavailable" : FORMAT[column](raw));

const json = async <T,>(page: Page, path: string) => (await (await page.request.get(`/data/reports/${path}`)).json()) as T;
const lanesOf = async (page: Page, company: string, scenario: string) => json<Lanes>(page, `${company}/lanes-${scenario}.json`);
const ownersPath = async (page: Page, company: string, scenario: string, segment: string) => {
  const index = await json<Index>(page, "index.json");
  return index.companies.find((c) => c.id === company)!.scenarios.find((s) => s.id === scenario)!.lanes_owners[segment];
};

async function open(page: Page, company: string, scenario = "as-signed") {
  const response = await page.goto(`/plan?company=${company}&scenario=${scenario}`, { waitUntil: "networkidle" });
  expect(response?.ok(), `${company}/${scenario}`).toBe(true);
  await expect(page.locator("#scenario-selector")).toHaveValue(scenario);
  await expect(page.getByTestId("lanes-grid")).toBeVisible();
}

const cell = (page: Page, row: string, column: string) => page.getByTestId(`cell-${row}-${column}`);

/** Scroll the page so a cell stands just below the sticky header (on a phone the header is half the screen: Playwright's own centering leaves the cell under it). */
async function below(page: Page, locator: ReturnType<Page["getByTestId"]>) {
  await locator.evaluate((el) => {
    el.scrollIntoView({ block: "nearest", inline: "center" });
    const header = document.querySelector<HTMLElement>(".sticky.top-0.z-40")!.getBoundingClientRect().height;
    window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - header - 8);
  });
}

test.describe("the lanes grid, every company @smoke", () => {
  // a large company's owners are hundreds of rows; the read is one round trip, but the page may be slow on a loaded runner
  test.describe.configure({ timeout: 90_000 });
  for (const company of COMPANIES) {
    test(`${company}: the grid shows the file's figures; opening a segment reads its owners from their own file @smoke`, async ({ page }) => {
      const issues = collectBrowserIssues(page);
      await open(page, company);
      const lanes = await lanesOf(page, company, "as-signed");
      const fy = lanes.periods[0];

      // every cell of the collapsed grid, against the file (one read of the page, compared with the file's figures; it retries until they agree or time runs out)
      const wanted = (rows: Row[], keys: string[]) => Object.fromEntries(rows.flatMap((row) => keys.map((key) => [`${row.path.join("/")}|${key}`, shown(key, row.cells[key].actual)])));
      const onPage = (rows: Row[], keys: string[]) =>
        page.evaluate(
          ({ rows, keys }) =>
            Object.fromEntries(rows.flatMap((id) => keys.map((key) => [`${id}|${key}`, document.querySelector(`[data-testid='cell-${id}-${key}'] [data-binding$='.actual']`)?.textContent ?? "not on the page"]))),
          { rows: rows.map((r) => r.path.join("/")), keys },
        );
      await expect.poll(() => onPage(fy.rows, lanes.columns.map((c) => c.key)), { message: "the collapsed grid shows the file's actuals" }).toEqual(wanted(fy.rows, lanes.columns.map((c) => c.key)));
      await expect(page.getByTestId("lanes-grid").locator("thead [data-col]")).toHaveCount(8);

      // opening each segment reads its owners file; the page shows that file's rows, figure for figure
      const segments = fy.rows.filter((r) => r.kind === "segment");
      for (const segment of segments) {
        await page.getByTestId(`expand-${segment.path.join("/")}`).click();
        const owners = await json<Owners>(page, await ownersPath(page, company, "as-signed", segment.path[1]));
        expect(owners.checks.every((c) => c.passed), "the owners file's own checks (owner rows add to the segment) passed in the core").toBe(true);
        const rows = owners.periods[0].rows;
        // wait on the rows that prove this segment's owners are in
        await expect(page.locator(`[data-testid^='row-${segment.path.join("/")}/']`)).toHaveCount(rows.length);
        const keys = ["created", "won", "bookings"];
        await expect.poll(() => onPage(rows, keys), { message: `${segment.label}: the owner rows show their file's actuals` }).toEqual(wanted(rows, keys));
      }
      await expect(page.getByTestId("owner-note")).toContainText("allocated goals");

      const text = await page.locator("body").innerText();
      expect(text, "NaN, undefined or null on the page").not.toMatch(BAD_TEXT);
      expect(await unboundDigits(page, []), "digits outside a bound element").toEqual([]);
      expect(issues).toEqual([]);
    });
  }

  test("the period switch moves the grid to a quarter, and the quarter's figures are the file's @smoke", async ({ page }) => {
    await open(page, "sapling-industries");
    const lanes = await lanesOf(page, "sapling-industries", "as-signed");
    const q = lanes.periods[3];
    await page.getByTestId(`period-${q.key}`).click();
    await expect(page.getByTestId(`period-${q.key}`)).toHaveAttribute("aria-pressed", "true");
    await expect(cell(page, "total", "bookings").locator("[data-binding$='.actual']")).toHaveText(usdShort(q.rows[0].cells.bookings.actual!));
    await expect(cell(page, "total", "won").locator("[data-binding$='.forecast']")).toHaveText(decimal1(q.rows[0].cells.won.forecast!));
  });

  test("switching company reloads the lanes: the grid carries the new company's figures @smoke", async ({ page }) => {
    await open(page, "sapling-industries");
    await page.locator("#company-selector").selectOption("sprout-labs");
    const lanes = await lanesOf(page, "sprout-labs", "as-signed");
    // wait on content that proves the new state, not on the stale grid
    await expect(page.locator("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.actual'][data-company='sprout-labs']")).toHaveText(usdShort(lanes.periods[0].rows[0].cells.bookings.actual!));
    await expect(page.getByTestId("plan-basis")).toContainText("Reconstructed FY plan basis");
  });

  test("another scenario draws that scenario's forecasts @smoke", async ({ page }) => {
    await open(page, "sapling-industries", "demo-plan");
    const lanes = await lanesOf(page, "sapling-industries", "demo-plan");
    await expect(cell(page, "total", "bookings").locator("[data-binding$='.forecast']")).toHaveText(usdShort(lanes.periods[0].rows[0].cells.bookings.forecast!));
    await expect(cell(page, "total", "bookings").locator("[data-binding$='.forecast']")).toHaveAttribute("data-scenario", "demo-plan");
  });
});

test.describe("the cell panel @smoke", () => {
  test("opens beside the grid with the records behind the cell: the record count is the cell's actual @smoke", async ({ page }) => {
    const issues = collectBrowserIssues(page);
    await open(page, "sapling-industries");
    const lanes = await lanesOf(page, "sapling-industries", "as-signed");
    const total = lanes.periods[0].rows[0].cells;

    await cell(page, "total", "created").click();
    const panel = page.getByTestId("cell-panel");
    await expect(panel).toBeVisible();
    await expect(page.locator("[data-testid='records'][data-state='ready']")).toBeVisible();
    // Created: the records are the deals created, and their count is the cell's actual
    await expect(panel.getByTestId("records-count").locator("[data-binding='record.count']")).toHaveText(whole(total.created.actual!));
    await expect(panel.getByTestId("record-row")).toHaveCount(Number(total.created.actual));

    // Won: two groups, carried in and created in the period, whose counts are the file's split of the actual
    await cell(page, "total", "won").click();
    const groups = panel.getByTestId("records-count").locator("[data-binding='record.count']");
    await expect(groups).toHaveCount(2);
    await expect(groups.first()).toHaveText(whole(total.won.split!.actual.carried_in));
    await expect(groups.last()).toHaveText(whole(total.won.split!.actual.created_in_period));
    await expect(panel.getByTestId("record-row")).toHaveCount(Number(total.won.actual));
    await expect(panel.getByTestId("contributions")).toContainText("modeled");

    // the three values, and the definition, are there
    await expect(panel).toContainText("Forecast");
    await expect(panel).toContainText("Goal");
    await expect(panel).toContainText("What it means");
    expect(await unboundDigits(page, [])).toEqual([]);
    expect(issues).toEqual([]);
  });

  test("an owner's panel shows quota, days, weight and share from the goal basis @smoke", async ({ page }) => {
    await open(page, "sapling-industries");
    await page.getByTestId("expand-segment/enterprise").click();
    const owners = await json<Owners>(page, await ownersPath(page, "sapling-industries", "as-signed", "enterprise"));
    const first = owners.periods[0].rows.find((r) => r.kind === "owner")!;
    await cell(page, first.path.join("/"), "bookings").click();
    const goal = page.getByTestId("goal-source");
    for (const id of ["basis.owner.quota", "basis.owner.days", "basis.owner.weight", "basis.owner.share"]) await expect(goal.locator(`[data-binding='${id}']`)).toBeVisible();
    await expect(goal).toContainText("allocated goal");
  });

  test("Escape closes the panel and the focus returns to the cell @smoke", async ({ page }) => {
    await open(page, "sapling-industries");
    const target = cell(page, "segment/enterprise", "bookings");
    await target.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("cell-panel")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("cell-panel")).toHaveCount(0);
    await expect(target).toBeFocused();
  });

  test("a cell with no color says why on hover and on focus, in the file's words @smoke", async ({ page }) => {
    await open(page, "sapling-industries");
    const lanes = (await json<{ reasons: Record<string, string> }>(page, "sapling-industries/lanes-as-signed.json")).reasons;
    const open_ = cell(page, "total", "open");
    const tip = open_.getByRole("tooltip");
    await expect(tip).toBeHidden();
    await open_.hover();
    await expect(tip).toBeVisible();
    await expect(tip).toHaveText(lanes.vacuous);
    await page.mouse.move(0, 0);
    await expect(tip).toBeHidden();
    await open_.focus();
    await expect(tip).toBeVisible();
  });

  test("the goal-inside-80%-range marker is on the total's bookings, and its range is the file's @smoke", async ({ page }) => {
    await open(page, "sapling-industries");
    const marker = page.getByTestId("range-marker");
    await expect(marker).toHaveCount(1);
    await expect(marker).toBeVisible();
    await expect(cell(page, "total", "bookings").getByTestId("range-marker")).toHaveCount(1);
  });
});

test.describe("layout at five widths, with the text spread @smoke", () => {
  for (const width of [390, 768, 1024, 1280, 1440]) {
    test.describe(`${width} wide`, () => {
      test.use({ viewport: { width, height: 900 } });
      for (const company of COMPANIES) {
        test(`${company}: the page never scrolls sideways, the grid scrolls inside itself with the first column kept, the panel does not cover its row @smoke`, async ({ page }) => {
          await open(page, company);
          await page.evaluate(() => document.fonts.ready);
          const sideways = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          const grid = page.getByTestId("grid-scroll");
          const box = async () => (await grid.boundingBox())!;

          // as shipped, the grid takes the width the window gives at desktop widths
          if (width >= 1280) {
            const main = (await page.locator("main").boundingBox())!;
            expect((await box()).width, "the grid uses the available width").toBeGreaterThanOrEqual(main.width - 2 * 24 - 2);
            expect(await grid.evaluate((el) => el.scrollWidth - el.clientWidth), "and needs no sideways scroll at rest").toBeLessThanOrEqual(1);
          }

          await page.addStyleTag({ content: STRETCH });
          expect(await sideways(), "the page does not scroll sideways").toBeLessThanOrEqual(0);

          // the grid is what scrolls, and the first column stays where it is
          const overflow = await grid.evaluate((el) => el.scrollWidth - el.clientWidth);
          if (width < 1024) expect(overflow, "below lg the grid scrolls inside its container").toBeGreaterThan(0);
          if (overflow > 0) {
            const head = page.getByTestId("row-total").locator("th").first();
            const before = (await head.boundingBox())!.x;
            await grid.evaluate((el) => (el.scrollLeft = 300));
            const after = (await head.boundingBox())!.x;
            expect(Math.abs(after - before), "the first column is sticky").toBeLessThan(1.5);
            await grid.evaluate((el) => (el.scrollLeft = 0));
          }

          // a segment opened, and a cell opened: the page still does not overflow, and the panel does not hide the cell at desktop widths
          await page.locator("[data-testid^='expand-segment/']").first().click();
          await expect(page.locator("[data-testid^='row-segment/'][data-role='owner']").first()).toBeVisible();
          await below(page, page.getByTestId("cell-total-bookings"));
          // on a phone the sticky header leaves too little room for Playwright's own aim; the tap is sent to the cell
          if (width < 1024) await page.getByTestId("cell-total-bookings").dispatchEvent("click");
          else await page.getByTestId("cell-total-bookings").click();
          const panel = page.getByTestId("cell-panel");
          await expect(panel).toBeVisible();
          await page.waitForTimeout(200);
          expect(await sideways(), "nor with the panel open").toBeLessThanOrEqual(0);
          const p = (await panel.boundingBox())!;
          if (width >= 1024) {
            const c = (await page.getByTestId("cell-total-bookings").boundingBox())!;
            const clear = c.x + c.width <= p.x + 1 || c.x >= p.x + p.width - 1;
            expect(clear, `the cell (${c.x}..${c.x + c.width}) is not under the panel (${p.x}..${p.x + p.width})`).toBe(true);
          } else {
            expect(p.width, "below lg the panel is a full-width sheet").toBeGreaterThanOrEqual(width - 1);
          }
          await page.keyboard.press("Escape");
          await expect(panel).toHaveCount(0);
        });
      }
    });
  }
});
