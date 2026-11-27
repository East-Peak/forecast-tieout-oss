import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { checkChart } from "../../binding/__tests__/harness";
import type { CapturedChart } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import PlanScreen from "../plan/PlanScreen";
import * as files from "./files";

const captured = vi.hoisted(() => [] as unknown[]);
vi.mock("recharts", async (importOriginal) => {
  const { withCapture } = await import("./rechartsCapture");
  return withCapture(await importOriginal<typeof import("recharts")>(), captured);
});
beforeEach(() => {
  captured.length = 0;
});
afterEach(cleanup);

const bridgeOf = (r: TieoutReport) => {
  if ("unavailable" in r.worksheet) throw new Error("no worksheet");
  return r.worksheet.bridge;
};

/** One small chart per step: the totals stand alone, an item floats from where the one above ended, the gap runs from the working plan to the target. */
function expectedRows(r: TieoutReport) {
  const b = bridgeOf(r);
  const working = b.steps.find((s) => s.kind === "working_plan")!;
  return b.steps.map((s, i) => ({
    period: String(i),
    total: s.kind === "as_signed" || s.kind === "working_plan" ? Number(s.to) : null,
    move: s.kind === "hires" || s.kind === "program" ? [Number(s.from), Number(s.to)] : null,
    gap: s.kind === "remaining_gap" ? [Number(working.to), Number(b.target.value)] : null,
  }));
}

function draw(company: string, scenario: string, report = files.report(company, scenario)): CapturedChart[] {
  captured.length = 0;
  render(
    <BindingProvider company={company} scenario={scenario} files={{ report, index: files.index(), comparison: files.comparison(company) }}>
      <PlanScreen />
    </BindingProvider>,
  );
  const last = new Map<string, CapturedChart>();
  for (const c of (captured as CapturedChart[]).filter((c) => c.series.some((s) => s.dataKey === "total"))) last.set(String((c.data as Array<{ period: string }>)[0].period), c);
  return [...last.values()];
}

function failures(got: CapturedChart[], r: TieoutReport): string[] {
  const want = expectedRows(r);
  if (got.length !== want.length) return [`${got.length} charts drawn, expected ${want.length}`];
  return want.flatMap((row, i) =>
    checkChart(`bridge step ${i}`, got[i], {
      data: [row],
      xKey: "period",
      series: ["total", "move", "gap"].map((dataKey) => ({ type: "Bar", dataKey })),
      referenceX: [String(Number(bridgeOf(r).target.value))],
    }),
  );
}

const PLANS = files.COMPANIES.flatMap((c) => (["demo-plan", "hires-only", "program-only"] as const).map((s) => [c, s] as const));

describe("the bridge's charts", () => {
  it.each(PLANS)("%s / %s: each step's bars are the report's from, to and target", (company, scenario) => {
    expect(failures(draw(company, scenario), files.report(company, scenario))).toEqual([]);
  });

  it.each(files.COMPANIES)("%s as signed: no plan, one line in words and no chart", (company) => {
    captured.length = 0;
    const { container } = render(
      <BindingProvider company={company} scenario="as-signed" files={{ report: files.report(company, "as-signed"), index: files.index(), comparison: files.comparison(company) }}>
        <PlanScreen />
      </BindingProvider>,
    );
    expect(container.querySelector("[data-testid='bridge-no-plan']")!.textContent).toMatch(/^No plan is in force/);
    expect(container.querySelector("[data-testid='bridge-table']")).toBeNull();
    expect((captured as CapturedChart[]).filter((c) => c.series.some((s) => s.dataKey === "total"))).toEqual([]);
  });

  describe("mutations are caught", () => {
    const base = () => files.report("sapling-industries", "demo-plan");
    it("pass when nothing is changed", () => expect(failures(draw("sapling-industries", "demo-plan"), base())).toEqual([]));
    it("a flipped sign is caught", () => {
      const report = structuredClone(base());
      const step = bridgeOf(report).steps[1];
      step.change = `-${step.change}` as never;
      step.from = `-${step.from}` as never;
      expect(failures(draw("sapling-industries", "demo-plan", report), base()).length).toBeGreaterThan(0);
    });
    it("another company's file is caught", () => expect(failures(draw("sprout-labs", "demo-plan"), base()).length).toBeGreaterThan(0));
    it("another scenario's file is caught", () => expect(failures(draw("sapling-industries", "hires-only"), base()).length).toBeGreaterThan(0));
    it("the bars of one step moved to another are caught", () => {
      const got = draw("sapling-industries", "demo-plan");
      [got[1].data, got[2].data] = [got[2].data, got[1].data];
      expect(failures(got, base()).some((f) => f.includes("data given"))).toBe(true);
    });
    it("a gap bar that starts at the as-signed amount rather than the working plan's is caught", () => {
      const got = draw("sapling-industries", "demo-plan");
      const last = (got[got.length - 1].data as Array<{ gap: [number, number] }>)[0];
      last.gap = [Number(bridgeOf(base()).steps[0].to), last.gap[1]];
      expect(failures(got, base()).some((f) => f.includes("data given"))).toBe(true);
    });
  });
});
