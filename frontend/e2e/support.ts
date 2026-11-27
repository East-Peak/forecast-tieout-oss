import { expect, type Page } from "@playwright/test";

/** What every browser smoke spec shares: console hygiene and the digit rule, checked in the real page. */
export const COMPANIES = ["sprout-labs", "sapling-industries", "mighty-oak-holdings"] as const;
export const SCENARIOS = ["as-signed", "demo-plan", "hires-only", "programme-only"] as const;
export const BAD_TEXT = /\bNaN\b|\bundefined\b|\[object|\bInfinity\b|\bnull\b/;

export function collectBrowserIssues(page: Page): string[] {
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

const TICK_SOURCES = ["^-?\\$\\d[\\d.,]*[KMB]?$", "^-?\\d[\\d,.]*$", "^[A-Z][a-z]{2} '\\d{2}$", "^Q[1-4]FY\\d{2}$"];

/**
 * Text nodes with a digit that sit in no bound element. The stated exceptions are checked by content: an axis
 * (or the library's hidden tick-measuring span) may hold only tick labels, a tooltip's period label only one of
 * the report's own period labels, and the literal names "80% range" and "95% range" are allowed.
 */
export async function unboundDigits(page: Page, periodLabels: string[]): Promise<string[]> {
  return page.evaluate(
    ({ ticks, labels }) => {
      const tick = ticks.map((t) => new RegExp(t));
      const out: string[] = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const el = node.parentElement;
        if (!el || ["SCRIPT", "STYLE"].includes(el.tagName)) continue;
        if (el.closest("[data-binding]")) continue;
        let text = (node.textContent ?? "").trim();
        if (!text) continue;
        if (el.closest(".recharts-cartesian-axis, #recharts_measurement_span")) {
          if (!/\d/.test(text) || tick.some((t) => t.test(text))) continue;
          out.push(`axis text that is not a tick label: ${text}`);
          continue;
        }
        if (el.closest("[data-exempt='period-label']")) {
          if (labels.includes(text)) continue;
          out.push(`period label that is not the report's: ${text}`);
          continue;
        }
        text = text.split("80% range").join("").split("95% range").join("");
        if (/\d/.test(text)) out.push(text.trim());
      }
      return out;
    },
    { ticks: TICK_SOURCES, labels: periodLabels },
  );
}

