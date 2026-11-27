/**
 * Test-only. The checks every screen is held to (design call 5), registered once for a screen:
 *   every committed binding is on the page with the report's value under an independently written
 *   expectation and the provenance the list declares, for three companies and four scenarios; no digit
 *   outside a bound element; the committed list and the expectations name the same bindings; and the
 *   checks fail when the screen is wrong (a path swapped, another company's file, a flipped sign, a
 *   scenario swapped, tampered attributes, a stray digit, an unlisted binding).
 * Built on the Forecast harness (binding/__tests__/harness.ts); only the per-screen parts differ.
 */
import { cleanup, render } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { checkBindings, openAll, unboundDigits } from "../../binding/__tests__/harness";
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import * as files from "./files";

export interface Case {
  company: string;
  scenario: string;
  report: TieoutReport;
  index: ReportIndex;
  comparison: ScenarioComparison;
}

export interface Built {
  expected: Expectation[];
  absent: Absent[];
  /** what a tooltip's or an axis's period labels may read on this page */
  periodLabels: string[];
}

export const caseOf = (company: string, scenario: string): Case => ({
  company,
  scenario,
  report: files.report(company, scenario),
  index: files.index(),
  comparison: files.comparison(company),
});

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

type Shown = Pick<Case, "report" | "index" | "comparison">;

export function mountScreen(Screen: ComponentType, shown: Shown, company: string, scenario: string): HTMLElement {
  const { container } = render(
    <BindingProvider company={company} scenario={scenario} files={shown}>
      <Screen />
    </BindingProvider>,
  );
  openAll(container);
  return container;
}

export interface ScreenChecks {
  name: string;
  Screen: ComponentType;
  /** the committed list in force for this report (a screen may read other places for other variants) */
  listFor: (report: TieoutReport) => readonly Binding[];
  /** the whole committed list, every variant (for the same-names check) */
  fullList: readonly Binding[];
  build: (c: Case) => Built;
  /** a binding to point at the wrong place, and the id the checks must then fail on */
  swap: { binding: Binding; to: string };
  /** a copy of the report with a sign flipped, and the ids that must fail */
  flip: (report: TieoutReport) => { report: TieoutReport; ids: string[] };
  /** a binding id that is on the page for the sapling as-signed case, whose attributes are tampered with */
  probe: string;
  /** extra checks specific to the screen */
  more?: () => void;
}

function failuresOf(container: HTMLElement, checks: ScreenChecks, c: Case): string[] {
  const { expected, absent, periodLabels } = checks.build(c);
  return [
    ...checkBindings(container, expected, absent, checks.listFor(c.report), c),
    ...unboundDigits(container, periodLabels).map((t) => `digits outside a bound element: ${t}`),
  ];
}

export function runScreenChecks(checks: ScreenChecks): void {
  afterEach(cleanup);
  const mount = (c: Case, company = c.company, scenario = c.scenario) => mountScreen(checks.Screen, c, company, scenario);

  describe(`${checks.name}: every binding (with its provenance), every digit`, () => {
    it.each(CASES)("%s / %s", (company, scenario) => {
      const c = caseOf(company, scenario);
      expect(failuresOf(mount(c), checks, c)).toEqual([]);
    });

    it("the committed list and the independent expectations name the same bindings", () => {
      const named = new Set<string>();
      for (const [company, scenario] of CASES) {
        const { expected, absent } = checks.build(caseOf(company, scenario));
        [...expected, ...absent].forEach((e) => named.add(e.id));
      }
      const listed = checks.fullList.map((b) => b.id);
      expect([...named].sort()).toEqual([...new Set(listed)].sort());
    });

    it("within the list in force for a case, every id names one place", () => {
      for (const [company, scenario] of CASES) {
        const ids = checks.listFor(caseOf(company, scenario).report).map((b) => b.id);
        expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([]);
      }
    });
  });

  describe(`${checks.name}: the checks fail when the screen is wrong (mutations)`, () => {
    const base = () => caseOf("sapling-industries", "as-signed");

    it("a swapped path is caught", () => {
      const c = base();
      const original = checks.swap.binding.path;
      (checks.swap.binding as { path: string }).path = checks.swap.to;
      try {
        const failures = failuresOf(mount(c), checks, c);
        expect(failures.some((f) => f.startsWith(checks.swap.binding.id)), failures.join("\n")).toBe(true);
      } finally {
        (checks.swap.binding as { path: string }).path = original;
      }
    });

    it("another company's file is caught", () => {
      const expected = base();
      const wrong = caseOf("sprout-labs", "as-signed");
      expect(failuresOf(mount(wrong, expected.company, expected.scenario), checks, expected).length).toBeGreaterThan(0);
    });

    it("a scenario swapped is caught: the page names the scenario it was given, and the report of another scenario differs", () => {
      const expected = caseOf("sprout-labs", "as-signed");
      const named = failuresOf(mount(expected, expected.company, "demo-plan"), checks, expected);
      expect(named.some((f) => f.includes("data-scenario"))).toBe(true);
    });

    it("a flipped sign is caught", () => {
      const c = base();
      const flipped = checks.flip(c.report);
      const failures = failuresOf(mount({ ...c, report: flipped.report }), checks, c);
      for (const id of flipped.ids) expect(failures.some((f) => f.startsWith(id)), `${id} in\n${failures.join("\n")}`).toBe(true);
    });

    it("tampered provenance is caught: the path, the source, the format, the scenario and the company", () => {
      const c = base();
      const container = mount(c);
      expect(failuresOf(container, checks, c)).toEqual([]);
      const el = container.querySelector(`[data-binding='${checks.probe}']`)!;
      expect(el, checks.probe).not.toBeNull();
      for (const [attribute, value] of [["data-path", "/wrong"], ["data-source", "index"], ["data-format", "usd-full"], ["data-scenario", "nope"], ["data-company", "other"]] as const) {
        const was = el.getAttribute(attribute)!;
        el.setAttribute(attribute, value);
        expect(failuresOf(container, checks, c).some((f) => f.includes(attribute)), attribute).toBe(true);
        el.setAttribute(attribute, was);
      }
    });

    it("a digit outside any bound element is caught", () => {
      const c = base();
      const container = mount(c);
      const stray = document.createElement("p");
      stray.textContent = "Revenue is up 12% on last year";
      container.appendChild(stray);
      expect(unboundDigits(container, [])).toEqual(["Revenue is up 12% on last year"]);
    });

    it("a bound element that is not on the committed list is caught", () => {
      const c = base();
      const container = mount(c);
      const extra = document.createElement("span");
      extra.setAttribute("data-binding", "sneaky");
      container.appendChild(extra);
      expect(failuresOf(container, checks, c).some((f) => f.startsWith("sneaky"))).toBe(true);
    });
  });

  checks.more?.();
}
