/**
 * Test-only. The checks every screen is held to (design call 5):
 *   1. every binding on the committed list is present, shows the file's value under an independently
 *      written expectation, AND carries the provenance the list declares (source, path, format,
 *      company, scenario): checkBindings;
 *   2. any digit outside a bound element fails, except the stated exceptions, each of which is
 *      validated by its content, not waved through: unboundDigits;
 *   3. each chart's real props (its data and its series configuration) match what the file holds:
 *      the screen tests capture them from the chart component itself (see capturedChart below);
 *   and the tests mutate (a swapped path, another company's file, a flipped sign, tampered attributes,
 *   a changed dataKey, transformed data, added stacking) to show these fail.
 * Tooltips and expandable rows are opened by the test (openAll here; real hovering in Playwright).
 */
import { fireEvent } from "@testing-library/react";
import type { Binding } from "../Bound";

/** One thing the page must show: the text each element with this binding id must have, in page order. */
export interface Expectation {
  id: string;
  /** the formatted text of each element, in document order (one entry for a single value) */
  texts: string[];
  /** the row pointer each element is read from (a row binding), in the same order; omitted for a plain binding */
  rows?: string[];
}

/** Binding ids a page must not show in this case (a plan item row on a baseline). */
export interface Absent {
  id: string;
}

/**
 * The stated exceptions to "no digit outside a bound element", each checked by what it contains:
 *  - text drawn by the chart library on an axis (.recharts-cartesian-axis) and the hidden span it measures
 *    ticks with (#recharts_measurement_span): must read as a tick label (a dollar tick, a month tick or a quarter);
 *  - a tooltip's period label (data-exempt="period-label"): must be one of the report's own period labels;
 *  - the two literal range names "80% range" and "95% range".
 */
const RANGE_NAMES = ["80% range", "95% range"] as const;
const TICK = [/^-?\$\d[\d.,]*[KM]?$/, /^-?\d[\d,.]*$/, /^[A-Z][a-z]{2} '\d{2}$/, /^Q[1-4]FY\d{2}$/];

export function unboundDigits(container: HTMLElement, periodLabels: readonly string[] = []): string[] {
  const found: string[] = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!element) continue;
    if (element.closest("[data-binding]")) continue;
    let text = (node.textContent ?? "").trim();
    if (!text) continue;
    if (element.closest(".recharts-cartesian-axis, #recharts_measurement_span")) {
      if (!/\d/.test(text) || TICK.some((pattern) => pattern.test(text))) continue;
      found.push(`axis text that is not a tick label: ${text}`);
      continue;
    }
    if (element.closest("[data-exempt='period-label']")) {
      if (periodLabels.includes(text)) continue;
      found.push(`period label that is not one of the report's: ${text}`);
      continue;
    }
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

const elementsOf = (container: HTMLElement, id: string): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>(`[data-binding="${id}"]`));

const expand = (path: string, ctx: { company: string; scenario: string }) =>
  path.split("{company}").join(ctx.company).split("{scenario}").join(ctx.scenario);

/**
 * Failures of check 1. `listed` is the committed binding list for this view; each element's declared
 * provenance is compared with its entry, and its text with the independent expectation.
 */
export function checkBindings(
  container: HTMLElement,
  expected: Expectation[],
  absent: Absent[],
  listed: readonly Binding[],
  ctx: { company: string; scenario: string },
  allowedPrefixes: string[] = [],
): string[] {
  const failures: string[] = [];
  const byId = new Map(listed.map((b) => [b.id, b]));
  for (const { id, texts: want, rows } of expected) {
    const got = elementsOf(container, id);
    if (got.length !== want.length) {
      failures.push(`${id}: expected ${want.length} element(s), the page has ${got.length}`);
      continue;
    }
    const binding = byId.get(id);
    if (!binding) {
      failures.push(`${id}: not on the committed list`);
      continue;
    }
    got.forEach((el, i) => {
      const text = el.textContent ?? "";
      if (text !== want[i]) failures.push(`${id}[${i}]: expected ${JSON.stringify(want[i])}, page shows ${JSON.stringify(text)}`);
      const declared = {
        "data-source": binding.source,
        "data-path": expand((rows?.[i] ?? "") + binding.path, ctx),
        "data-format": binding.format,
        "data-company": ctx.company,
        "data-scenario": ctx.scenario,
      };
      for (const [attribute, value] of Object.entries(declared)) {
        const seen = el.getAttribute(attribute);
        if (seen !== value) failures.push(`${id}[${i}]: ${attribute} is ${JSON.stringify(seen)}, the list declares ${JSON.stringify(value)}`);
      }
    });
  }
  for (const { id } of absent) {
    if (elementsOf(container, id).length > 0) failures.push(`${id}: should not be on the page in this case`);
  }
  const onPage = new Set(
    Array.from(container.querySelectorAll<HTMLElement>("[data-binding]")).map((el) => el.getAttribute("data-binding") ?? ""),
  );
  for (const id of onPage) {
    if (!byId.has(id) && !allowedPrefixes.some((prefix) => id.startsWith(prefix))) {
      failures.push(`${id}: a bound element that is not on the committed list`);
    }
  }
  return failures;
}

/** What a chart component was given, as captured from the component itself (see ForecastCharts.test.tsx). */
export interface CapturedChart {
  data: unknown;
  xKey: string | undefined;
  series: Array<{ type: string; dataKey: string; stackId?: unknown }>;
  referenceX: string[];
}

export interface ExpectedChart {
  data: unknown;
  xKey: string;
  /** in drawing order */
  series: Array<{ type: string; dataKey: string }>;
  referenceX?: string[];
}

/** Failures of check 3: the chart's real data prop and series configuration are what the file calls for. */
export function checkChart(name: string, got: CapturedChart | undefined, want: ExpectedChart): string[] {
  if (!got) return [`${name}: no chart was drawn`];
  const failures: string[] = [];
  if (canon(got.data) !== canon(want.data)) failures.push(`${name}: the data given to the chart differs from the bound series`);
  if (got.xKey !== want.xKey) failures.push(`${name}: the x axis reads ${String(got.xKey)}, expected ${want.xKey}`);
  const shape = (s: { type: string; dataKey: string }) => `${s.type}:${s.dataKey}`;
  if (got.series.map(shape).join(",") !== want.series.map(shape).join(",")) {
    failures.push(`${name}: series are ${got.series.map(shape).join(",")}, expected ${want.series.map(shape).join(",")}`);
  }
  if (got.series.some((s) => s.stackId !== undefined)) failures.push(`${name}: a series is stacked, which adds values the file does not hold`);
  if (canon(got.referenceX) !== canon(want.referenceX ?? [])) failures.push(`${name}: reference lines differ`);
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
