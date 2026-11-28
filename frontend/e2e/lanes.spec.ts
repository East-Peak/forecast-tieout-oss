import { expect, test } from "@playwright/test";
import { collectBrowserIssues } from "./support";

test("@smoke the lanes prototype loads at 1440 with no console errors and no sideways scroll", async ({ page }) => {
  const issues = collectBrowserIssues(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/lanes?company=sapling-industries", { waitUntil: "networkidle" });
  await expect(page.getByTestId("grid")).toBeVisible();
  await expect(page.locator("thead th[data-col]")).toHaveCount(8);
  await page.getByRole("button", { name: "Expand Enterprise" }).click();
  await expect(page.locator("tr[data-role='owner']").first()).toBeVisible();
  await page.getByTestId("cell-total-won").click();
  await expect(page.getByTestId("cell-panel")).toBeVisible();
  const overflow = await page.evaluate(() => ({ page: document.documentElement.scrollWidth > document.documentElement.clientWidth, grid: document.querySelector("[data-testid=grid-scroll]")!.scrollWidth > document.querySelector("[data-testid=grid-scroll]")!.clientWidth }));
  expect(overflow.page, "the page scrolls sideways").toBe(false);
  expect(overflow.grid, "the grid scrolls sideways at 1440").toBe(false);
  expect(issues).toEqual([]);
});
