import { describe, expect, it } from "vitest";
import type { TieoutReport } from "../../generated/report";
import { B, LISTED_BINDINGS } from "../capacity/bindings";
import CapacityScreen from "../capacity/CapacityScreen";
import { build } from "./capacityExpectations";
import { caseOf, mountScreen, runScreenChecks } from "./screenChecks";

runScreenChecks({
  name: "Capacity",
  Screen: CapacityScreen,
  listFor: () => LISTED_BINDINGS,
  fullList: LISTED_BINDINGS,
  build,
  swap: { binding: B.heads, to: B.departed.path },
  flip: (report) => {
    const flipped = structuredClone(report);
    const rc = flipped.roster_capacity.decision.horizons;
    rc[0].improvement = `-${rc[0].improvement}` as never;
    return { report: flipped, ids: ["horizon.improvement"] };
  },
  probe: "roster.heads",
  more: () => {
    describe("Capacity: the screen's own claims", () => {
      it("Mighty Oak says in words that hiring is unsupported by this history, with the reason, and shows no invented figure", () => {
        const c = caseOf("mighty-oak-holdings", "as-signed");
        const container = mountScreen(CapacityScreen, c, c.company, c.scenario);
        const banner = container.querySelector("[data-testid='capacity-not-used']")!;
        expect(banner.textContent).toContain("unsupported by this history");
        expect(banner.textContent).toContain(c.report.roster_capacity.decision.reason);
        // what was not adopted is not drawn as a forecast: the decision says "not shown", the rate is the flat trailing one
        expect(container.querySelector("[data-binding='decision.outcome']")!.textContent).toBe("not shown");
        expect(container.querySelector("[data-binding='decision.forecast-uses']")!.textContent).toBe("the flat trailing creation rate");
      });

      it("the deals created per ramped AE-month are shown to two places, not as six", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const container = mountScreen(CapacityScreen, c, c.company, c.scenario);
        expect(container.querySelector("[data-binding='creation.rate']")!.textContent).toBe("8.18");
        const m = caseOf("mighty-oak-holdings", "as-signed");
        expect(mountScreen(CapacityScreen, m, m.company, m.scenario).querySelector("[data-binding='creation.rate']")!.textContent).toBe("0.42");
      });

      it("a company where capacity is adopted shows no not-adopted banner", () => {
        for (const company of ["sprout-labs", "sapling-industries"]) {
          const c = caseOf(company, "as-signed");
          const container = mountScreen(CapacityScreen, c, c.company, c.scenario);
          expect(container.querySelector("[data-testid='capacity-not-used']"), company).toBeNull();
          expect(container.textContent).not.toContain("unsupported by this history");
        }
      });

      it("a roster that cannot be read says why in words and shows no headcount figures", () => {
        const c = caseOf("sprout-labs", "as-signed");
        const report = structuredClone(c.report);
        report.roster_capacity = {
          ...report.roster_capacity,
          roster: { rows: 0, unavailable: "team_members.csv has no quota-carrying rows" },
        } as TieoutReport["roster_capacity"];
        const container = mountScreen(CapacityScreen, { ...c, report }, c.company, c.scenario);
        expect(container.querySelector("[data-binding='roster.unavailable']")!.textContent).toBe("team_members.csv has no quota-carrying rows");
        expect(container.querySelector("[data-binding='roster.heads']")).toBeNull();
      });

      it("a quota that cannot be read says why in words, and no attainment is drawn", () => {
        const c = caseOf("sapling-industries", "as-signed");
        const report = structuredClone(c.report);
        report.quota_productivity = { unavailable: "no owner on any won deal", limits: ["owner is the current owner"] };
        const container = mountScreen(CapacityScreen, { ...c, report }, c.company, c.scenario);
        expect(container.querySelector("[data-binding='quota.unavailable']")!.textContent).toBe("no owner on any won deal");
        expect(container.querySelector("[data-binding='quota.attainment']")).toBeNull();
      });
    });
  },
});
