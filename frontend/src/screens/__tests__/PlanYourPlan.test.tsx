import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkBindings, unboundDigits } from "../../binding/__tests__/harness";
import { YOUR_PLAN, withYourPlan, withYourPlanRow } from "../../editor/yourPlan";
import type { ComparisonRow } from "../../editor/protocol";
import type { TieoutReport } from "../../generated/report";
import { LISTED_BINDINGS } from "../plan/bindings";
import { WORKSHEET_BINDINGS } from "../plan/worksheetBindings";
import PlanScreen from "../plan/PlanScreen";
import * as files from "./files";
import { build } from "./planExpectations";
import { mountScreen } from "./screenChecks";
import type { Case } from "./screenChecks";

// recharts draws nothing without a measured box (jsdom has none): its container is given a size, and the figures printed at the bars' ends then exist
vi.mock("recharts", async (importOriginal) => {
  const { withCapture } = await import("./rechartsCapture");
  return withCapture(await importOriginal<typeof import("recharts")>(), []);
});

afterEach(cleanup);

// The core's own output for an edited plan, written by a native run (engine/scripts/generate_editor_fixture.py):
// a report no committed scenario file holds, shown by the same screen under the same checks.
const FIXTURE = resolve(__dirname, "fixtures/your-plan");
const read = <T,>(name: string) => JSON.parse(readFileSync(resolve(FIXTURE, name), "utf8")) as T;
const COMPANY = "sapling-industries";

function computed(): Case {
  return {
    company: COMPANY,
    scenario: YOUR_PLAN,
    report: read<TieoutReport>("report.json"),
    index: withYourPlan(files.index()),
    comparison: withYourPlanRow(files.comparison(COMPANY), read<ComparisonRow>("comparison-row.json")),
  };
}

describe("Plan: a report computed in the browser is held to the same checks as a committed one", () => {
  it("every committed binding is on the page with the report's value and provenance, scenario your-plan, and no digit stands outside one", () => {
    const c = computed();
    const container = mountScreen(PlanScreen, c, c.company, c.scenario);
    const { expected, absent, periodLabels } = build(c);
    expect(expected.length).toBeGreaterThan(20);
    expect([...checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], c), ...unboundDigits(container, periodLabels)]).toEqual([]);
    expect(container.querySelector("[data-binding='worksheet.summary.remaining-gap']")?.getAttribute("data-scenario")).toBe(YOUR_PLAN);
  });

  it("the comparison table lists the visitor's plan last, from the core's row", () => {
    const c = computed();
    const container = mountScreen(PlanScreen, c, c.company, c.scenario);
    const rows = Array.from(container.querySelectorAll("[data-testid='compare-row']"));
    expect(rows).toHaveLength(5);
    expect(rows[4].textContent).toContain("Your plan");
  });

  it("a figure from the wrong report is caught", () => {
    const c = computed();
    const other = { ...c, report: files.report(COMPANY, "demo-plan") };
    const container = mountScreen(PlanScreen, other, c.company, c.scenario);
    const { expected, absent } = build(c);
    expect(checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], c).length).toBeGreaterThan(0);
  });
});
