import { describe, expect, it } from "vitest";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { EditorFailure } from "../client";
import type { EditorStatus } from "../client";
import type { ApplyOutcome, ComparisonRow, Facts, PlanDoc } from "../protocol";
import { YourPlanStore } from "../store";
import { YOUR_PLAN, withYourPlan, withYourPlanRow } from "../yourPlan";

const DEMO: PlanDoc = { hires: [{ segment: "mid_market", start: "2026-10", count: 2 }], programs: [{ name: "P", pipeline: 5, start: "2026-10", ramp_months: 3 }] };
const factsOf = (company: string): Facts => ({ company, segments: [{ value: "mid_market", label: "Mid Market" }], months: ["2026-09"], max_dollars: "9", demo_plan: DEMO });
const reportOf = (tag: string) => ({ tag }) as unknown as TieoutReport;
const rowOf = (tag: string) => ({ scenario: YOUR_PLAN, label: tag }) as unknown as ComparisonRow;

/** A stand-in for the client that records what it was asked and answers from a queue. */
class FakeEditor {
  status: EditorStatus = { phase: "idle" };
  calls: string[] = [];
  outcomes: Array<ApplyOutcome | Error> = [];
  applied: PlanDoc[] = [];
  private listeners = new Set<() => void>();
  subscribe = (l: () => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };
  open(company: string) {
    this.calls.push(`open ${company}`);
    return Promise.resolve(factsOf(company));
  }
  apply(company: string, plan: PlanDoc) {
    this.calls.push(`apply ${company}`);
    this.applied.push(plan);
    const next = this.outcomes.shift() ?? { kind: "report" as const, report: reportOf("demo"), comparison: rowOf("demo") };
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  }
}

const make = () => {
  const editor = new FakeEditor();
  return { editor, store: new YourPlanStore(editor) };
};

describe("the first time a company's plan is shown", () => {
  it("opens the company, computes the demo plan's items, and starts the form from them", async () => {
    const { editor, store } = make();
    const shown = await store.load("acme");
    expect(editor.calls).toEqual(["open acme", "apply acme"]);
    expect(editor.applied[0]).toEqual(DEMO);
    expect(shown.report).toEqual(reportOf("demo"));
    expect(store.snapshot.drafts.acme).toEqual(DEMO);
    expect(store.snapshot.facts.acme).toEqual(factsOf("acme"));
  });

  it("starts the form from a copy, so editing it never changes the demo plan", async () => {
    const { store } = make();
    await store.load("acme");
    store.snapshot.drafts.acme.hires[0].count = 9;
    expect(store.snapshot.facts.acme.demo_plan.hires[0].count).toBe(2);
  });

  it("shows what was applied last, without touching the worker, when the company comes back", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.calls.length = 0;
    await expect(store.load("acme")).resolves.toMatchObject({ report: reportOf("demo") });
    expect(editor.calls).toEqual([]);
  });

  it("fails the load when the demo plan itself is not accepted, rather than showing nothing", async () => {
    const { editor, store } = make();
    editor.outcomes.push({ kind: "invalid", errors: [{ section: "hires", index: 1, position: 0, message: "hires[1]: no" }] });
    await expect(store.load("acme")).rejects.toThrow(/hires\[1\]: no/);
  });
});

describe("Apply", () => {
  it("computes the form's plan, keeps it, and says nothing is wrong", async () => {
    const { editor, store } = make();
    await store.load("acme");
    store.setDraft("acme", { ...DEMO, hires: [] });
    editor.outcomes.push({ kind: "report", report: reportOf("edited"), comparison: rowOf("edited") });
    await store.apply("acme");
    expect(editor.applied.slice(-1)[0]).toEqual({ ...DEMO, hires: [] });
    expect(store.snapshot.applied.acme.report).toEqual(reportOf("edited"));
    expect(store.snapshot.applied.acme.plan).toEqual({ ...DEMO, hires: [] });
    expect(store.snapshot.feedback).toEqual({ errors: [], problems: [], failure: null, busy: false });
  });

  it("keeps the last good report and shows the core's words when it refuses the plan", async () => {
    const { editor, store } = make();
    await store.load("acme");
    const errors = [{ section: "programs" as const, index: 1, position: 0, message: "programs[1]: pipeline must be more than 0" }];
    editor.outcomes.push({ kind: "invalid", errors });
    await store.apply("acme");
    expect(store.snapshot.applied.acme.report).toEqual(reportOf("demo"));
    expect(store.snapshot.feedback.errors).toEqual(errors);
  });

  it("shows a report that failed its checks as problems and keeps the last good one", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.outcomes.push({ kind: "refused", problems: ["/plan: wrong"] });
    await store.apply("acme");
    expect(store.snapshot.feedback.problems).toEqual(["/plan: wrong"]);
    expect(store.snapshot.applied.acme.report).toEqual(reportOf("demo"));
  });

  it("shows a timeout or a crash as a failure, ready to be tried again", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.outcomes.push(new EditorFailure("timeout", "no answer within the time allowed"));
    await store.apply("acme");
    expect(store.snapshot.feedback.failure).toEqual({ kind: "timeout", message: "no answer within the time allowed" });
    expect(store.snapshot.feedback.busy).toBe(false);
    await store.apply("acme");
    expect(store.snapshot.feedback.failure).toBeNull();
  });

  it("is busy while the worker computes, and a company's plans do not touch another's", async () => {
    const { editor, store } = make();
    await store.load("acme");
    await store.load("birch");
    editor.outcomes.push({ kind: "report", report: reportOf("acme-edited"), comparison: rowOf("a") });
    const pending = store.apply("acme");
    expect(store.snapshot.feedback.busy).toBe(true);
    await pending;
    expect(store.snapshot.applied.birch.report).toEqual(reportOf("demo"));
  });

  it("tells its subscribers whenever what the screen shows changes", async () => {
    const { store } = make();
    let heard = false;
    store.subscribe(() => {
      heard = true;
    });
    await store.load("acme");
    expect(heard).toBe(true);
  });
});

describe("the choice and the rows", () => {
  const index = { schema_version: "1", default_company: "a", companies: [{ id: "a", scenarios: [{ id: "as-signed" }] }, { id: "b", scenarios: [] }] } as unknown as ReportIndex;

  it("adds Your plan after the named scenarios of every company", () => {
    const withIt = withYourPlan(index);
    for (const c of withIt.companies) expect(c.scenarios.slice(-1)[0]).toMatchObject({ id: YOUR_PLAN, label: "Your plan", plan_file: null });
    expect(withIt.companies[0].scenarios.map((s) => s.id)).toEqual(["as-signed", YOUR_PLAN]);
    expect(index.companies[0].scenarios).toHaveLength(1);
  });

  it("puts the computed row last in the comparison, replacing an earlier one", () => {
    const base = { company: "a", as_of: "x", baseline: "as-signed", rows: [{ scenario: "as-signed" }] } as unknown as ScenarioComparison;
    const once = withYourPlanRow(base, rowOf("one"));
    const twice = withYourPlanRow(once, rowOf("two"));
    expect(twice.rows.map((r) => r.scenario)).toEqual(["as-signed", YOUR_PLAN]);
    expect(twice.rows.slice(-1)[0]?.label).toBe("two");
  });
});
