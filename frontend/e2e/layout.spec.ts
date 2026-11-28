import { expect, test, type Page } from "@playwright/test";
import { COMPANIES, STRETCH } from "./support";

/**
 * The composition of the four Evidence screens at desktop and wide-desktop widths: the content column lines up with the header's
 * edges (no empty band beside it), a row of cards fills its row at one height, and no card is a tall box around a little content.
 */
const EVIDENCE = ["forecast", "capacity", "pipeline", "trust"] as const;
const WIDTHS = [1280, 1440, 1920, 2304] as const;

async function open(page: Page, screen: string, company: string) {
  const response = await page.goto(`/${screen}?company=${company}&scenario=as-signed`, { waitUntil: "networkidle" });
  expect(response?.ok(), `${screen} ${company}`).toBe(true);
  await expect(page.locator("main h2").first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test.describe("the content column and the header share their edges @smoke", () => {
  for (const width of WIDTHS) {
    test.describe(`${width} wide`, () => {
      test.use({ viewport: { width, height: 900 } });
      for (const screen of EVIDENCE) {
        test(`${screen}: the column's left and right edges are the header's content edges @smoke`, async ({ page }) => {
          await open(page, screen, "sapling-industries");
          const edges = await page.evaluate(() => {
            const header = document.querySelector("header") as HTMLElement;
            const style = getComputedStyle(header);
            const box = header.getBoundingClientRect();
            const column = document.querySelector("main > div") as HTMLElement;
            const c = column.getBoundingClientRect();
            return {
              headerLeft: box.left + parseFloat(style.paddingLeft),
              headerRight: box.right - parseFloat(style.paddingRight),
              columnLeft: c.left,
              columnRight: c.right,
            };
          });
          expect(Math.abs(edges.columnLeft - edges.headerLeft), "left edges").toBeLessThanOrEqual(2);
          expect(Math.abs(edges.columnRight - edges.headerRight), "right edges: no band beside the content").toBeLessThanOrEqual(2);
        });
      }
    });
  }
});

test.describe("cards fill their rows and wrap their content @smoke", () => {
  for (const width of [1440, 1920]) {
    test.describe(`${width} wide`, () => {
      test.use({ viewport: { width, height: 900 } });
      for (const company of width === 1440 ? COMPANIES : (["sapling-industries"] as const)) {
        for (const screen of EVIDENCE) {
          test(`${screen}: ${company} @smoke`, async ({ page }) => {
            await open(page, screen, company);
            const faults = await page.evaluate(() => {
              const out: string[] = [];
              const name = (el: Element) => `${el.getAttribute("data-testid") ?? el.tagName}: ${(el.textContent ?? "").trim().slice(0, 30)}`;
              // a grid whose children are cards: one height within a row, and the row filled edge to edge
              const grids = new Set<HTMLElement>();
              document.querySelectorAll("main [data-testid='metric-card'], main [data-testid='verdict-card']").forEach((card) => {
                if (card.parentElement && getComputedStyle(card.parentElement).display === "grid") grids.add(card.parentElement);
              });
              grids.forEach((grid) => {
                const cards = Array.from(grid.children).filter((c) => c.matches("[data-testid='metric-card'], [data-testid='verdict-card']"));
                const rows = new Map<number, Element[]>();
                cards.forEach((c) => rows.set(Math.round(c.getBoundingClientRect().top), [...(rows.get(Math.round(c.getBoundingClientRect().top)) ?? []), c]));
                const g = grid.getBoundingClientRect();
                rows.forEach((row) => {
                  const heights = row.map((c) => c.getBoundingClientRect().height);
                  if (Math.max(...heights) - Math.min(...heights) > 2) out.push(`uneven heights in a row: ${row.map(name).join(" | ")}`);
                  if (row.length > 1) {
                    const left = Math.min(...row.map((c) => c.getBoundingClientRect().left));
                    const right = Math.max(...row.map((c) => c.getBoundingClientRect().right));
                    if (Math.abs(left - g.left) > 2 || Math.abs(right - g.right) > 2) out.push(`a row of cards does not fill its grid: ${row.map(name).join(" | ")}`);
                  }
                });
              });
              // no card holds much more room than its content: free space below the content stays under a third of the card
              document.querySelectorAll("main .shadow-ft").forEach((card) => {
                if (card.closest("[data-testid='grid-scroll']") || !(card instanceof HTMLElement) || card.tagName === "SPAN") return;
                const style = getComputedStyle(card);
                const box = card.getBoundingClientRect();
                const inner = box.bottom - parseFloat(style.paddingBottom) - parseFloat(style.borderBottomWidth);
                const bottoms = Array.from(card.children).map((c) => c.getBoundingClientRect().bottom);
                if (bottoms.length === 0) return;
                const free = inner - Math.max(...bottoms);
                if (free > 24 && free > box.height / 3) out.push(`a card with ${Math.round(free)}px of empty room below its content: ${name(card)}`);
              });
              return out;
            });
            expect(faults).toEqual([]);
          });
        }
      }
    });
  }
});

test.describe("nothing overflows at wide desktop widths either, in stretched text @smoke", () => {
  for (const width of [1280, 1440, 1920]) {
    test.describe(`${width} wide`, () => {
      test.use({ viewport: { width, height: 900 } });
      for (const screen of EVIDENCE) {
        test(`${screen} @smoke`, async ({ page }) => {
          await open(page, screen, "sapling-industries");
          await page.addStyleTag({ content: STRETCH });
          const over = await page.evaluate(() => {
            const w = document.documentElement.clientWidth;
            return {
              sideways: document.documentElement.scrollWidth - w,
              wide: Array.from(document.querySelectorAll("main *")).filter((el) => el.getBoundingClientRect().right > w + 1).slice(0, 5).map((el) => `${el.tagName}.${String(el.className).slice(0, 40)}`),
              scrolling: Array.from(document.querySelectorAll(".overflow-x-auto")).filter((el) => el.scrollWidth > el.clientWidth + 1).length,
            };
          });
          expect(over.sideways).toBeLessThanOrEqual(0);
          expect(over.wide).toEqual([]);
          expect(over.scrolling).toBe(0);
        });
      }
    });
  }
});
