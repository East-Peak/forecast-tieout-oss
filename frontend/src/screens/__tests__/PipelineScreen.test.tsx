import { describe, expect, it } from "vitest";
import type { TieoutReport } from "../../generated/report";
import { B, LISTED_BINDINGS } from "../pipeline/bindings";
import PipelineScreen from "../pipeline/PipelineScreen";
import { build } from "./pipelineExpectations";
import { caseOf, mountScreen, runScreenChecks } from "./screenChecks";

const quarterOf = (report: TieoutReport, name: string) => {
  const rp = report.required_pipeline;
  if ("unavailable" in rp) throw new Error("unavailable");
  return rp.quarters.find((q) => q.quarter === name)!;
};

runScreenChecks({
  name: "Pipeline",
  Screen: PipelineScreen,
  listFor: () => LISTED_BINDINGS,
  fullList: LISTED_BINDINGS,
  build,
  swap: { binding: B.fySolvableTotal, to: B.cap.path },
  flip: (report) => {
    const flipped = structuredClone(report);
    const rp = flipped.required_pipeline;
    if ("unavailable" in rp) throw new Error("unavailable");
    const q = rp.quarters.find((x) => x.outcome === "feasible")!;
    q.required_extra_pipeline = `-${q.required_extra_pipeline}` as never;
    return { report: flipped, ids: ["quarter.required"] };
  },
  probe: "quarter.target",
  more: () => {
    describe("Pipeline: the screen's own claims", () => {
      it("shows each too-late reason as a plain sentence, never a code", () => {
        for (const company of ["sprout-labs", "mighty-oak-holdings"]) {
          const c = caseOf(company, "as-signed");
          const container = mountScreen(PipelineScreen, c, c.company, c.scenario);
          const panels = container.querySelectorAll("[data-testid='too-late']");
          expect(panels.length, company).toBeGreaterThan(0);
          for (const code of ["over_cap", "total_rate", "per_rep"]) expect(container.textContent, code).not.toContain(code);
          const shown = Array.from(container.querySelectorAll("[data-binding='late.reason']")).map((el) => el.textContent);
          const rp = c.report.required_pipeline;
          if ("unavailable" in rp) throw new Error("unavailable");
          expect(shown).toEqual(rp.quarters.flatMap((q) => q.too_late.reasons));
          // a sentence says what is needed or what is over, not a bare code
          for (const sentence of shown) expect(sentence).toMatch(/\s/);
        }
      });

      it("an unreachable quarter reads as a shortfall that remains, never as a negative requirement", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const q = quarterOf(c.report, "Q3FY26");
        expect(q.outcome).toBe("unreachable within bounds");
        expect(Number(q.surplus_over_target)).toBeLessThan(0);
        const container = mountScreen(PipelineScreen, c, c.company, c.scenario);
        const said = container.querySelector("[data-binding='quarter.surplus']")!.textContent!;
        expect(said).toMatch(/^still short of target by \$/);
        expect(said).not.toMatch(/-\$|-\d/);
        // and the requirement column says that no amount helps, not a number
        const required = container.querySelector("[data-binding='quarter.required.none']")!;
        expect(required.textContent).toBe("no amount helps within the cap");
      });

      it("a quarter already covered says so in words, and is not shown as a zero requirement", () => {
        const c = caseOf("sapling-industries", "as-signed");
        const container = mountScreen(PipelineScreen, c, c.company, c.scenario);
        const el = container.querySelector("[data-binding='quarter.required.covered']")!;
        expect(el.textContent).toBe("none needed: already covered");
        expect(el.getAttribute("data-unavailable")).toBe("true");
        expect(container.querySelector("[data-binding='quarter.surplus']")!.textContent).toMatch(/^ahead of target by \$/);
      });

      it("a requirement that cannot be computed says why in words and shows no solved figure", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const report = structuredClone(c.report);
        report.required_pipeline = { unavailable: "the fitted forecast is unavailable (short history)" };
        const container = mountScreen(PipelineScreen, { ...c, report }, c.company, c.scenario);
        expect(container.querySelector("[data-binding='required.unavailable']")!.textContent).toBe("the fitted forecast is unavailable (short history)");
        expect(container.querySelector("[data-binding='required.solvable-total']")).toBeNull();
        expect(container.querySelector("[data-binding='flow.count']")).not.toBeNull(); // the year's flow is still shown
      });

      it("the stage win rates carry their sample sizes, and no age-group cell is shown as a stage", () => {
        const c = caseOf("sapling-industries", "as-signed");
        const container = mountScreen(PipelineScreen, c, c.company, c.scenario);
        const rows = container.querySelectorAll("[data-testid='win-rate-row']");
        const stage = c.report.rates.filter((r) => /^win_within_horizon:[^:]+$/.test(r.name)).length;
        expect(rows.length).toBe(stage + 1); // the stages and the new-pipeline win rate
        expect(container.querySelectorAll("[data-binding='rate.sample']").length).toBe(rows.length);
      });
    });
  },
});
