/**
 * Test-only. The checks every screen is held to (design call 5):
 *   1. every binding on the committed list is present and shows the file's value under an
 *      independently written expectation (checkBindings);
 *   2. any digit outside a bound element fails, except the stated exceptions (unboundDigits);
 *   3. each chart's plotted data equals its bound series (checkPlotted);
 *   and the tests mutate (a swapped path, another company's file, a flipped sign) to show these fail.
 * Tooltips and expandable rows are opened by the test before checking (openAll, tooltips in the screen test).
 */
import { fireEvent } from "@testing-library/react";

/** One thing the page must show: the text each element with this binding id must have, in page order. */
export interface Expectation {
  id: string;
  /** the formatted text of each element, in document order (one entry for a single value) */
  texts: string[];
}

/** Expectations for the binding ids a page does not show in this case (a plan item row on a baseline). */
export interface Absent {
  id: string;
}

/**
 * The stated exceptions to "no digit outside a bound element":
 *  - axis tick labels drawn by the chart library (.recharts-cartesian-axis), and the hidden span the
 *    library measures them with (#recharts_measurement_span);
 *  - a period label (the tooltip's header), marked data-exempt="period-label";
 *  - the two literal range names "80% range" and "95% range" (the names of the report's two ranges).
 */
const RANGE_NAMES = ["80% range", "95% range"] as const;

export function unboundDigits(container: HTMLElement): string[] {
  const found: string[] = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!element) continue;
    if (element.closest("[data-binding], .recharts-cartesian-axis, [data-exempt='period-label'], #recharts_measurement_span")) continue;
    let text = node.textContent ?? "";
    for (const name of RANGE_NAMES) text = text.split(name).join("");
    if (/\d/.test(text)) found.push(text.trim());
  }
  return found;
}

/** Click every collapsed disclosure and row toggle, repeatedly, until nothing is collapsed. */
export function openAll(container: HTMLElement): void {
  for (let pass = 0; pass < 5; pass++) {
    const closed = container.querySelectorAll<HTMLElement>("[aria-expanded='false']");
    if (closed.length === 0) return;
    closed.forEach((button) => fireEvent.click(button));
  }
}

const texts = (container: HTMLElement, id: string): string[] =>
  Array.from(container.querySelectorAll<HTMLElement>(`[data-binding="${id}"]`)).map((el) => el.textContent ?? "");

/** Failures of check 1: each expectation met, nothing on the page outside the committed list (plus allowed prefixes). */
export function checkBindings(
  container: HTMLElement,
  expected: Expectation[],
  absent: Absent[],
  listed: string[],
  allowedPrefixes: string[] = [],
): string[] {
  const failures: string[] = [];
  for (const { id, texts: want } of expected) {
    const got = texts(container, id);
    if (got.length !== want.length) {
      failures.push(`${id}: expected ${want.length} element(s), the page has ${got.length}`);
      continue;
    }
    want.forEach((text, i) => {
      if (got[i] !== text) failures.push(`${id}[${i}]: expected ${JSON.stringify(text)}, page shows ${JSON.stringify(got[i])}`);
    });
  }
  for (const { id } of absent) {
    if (texts(container, id).length > 0) failures.push(`${id}: should not be on the page in this case`);
  }
  const onPage = new Set(
    Array.from(container.querySelectorAll<HTMLElement>("[data-binding]")).map((el) => el.getAttribute("data-binding") ?? ""),
  );
  for (const id of onPage) {
    if (!listed.includes(id) && !allowedPrefixes.some((prefix) => id.startsWith(prefix))) {
      failures.push(`${id}: a bound element that is not on the committed list`);
    }
  }
  return failures;
}

/** Failures of check 3: the data each chart was given equals the series the test builds from the file. */
export function checkPlotted(container: HTMLElement, expected: Record<string, unknown>): string[] {
  const failures: string[] = [];
  for (const [chart, want] of Object.entries(expected)) {
    const el = container.querySelector<HTMLElement>(`[data-chart="${chart}"][data-plotted]`);
    if (!el) {
      failures.push(`${chart}: no chart on the page`);
      continue;
    }
    const got: unknown = JSON.parse(el.getAttribute("data-plotted") ?? "null");
    if (canon(got) !== canon(want)) failures.push(`${chart}: plotted data differs from the bound series`);
  }
  return failures;
}

/** JSON with every object's keys in order, so two values compare equal whatever order they were built in. */
function canon(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  );
}
