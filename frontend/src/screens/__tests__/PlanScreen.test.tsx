import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { unboundDigits } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import type { Loaders } from "../../session/ReportSession";
import { B, LISTED_BINDINGS } from "../plan/bindings";
import PlanScreen from "../plan/PlanScreen";
import * as files from "./files";
import * as fmt from "./independent";
import { build } from "./planExpectations";
import { caseOf, mountScreen, runScreenChecks } from "./screenChecks";

const fromDisk: Loaders = {
  index: () => Promise.resolve(files.index()),
  report: (path) => {
    const [company, file] = path.split("/");
    return Promise.resolve(files.report(company, file.replace(".json", "")));
  },
  comparison: (path) => Promise.resolve(files.comparison(path.split("/")[0])),
};

const fullPlan = (r: TieoutReport) => {
  if (!r.plan || "unavailable" in r.plan) throw new Error("no plan");
  return r.plan;
};

runScreenChecks({
  name: "Plan",
  Screen: PlanScreen,
  listFor: () => LISTED_BINDINGS,
  fullList: LISTED_BINDINGS,
  build,
  swap: { binding: B.closeGap, to: B.programmeCap.path },
  flip: (report) => {
    const flipped = structuredClone(report);
    const row = flipped.actions;
    if ("unavailable" in row) throw new Error("unavailable");
    row.close_the_fiscal_year_gap.fiscal_year_gap = `-${row.close_the_fiscal_year_gap.fiscal_year_gap}` as never;
    return { report: flipped, ids: ["close.gap"] };
  },
  probe: "close.gap",
  more: () => {
    describe("Plan: with no plan selected", () => {
      it("says there is no plan and invites picking one, and shows no figure for a plan (not zeros)", () => {
        for (const company of files.COMPANIES) {
          const c = caseOf(company, "as-signed");
          const container = mountScreen(PlanScreen, c, c.company, c.scenario);
          const note = container.querySelector("[data-testid='no-plan']")!;
          expect(note.textContent).toContain("There is no plan in this scenario");
          expect(note.textContent).toContain("Pick a scenario");
          for (const id of ["plan.expected", "plan.gap", "plan.gap-change", "item.label", "window.rest.with-plan", "items.cost"]) {
            expect(container.querySelector(`[data-binding='${id}']`), `${company} ${id}`).toBeNull();
          }
          cleanup();
        }
      });
    });

    describe("Plan: both windows, with ranges", () => {
      it("shows as signed against the scenario in both windows, with the plan's range and the as-signed range, ranges as the report's pairs", () => {
        const c = caseOf("sapling-industries", "demo-plan");
        const container = mountScreen(PlanScreen, c, c.company, c.scenario);
        const plan = fullPlan(c.report);
        const text = (id: string) => container.querySelector(`[data-binding='${id}']`)!.textContent;
        expect(text("window.rest.as-signed")).toBe(fmt.usdShort(plan.baseline["rest of fiscal year"]));
        expect(text("window.next12.with-plan")).toBe(fmt.usdShort(plan.with_plan["next twelve months"]));
        const range = plan.ranges.bookings_in_window["next twelve months"].range80;
        expect(text("window.next12.with-plan.range80.low")).toBe(fmt.usdShort(range[0]));
        expect(text("window.next12.with-plan.range80.high")).toBe(fmt.usdShort(range[1]));
        expect(container.querySelectorAll("[data-testid='window-row']").length).toBe(2);
      });

      it("the gain in each window is the comparison file's figure, which is the core's own difference", () => {
        for (const company of files.COMPANIES) {
          const c = caseOf(company, "demo-plan");
          const container = mountScreen(PlanScreen, c, c.company, c.scenario);
          const row = c.comparison.rows.find((x) => x.scenario === "demo-plan")!;
          const gain = container.querySelector("[data-binding='window.rest.gain']")!;
          expect(gain.getAttribute("data-source")).toBe("comparison");
          expect(gain.textContent).toBe(fmt.usdShort(row.bookings_change!["rest of fiscal year"]));
          expect(gain.textContent).toBe(fmt.usdShort(fullPlan(c.report).difference["rest of fiscal year"]));
          cleanup();
        }
      });
    });

    describe("Plan: what the report cannot value is said in words", () => {
      it("Mighty Oak's unsupported hires are said so in words, in the items, the actions and what closes the gap", () => {
        const c = caseOf("mighty-oak-holdings", "demo-plan");
        const container = mountScreen(PlanScreen, c, c.company, c.scenario);
        const text = container.textContent ?? "";
        expect(text).toContain("unsupported by this history");
        const hires = Array.from(container.querySelectorAll("[data-testid='plan-item-row']")).filter((row) => /hire/i.test(row.textContent ?? ""));
        expect(hires.length).toBeGreaterThan(0);
        for (const row of hires) expect(row.textContent).toContain("unsupported by this history");
        expect(container.querySelector("[data-binding='close.hires.outcome']")!.textContent).toBe("unsupported by this history");
        expect(container.querySelector("[data-binding='close.programme.outcome']")!.textContent).toBe("unreachable");
        const unsupported = Array.from(container.querySelectorAll("[data-testid='action-row']")).find((row) => /Hire/.test(row.textContent ?? ""))!;
        expect(unsupported.textContent).toContain("unsupported by this history");
        expect(unsupported.textContent).not.toMatch(/\$0(?![\d.,KM])/);
        // not a ranked action: no rank, no per-dollar figure
        expect(unsupported.querySelector("[data-binding='action.rank']")!.textContent).toBe("not ranked");
        expect(container.querySelector("[data-testid='better-per-dollar']")!.textContent).toContain("Add $");
      });

      it("a plan with items the history cannot value says that the totals are for the valued ones; a fully valued plan does not", () => {
        for (const [company, scenario, unvalued] of [["mighty-oak-holdings", "demo-plan", true], ["mighty-oak-holdings", "hires-only", true], ["sprout-labs", "demo-plan", false]] as const) {
          const c = caseOf(company, scenario);
          const container = mountScreen(PlanScreen, c, c.company, c.scenario);
          expect(container.querySelector("[data-testid='unvalued-note']") !== null, `${company} ${scenario}`).toBe(unvalued);
          cleanup();
        }
      });

      it("a plan that cannot be valued says why and shows no plan figure", () => {
        const c = caseOf("sprout-labs", "demo-plan");
        const report = structuredClone(c.report);
        report.plan = { unavailable: "no close-timing evidence" };
        const container = mountScreen(PlanScreen, { ...c, report }, c.company, c.scenario);
        expect(container.querySelector("[data-binding='plan.unavailable']")!.textContent).toBe("no close-timing evidence");
        expect(container.querySelector("[data-binding='plan.expected']")).toBeNull();
        expect(container.querySelector("[data-testid='no-plan']")).toBeNull();
      });

      it("two actions that cannot be compared say why and show no figure", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const report = structuredClone(c.report);
        report.actions = { unavailable: "no close-timing evidence" };
        const container = mountScreen(PlanScreen, { ...c, report }, c.company, c.scenario);
        expect(container.querySelector("[data-binding='actions.unavailable']")!.textContent).toBe("no close-timing evidence");
        expect(container.querySelector("[data-testid='action-row']")).toBeNull();
      });
    });

    describe("Plan: scenario switching, through the whole app", () => {
      it("choosing a scenario in the page loads its report and moves the whole screen, and back again", async () => {
        render(
          <MemoryRouter initialEntries={["/plan?company=sapling-industries&scenario=as-signed"]}>
            <App loaders={fromDisk} />
          </MemoryRouter>,
        );
        await waitFor(() => expect(screen.getByTestId("no-plan")).toBeInTheDocument());
        const press = (id: string) => fireEvent.click(document.querySelector(`[data-scenario-id='${id}']`)!);
        const gap = () => document.querySelector("[data-binding='plan.gap']")?.textContent;

        press("demo-plan");
        await waitFor(() => expect(gap()).toBeDefined());
        const demo = files.report("sapling-industries", "demo-plan");
        expect(gap()).toBe(fmt.usdShort(fullPlan(demo).gap.fiscal_year.gap_with_plan));
        expect(document.querySelector("[data-scenario-id='demo-plan']")!.getAttribute("aria-pressed")).toBe("true");
        expect(document.querySelectorAll("[data-testid='plan-item-row']").length).toBe(fullPlan(demo).items.length);
        expect((document.getElementById("scenario-selector") as HTMLSelectElement).value).toBe("demo-plan");

        press("hires-only");
        await waitFor(() => expect(document.querySelector("[data-scenario-id='hires-only']")!.getAttribute("aria-pressed")).toBe("true"));
        await waitFor(() => expect(document.querySelectorAll("[data-testid='plan-item-row']").length).toBe(fullPlan(files.report("sapling-industries", "hires-only")).items.length));
        expect(gap()).toBe(fmt.usdShort(fullPlan(files.report("sapling-industries", "hires-only")).gap.fiscal_year.gap_with_plan));
        expect(gap()).not.toBe(fmt.usdShort(fullPlan(demo).gap.fiscal_year.gap_with_plan));
        expect(unboundDigits(document.body)).toEqual([]);

        press("as-signed");
        await waitFor(() => expect(screen.getByTestId("no-plan")).toBeInTheDocument());
        expect(document.querySelector("[data-binding='plan.gap']")).toBeNull();
        cleanup();
      });
    });
  },
});
