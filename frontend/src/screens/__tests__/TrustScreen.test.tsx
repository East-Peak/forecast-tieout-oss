import { cleanup } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { B, LISTED_BINDINGS } from "../trust/bindings";
import TrustScreen from "../trust/TrustScreen";
import * as files from "./files";
import { caseOf, mountScreen, runScreenChecks } from "./screenChecks";
import { build } from "./trustExpectations";

runScreenChecks({
  name: "Trust",
  Screen: TrustScreen,
  listFor: () => LISTED_BINDINGS,
  fullList: LISTED_BINDINGS,
  build,
  swap: { binding: B.sourceRows, to: B.monthsOfHistory.path },
  flip: (report) => {
    const flipped = structuredClone(report);
    const first = flipped.backtest.horizons[0];
    first.signed_bias["fitted model"] = `-${first.signed_bias["fitted model"]}` as never;
    return { report: flipped, ids: ["backtest.bias.fitted"] };
  },
  probe: "recon.source-rows",
  more: () => {
    describe("Trust: the screen's own claims", () => {
      it("both verdicts lead, with their reasons, as the report words them", () => {
        for (const company of files.COMPANIES) {
          const c = caseOf(company, "as-signed");
          const container = mountScreen(TrustScreen, c, c.company, c.scenario);
          const cards = container.querySelectorAll("[data-testid='verdict-card']");
          expect(cards.length).toBe(2);
          expect(cards[0].textContent).toContain(c.report.verdicts.software_correct.verdict);
          expect(cards[1].textContent).toContain(c.report.verdicts.forecast_better_than_baselines.reason);
          cleanup();
        }
      });

      it("a 'no' verdict is shown as no, with its reason, not softened (Mighty Oak's forecast is not better than the baselines)", () => {
        const c = caseOf("mighty-oak-holdings", "as-signed");
        const container = mountScreen(TrustScreen, c, c.company, c.scenario);
        expect(container.querySelector("[data-binding='verdict.better']")!.textContent).toBe("no");
        expect(container.querySelector("[data-binding='verdict.better.reason']")!.textContent).toMatch(/not lower than every baseline/);
      });

      it("every rate in the report is shown once, each with its definition, sample and source", () => {
        for (const [company, scenario] of [["sprout-labs", "as-signed"], ["mighty-oak-holdings", "demo-plan"]] as const) {
          const c = caseOf(company, scenario);
          const container = mountScreen(TrustScreen, c, c.company, c.scenario);
          const rows = container.querySelectorAll("[data-testid='rate-row']");
          expect(rows.length).toBe(c.report.rates.length);
          const names = Array.from(container.querySelectorAll("[data-binding='rate.name']")).map((el) => el.textContent);
          expect(new Set(names).size).toBe(names.length);
          expect(names).toEqual(c.report.rates.map((r) => r.name));
          expect(container.querySelectorAll("[data-binding='rate.sample']").length).toBe(rows.length);
          expect(container.querySelectorAll("[data-binding='rate.source']").length).toBe(rows.length);
          cleanup();
        }
      });

      it("a rate says its value in its own unit: a share as a percent, dollars as dollars, a number as a number", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const container = mountScreen(TrustScreen, c, c.company, c.scenario);
        const row = (name: string) => Array.from(container.querySelectorAll("[data-testid='rate-row']")).find((r) => r.querySelector("[data-binding='rate.name']")!.textContent === name)!;
        expect(row("new_pipeline_win_rate").querySelector("[data-binding='rate.value.share']")!.textContent).toBe("15.7%");
        expect(row("mean_won_arr").querySelector("[data-binding='rate.value.dollars']")!.textContent).toBe("$69,646");
        expect(row("median_won_cycle_days").querySelector("[data-binding='rate.value.number']")!.textContent).toBe("113");
      });

      it("the back-test table has both baselines and the fold counts, for each horizon", () => {
        const c = caseOf("sapling-industries", "as-signed");
        const container = mountScreen(TrustScreen, c, c.company, c.scenario);
        const rows = container.querySelectorAll("[data-testid='backtest-row']");
        expect(rows.length).toBe(c.report.backtest.horizons.length);
        for (const id of ["backtest.error.fitted", "backtest.error.stage", "backtest.error.run-rate", "backtest.folds"]) {
          expect(container.querySelectorAll(`[data-binding='${id}']`).length, id).toBe(rows.length);
        }
      });

      it("links to report.md and report.json for the scenario shown, under the published data folder", () => {
        const c = caseOf("mighty-oak-holdings", "hires-only");
        const container = mountScreen(TrustScreen, c, c.company, c.scenario);
        const md = container.querySelector("a[data-binding='files.report-md']")!;
        const json = container.querySelector("a[data-binding='files.report-json']")!;
        expect(md.getAttribute("href")).toBe("/data/reports/mighty-oak-holdings/hires-only.md");
        expect(json.getAttribute("href")).toBe("/data/reports/mighty-oak-holdings/hires-only.json");
        expect(md.getAttribute("data-source")).toBe("index");
      });

      it("a failed check is shown as failed, in red", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const report = structuredClone(c.report);
        report.reconciliation.checks[0].passed = false;
        const container = mountScreen(TrustScreen, { ...c, report }, c.company, c.scenario);
        const first = container.querySelector("[data-testid='reconciliation-check'] [data-testid='check-result']")!;
        expect(first.textContent).toBe("failed");
        expect(first.className).toMatch(/red/);
      });

      it("the excluded rows are listed in full on Mighty Oak and absent where nothing was excluded", () => {
        const mighty = caseOf("mighty-oak-holdings", "as-signed");
        const container = mountScreen(TrustScreen, mighty, mighty.company, mighty.scenario);
        expect(container.querySelectorAll("[data-testid='exclusion-row']").length).toBe(mighty.report.reconciliation.exclusions.length);
        expect(container.querySelectorAll("[data-testid='excluded-motion']").length).toBe(2);
        cleanup();
        const sprout = caseOf("sprout-labs", "as-signed");
        const none = mountScreen(TrustScreen, sprout, sprout.company, sprout.scenario);
        expect(none.querySelector("[data-testid='exclusion-row']")).toBeNull();
        expect(none.querySelector("[data-testid='excluded-motion']")).toBeNull();
      });
    });
  },
});
