import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../../App";
import { openAll, unboundDigits } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import type { Loaders } from "../../session/ReportSession";
import { B, LISTED_BINDINGS, W } from "../plan/bindings";
import { WORKSHEET_BINDINGS } from "../plan/worksheetBindings";
import PlanScreen from "../plan/PlanScreen";
import * as files from "./files";
import * as fmt from "./independent";
import { build } from "./planExpectations";
import { caseOf, mountScreen, runScreenChecks } from "./screenChecks";

// recharts draws nothing without a measured box (jsdom has none): its container is given a size, and the figures printed at the bars' ends then exist
vi.mock("recharts", async (importOriginal) => {
  const { withCapture } = await import("./rechartsCapture");
  return withCapture(await importOriginal<typeof import("recharts")>(), []);
});

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
  listFor: () => [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS],
  fullList: [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS],
  build,
  swap: { binding: B.closeGap, to: B.programCap.path },
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
      it("says there is no plan in the report's words and invites building one, and shows no figure for a plan (not zeros)", () => {
        for (const company of files.COMPANIES) {
          const c = caseOf(company, "as-signed");
          const container = mountScreen(PlanScreen, c, c.company, c.scenario);
          const note = container.querySelector("[data-testid='no-plan']")!;
          expect(note.textContent).toContain(c.report.worksheet && "summary" in c.report.worksheet ? c.report.worksheet.summary.no_plan_note : "");
          expect(note.textContent).toContain("Pick a scenario");
          for (const id of ["worksheet.summary.twelve-month-gain", "worksheet.summary.cash-cost", "item.label", "window.rest.with-plan", "items.cost"]) {
            expect(container.querySelector(`[data-binding='${id}']`), `${company} ${id}`).toBeNull();
          }
          cleanup();
        }
      });
    });

    describe("Plan: the two windows swapped in the bindings is caught", () => {
      it("a screen that reads the next twelve months where it says the rest of the year fails", () => {
        const c = caseOf("sapling-industries", "demo-plan");
        const keys = Object.keys(W.rest) as Array<keyof typeof W.rest>;
        const swap = () => {
          for (const key of keys) {
            const a = W.rest[key] as { path: string };
            const b = W.next12[key] as { path: string };
            [a.path, b.path] = [b.path, a.path];
          }
        };
        swap();
        try {
          const container = mountScreen(PlanScreen, c, c.company, c.scenario);
          const failures = build(c).expected
            .filter((e) => e.id.startsWith("window.rest.as-signed") || e.id.startsWith("window.next12.with-plan"))
            .map((e) => container.querySelector(`[data-binding='${e.id}']`)?.textContent === e.texts[0]);
          expect(failures.includes(false), "the swapped windows show the wrong figure").toBe(true);
        } finally {
          swap();
        }
      });
    });

    describe("Plan: a missing cost says why, from the report's own outcome and cost status", () => {
      const costText = (company: string, id: string, edit?: (r: TieoutReport) => void) => {
        const c = caseOf(company, "as-signed");
        const report = structuredClone(c.report);
        edit?.(report);
        const container = mountScreen(PlanScreen, { ...c, report }, c.company, c.scenario);
        const text = container.querySelector(`[data-binding='${id}']`)!.textContent;
        cleanup();
        return text;
      };
      const closing = (r: TieoutReport) => {
        if ("unavailable" in r.actions) throw new Error("unavailable");
        return r.actions.close_the_fiscal_year_gap;
      };

      it("unreachable hires whose cost was entered do not say the cost was missing", () => {
        for (const company of ["sprout-labs", "sapling-industries"]) {
          const said = costText(company, "close.hires.cost");
          expect(said, company).toMatch(/^no cost: no number of hires closes the gap/);
          expect(said).not.toMatch(/not entered/);
        }
      });

      it("a cost that was not entered says so", () => {
        const said = costText("sprout-labs", "close.hires.cost", (r) => {
          const h = closing(r).hires;
          if (!("bound" in h)) throw new Error("hires not solved");
          h.cost_status = "cost not entered";
          h.cash_cost_note = "cost not entered";
        });
        expect(said).toBe("cost not entered");
      });

      it("hires already covered say nothing needs adding", () => {
        const said = costText("sprout-labs", "close.hires.cost", (r) => {
          const h = closing(r).hires;
          if (!("bound" in h)) throw new Error("hires not solved");
          h.outcome = "already covered";
          h.count = 0 as never;
          h.cash_cost_note = "no cost: the gap is already covered, so nothing needs adding";
        });
        expect(said).toMatch(/already covered/);
      });

      it("a program that cannot close the gap says no amount does, and Mighty Oak's says it is over the cap", () => {
        const c = caseOf("mighty-oak-holdings", "as-signed");
        const container = mountScreen(PlanScreen, c, c.company, c.scenario);
        expect(container.querySelector("[data-binding='close.program.cost']")!.textContent).toMatch(/^no cost: no amount of pipeline closes the gap/);
        const program = container.querySelector("[data-testid='close-program']")!.textContent!;
        expect(program).toMatch(/Over the cap: closing it would take \$3\.0B, against a cap of \$2\.4B/);
        expect(program).not.toMatch(/not over the cap/);
        cleanup();
        const sprout = caseOf("sprout-labs", "as-signed");
        const ok = mountScreen(PlanScreen, sprout, sprout.company, sprout.scenario).querySelector("[data-testid='close-program']")!.textContent!;
        expect(ok).toMatch(/Within the cap of \$111\.7M/);
      });
    });

    describe("Plan: what could not be valued is not a zero", () => {
      it("Mighty Oak's hires-only scenario shows words, not $0, with the reason in words and the table saying so too", () => {
        const c = caseOf("mighty-oak-holdings", "hires-only");
        const container = mountScreen(PlanScreen, c, c.company, c.scenario);
        const text = (id: string) => container.querySelector(`[data-binding='${id}']`)!.textContent;
        expect(text("worksheet.summary.twelve-month-gain.not-valued")).toBe("not valued");
        expect(text("window.rest.gain")).toBe("not valued");
        expect(text("items.total.rest")).toBe("not valued");
        expect(container.querySelector("[data-testid='unvalued-note']")!.textContent).toMatch(/^no item in this plan is valued: hiring is unsupported by this history/);
        const row = Array.from(container.querySelectorAll("[data-testid='compare-row']")).find((r) => r.textContent?.includes("Hires only"))!;
        expect(row.textContent).toContain("not valued");
        expect(row.textContent).not.toMatch(/\$0(?![\d.,KM])/);
      });

      it("a partly valued plan keeps its figure and names what it leaves out", () => {
        const c = caseOf("mighty-oak-holdings", "demo-plan");
        const container = mountScreen(PlanScreen, c, c.company, c.scenario);
        expect(container.querySelector("[data-binding='worksheet.summary.twelve-month-gain']")!.textContent).toBe("$1.6M");
        expect(container.querySelector("[data-testid='unvalued-note']")!.textContent).toMatch(/leave out what cannot be valued: 4 Mid-Market hires/);
      });

      it("segment names read as words", () => {
        const c = caseOf("sprout-labs", "demo-plan");
        const container = mountScreen(PlanScreen, c, c.company, c.scenario);
        expect(container.textContent).not.toMatch(/mid_market|_market/);
        expect(container.textContent).toMatch(/Mid Market/);
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
        expect(container.querySelector("[data-binding='close.program.outcome']")!.textContent).toBe("unreachable");
        const unsupported = container.querySelector("[data-testid='worksheet-action-row'][data-kind='hire']")!;
        expect(unsupported.textContent).toContain("unsupported by this history");
        expect(unsupported.textContent).not.toMatch(/\$0(?![\d.,KM])/);
        // not a ranked action: no rank, no per-dollar figure, said in the opened details
        const details = container.querySelector("[data-testid='action-detail']")!.parentElement!;
        expect(Array.from(container.querySelectorAll("[data-testid='action-detail']")).some((d) => d.querySelector("[data-binding='action.rank']")?.textContent === "not ranked"), details.textContent ?? "").toBe(true);
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
        expect(container.querySelector("[data-binding='window.rest.with-plan']")).toBeNull();
        expect(container.querySelector("[data-testid='no-plan']")).toBeNull();
      });

      it("two actions that cannot be compared say why and show no figure", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const report = structuredClone(c.report);
        report.actions = { unavailable: "no close-timing evidence" };
        const container = mountScreen(PlanScreen, { ...c, report }, c.company, c.scenario);
        expect(container.querySelector("[data-binding='actions.unavailable']")!.textContent).toBe("no close-timing evidence");
        expect(container.querySelector("[data-testid='action-figures']")).toBeNull();
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
        // the ledger is closed on a phone-sized window (and so here): open it to count the items
        const opened = () => {
          openAll(document.body);
          return document.querySelectorAll("[data-testid='plan-item-row']");
        };
        const gap = () => document.querySelector("[data-binding='worksheet.summary.remaining-gap']")?.textContent;

        press("demo-plan");
        await waitFor(() => expect(gap()).toBeDefined());
        const demo = files.report("sapling-industries", "demo-plan");
        expect(gap()).toBe(fmt.usdShort(fullPlan(demo).gap.fiscal_year.gap_with_plan));
        expect(document.querySelector("[data-scenario-id='demo-plan']")!.getAttribute("aria-pressed")).toBe("true");
        expect(opened().length).toBe(fullPlan(demo).items.length);
        expect((document.getElementById("scenario-selector") as HTMLSelectElement).value).toBe("demo-plan");

        press("hires-only");
        await waitFor(() => expect(document.querySelector("[data-scenario-id='hires-only']")!.getAttribute("aria-pressed")).toBe("true"));
        await waitFor(() => expect(opened().length).toBe(fullPlan(files.report("sapling-industries", "hires-only")).items.length));
        expect(gap()).toBe(fmt.usdShort(fullPlan(files.report("sapling-industries", "hires-only")).gap.fiscal_year.gap_with_plan));
        expect(gap()).not.toBe(fmt.usdShort(fullPlan(demo).gap.fiscal_year.gap_with_plan));
        expect(unboundDigits(document.body)).toEqual([]);

        press("as-signed");
        await waitFor(() => expect(screen.getByTestId("no-plan")).toBeInTheDocument());
        expect(document.querySelector("[data-binding='worksheet.summary.twelve-month-gain']")).toBeNull();
        cleanup();
      });
    });
  },
});
