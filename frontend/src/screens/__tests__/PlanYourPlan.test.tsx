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
const FIXTURES = resolve(__dirname, "fixtures");
const read = <T,>(name: string, dir = "your-plan") => JSON.parse(readFileSync(resolve(FIXTURES, dir, name), "utf8")) as T;
const COMPANY = "sapling-industries";

/** The core's own output for the fixture plan in `dir`: "your-plan" has hires and a program, "your-plan-actions" adds a win-rate action. */
function computed(dir = "your-plan"): Case {
  return {
    company: COMPANY,
    scenario: YOUR_PLAN,
    report: read<TieoutReport>("report.json", dir),
    index: withYourPlan(files.index()),
    comparison: withYourPlanRow(files.comparison(COMPANY), read<ComparisonRow>("comparison-row.json", dir)),
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

  it("a plan with a win-rate action is held to them too: the Actions block and the bridge's joint step, every figure the core's", () => {
    const c = computed("your-plan-actions");
    const container = mountScreen(PlanScreen, c, c.company, c.scenario);
    const { expected, absent, periodLabels } = build(c);
    for (const id of ["driver-actions.item.name", "driver-actions.item.removal.rest", "driver-actions.joint.rest", "driver-actions.with.year", "driver-actions.without.next12"]) {
      expect(expected.some((e) => e.id === id), `${id} is expected`).toBe(true);
      expect(container.querySelector(`[data-binding='${id}']`), `${id} is on the page`).not.toBeNull();
    }
    expect([...checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], c), ...unboundDigits(container, periodLabels)]).toEqual([]);
    expect(Array.from(container.querySelectorAll("[data-testid='bridge-row']")).map((r) => r.getAttribute("data-kind"))).toContain("actions");
  });

  it("a plan with an action on each driver is held to them too: the block names each driver, and the material reconciliation is the core's figure and sentence in both windows", () => {
    const c = computed("your-plan-three-drivers");
    const container = mountScreen(PlanScreen, c, c.company, c.scenario);
    const { expected, absent, periodLabels } = build(c);
    expect([...checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], c), ...unboundDigits(container, periodLabels)]).toEqual([]);
    const section = c.report.driver_actions;
    if (!("joint_gain" in section)) throw new Error("no actions");
    const rows = Array.from(container.querySelectorAll("[data-testid='driver-action-row']"));
    expect(rows.map((r) => r.querySelector("[data-testid='driver-action-driver']")?.textContent)).toEqual(["Win rate", "Won ARR per win", "Creation productivity"]);
    const line = container.querySelector("[data-testid='driver-actions-reconciliation']")!;
    expect(section.reconciliation.material).toEqual({ "rest of fiscal year": true, "next twelve months": true });
    expect(line).toHaveTextContent("-$22K");
    expect(line).toHaveTextContent("-$660K");
    for (const w of ["rest of fiscal year", "next twelve months"] as const) expect(line).toHaveTextContent(section.reconciliation.sentences[w]);
    expect(container.querySelector("[data-testid='driver-actions']")).toHaveTextContent(/the size of a win, the creation of new pipeline or how long wins take/);
    expect(Array.from(container.querySelectorAll("[data-testid='bridge-row']")).map((r) => r.getAttribute("data-kind"))).toContain("actions");
  });

  it("a plan with an action on each of the four drivers is held to them too: the cycle's tag, the core's timing sentence for the material reconciliation, and no solved cycle", () => {
    const c = computed("your-plan-four-drivers");
    const container = mountScreen(PlanScreen, c, c.company, c.scenario);
    const { expected, absent, periodLabels } = build(c);
    expect([...checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], c), ...unboundDigits(container, periodLabels)]).toEqual([]);
    const section = c.report.driver_actions;
    if (!("joint_gain" in section)) throw new Error("no actions");
    const rows = Array.from(container.querySelectorAll("[data-testid='driver-action-row']"));
    expect(rows.map((r) => r.querySelector("[data-testid='driver-action-driver']")?.textContent)).toEqual(["Win rate", "Won ARR per win", "Creation productivity", "Cycle length"]);
    const line = container.querySelector("[data-testid='driver-actions-reconciliation']")!;
    expect(section.reconciliation.material).toEqual({ "rest of fiscal year": true, "next twelve months": true });
    for (const w of ["rest of fiscal year", "next twelve months"] as const) {
      expect(line).toHaveTextContent(section.reconciliation.sentences[w]);
      expect(section.reconciliation.sentences[w]).not.toMatch(/reinforce|overlap/);
    }
    expect(container.querySelector("[data-testid='driver-actions']")).toHaveTextContent(section.definition);
    expect(section.definition).toMatch(/changes when wins land/);
    // the cycle is not solved for while the plan moves it: the core's sentence stands where the figure would, once
    const cycle = container.querySelector("[data-testid='driver-row'][data-driver='cycle_days']")!;
    expect(cycle.querySelector("[data-testid='needed-stacked']")).toHaveTextContent(/cycle action/);
    expect(container.querySelector("[data-testid='driver-scaled'][data-driver='cycle_days']")).toBeNull();
    expect(cycle.querySelector("[data-testid='driver-position-pill']")).not.toBeNull();
  });

  it("the tornado says where the plan's win-rate action sits against the worksheet even though no setting is solved, and says how a size or creation action stacks with its flex", () => {
    const c = computed("your-plan-three-drivers");
    const container = mountScreen(PlanScreen, c, c.company, c.scenario);
    const rate = container.querySelector("[data-testid='driver-row'][data-driver='win_rate']")!;
    expect(rate.querySelector("[data-testid='driver-position-pill']")).toHaveTextContent("Outside historical settings");
    for (const driver of ["won_arr", "productivity"]) {
      const note = container.querySelector(`[data-testid='driver-scaled'][data-driver='${driver}']`);
      const row = c.report.worksheet && "drivers" in c.report.worksheet ? c.report.worksheet.drivers.find((d) => d.driver === driver) : undefined;
      expect(note, driver).not.toBeNull();
      expect(note).toHaveTextContent(row!.limitation!);
      expect(note!.querySelector("[data-binding='driver.scaled']")).not.toBeNull();
    }
    const plain = mountScreen(PlanScreen, computed("your-plan-actions"), COMPANY, YOUR_PLAN);
    expect(plain.querySelector("[data-testid='driver-scaled']")).toBeNull();
    expect(plain.querySelector("[data-testid='driver-row'][data-driver='won_arr'] [data-testid='driver-position-pill']")).toBeNull();
  });

  it("the reconciliation line is said only where the core calls it material, in the core's sentence for that window; a figure that rounds to zero is not said", () => {
    const c = computed("your-plan-actions");
    const none = mountScreen(PlanScreen, c, c.company, c.scenario);
    expect(none.querySelector("[data-testid='driver-actions-reconciliation']")).toBeNull();
    cleanup();
    const report = structuredClone(c.report);
    if (!("joint_gain" in report.driver_actions)) throw new Error("no actions");
    report.driver_actions.reconciliation.values["next twelve months"] = "-84200.17" as never;
    report.driver_actions.reconciliation.material["next twelve months"] = true;
    // a residue of a cent is the core's to call immaterial: the line is not said, though the figure is not zero
    report.driver_actions.reconciliation.values["rest of fiscal year"] = "0.01" as never;
    report.driver_actions.reconciliation.sentences["next twelve months"] = "The actions reinforce one another: together they gain more than removing each one loses." as never;
    const shown = { ...c, report };
    const container = mountScreen(PlanScreen, shown, c.company, c.scenario);
    const { expected, absent, periodLabels } = build(shown);
    expect(expected.some((e) => e.id === "driver-actions.reconciliation.next12")).toBe(true);
    expect(container.querySelector("[data-binding='driver-actions.reconciliation.rest']")).toBeNull();
    expect(container.querySelector("[data-binding='driver-actions.reconciliation.next12']")?.textContent).toBe("-$84K");
    expect([...checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], shown), ...unboundDigits(container, periodLabels)]).toEqual([]);
  });

  it("an action's figures are the core's: a changed removal value is caught", () => {
    const c = computed("your-plan-actions");
    const wrong = structuredClone(c.report);
    if (!("joint_gain" in wrong.driver_actions)) throw new Error("no actions");
    wrong.driver_actions.items[0].removal_value["rest of fiscal year"] = "1.00" as never;
    const container = mountScreen(PlanScreen, { ...c, report: wrong }, c.company, c.scenario);
    const { expected, absent } = build(c);
    expect(checkBindings(container, expected, absent, [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], c).some((f) => f.startsWith("driver-actions.item.removal.rest"))).toBe(true);
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
