import { describe, expect, it } from "vitest";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { EditorFailure } from "../client";
import type { EditorStatus } from "../client";
import type { ApplyOutcome, ComparisonRow, Facts, LanesOutcome, PlanDoc } from "../protocol";
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
  /** the revision the next report is given: every Apply that makes a report is a new one */
  revision = 0;
  async apply(company: string, plan: PlanDoc) {
    this.calls.push(`apply ${company}`);
    this.applied.push(plan);
    const next = this.outcomes.shift() ?? { kind: "report" as const, report: reportOf("demo"), comparison: rowOf("demo"), revision: 0 };
    if (next instanceof Error) throw next;
    return next.kind === "report" ? { ...next, revision: ++this.revision } : next;
  }
  /** the lanes asked for, each held until the test answers it */
  lanesCalls: Array<{ company: string; revision: number; resolve: (o: LanesOutcome) => void; reject: (e: Error) => void }> = [];
  lanes(company: string, revision: number) {
    return new Promise<LanesOutcome>((resolve, reject) => this.lanesCalls.push({ company, revision, resolve, reject }));
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
    editor.outcomes.push({ kind: "report", report: reportOf("edited"), comparison: rowOf("edited"), revision: 0 });
    await store.apply("acme");
    expect(editor.applied.slice(-1)[0]).toEqual({ ...DEMO, hires: [] });
    expect(store.snapshot.applied.acme.report).toEqual(reportOf("edited"));
    expect(store.snapshot.applied.acme.plan).toEqual({ ...DEMO, hires: [] });
    expect(store.snapshot.feedback).toEqual({ company: null, errors: [], problems: [], failure: null, busy: false });
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
    editor.outcomes.push({ kind: "report", report: reportOf("acme-edited"), comparison: rowOf("a"), revision: 0 });
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

const LANES = (tag: string): LanesOutcome => ({ kind: "lanes", lanes: { tag } as never, owners: { enterprise: { tag } as never } });
const tick = () => new Promise((r) => setTimeout(r, 0));

describe("the lanes of an Apply", () => {
  it("are pending with the report, asked for by the Apply's revision, and ready when the worker answers", async () => {
    const { editor, store } = make();
    await store.load("acme");
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "pending" });
    expect(editor.lanesCalls.map((c) => [c.company, c.revision])).toEqual([["acme", store.snapshot.applied.acme.revision]]);
    editor.lanesCalls[0].resolve(LANES("one"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "ready", lanes: { tag: "one" }, owners: { enterprise: { tag: "one" } } });
  });

  it("an answer for an earlier Apply of the company is dropped: the later Apply's lanes stay pending", async () => {
    const { editor, store } = make();
    await store.load("acme");
    store.setDraft("acme", { ...DEMO, hires: [] });
    await store.apply("acme");
    expect(editor.lanesCalls).toHaveLength(2);
    editor.lanesCalls[0].resolve(LANES("old"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "pending" });
    editor.lanesCalls[1].resolve(LANES("new"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toMatchObject({ status: "ready", lanes: { tag: "new" } });
  });

  it("belong to their company: one company's answer does not touch another's", async () => {
    const { editor, store } = make();
    await store.load("acme");
    await store.load("birch");
    editor.lanesCalls.find((c) => c.company === "acme")!.resolve(LANES("acme's"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toMatchObject({ status: "ready", lanes: { tag: "acme's" } });
    expect(store.snapshot.applied.birch.lanes).toEqual({ status: "pending" });
  });

  it("a refusal or a failure is the lanes' own state: the report stays", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.lanesCalls[0].resolve({ kind: "refused", problems: ["goals would move"] });
    await tick();
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "failed", message: "goals would move" });
    expect(store.snapshot.applied.acme.report).toEqual(reportOf("demo"));
    store.setDraft("acme", { ...DEMO, hires: [] });
    await store.apply("acme");
    editor.lanesCalls[1].reject(new EditorFailure("timeout", "no answer within the time allowed"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "failed", message: "no answer within the time allowed" });
  });

  it("a worker that had moved on is the lanes' failure, in words that say what to do; the report stays", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.lanesCalls[0].resolve({ kind: "stale" });
    await tick();
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "failed", message: expect.stringMatching(/apply the plan again/) });
    expect(store.snapshot.applied.acme.report).toEqual(reportOf("demo"));
  });

  it("a request replaced by a newer one for lanes changes nothing: the newer one is what is shown", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.lanesCalls[0].reject(new EditorFailure("superseded", "replaced"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toEqual({ status: "pending" });
  });

  it("an Apply that is refused leaves the report and its lanes alone, so the lanes still arrive", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.outcomes.push({ kind: "invalid", errors: [{ section: "hires", index: 1, position: 0, message: "hires[1]: no" }] });
    await store.apply("acme");
    expect(editor.lanesCalls).toHaveLength(1);
    editor.lanesCalls[0].resolve(LANES("kept"));
    await tick();
    expect(store.snapshot.applied.acme.lanes).toMatchObject({ status: "ready", lanes: { tag: "kept" } });
  });
});

describe("what the form shows belongs to its company and its own Apply", () => {
  it("does not carry one company's refusal over to another company's form", async () => {
    const { editor, store } = make();
    await store.load("acme");
    await store.load("birch");
    editor.outcomes.push({ kind: "invalid", errors: [{ section: "hires", index: 1, position: 0, message: "hires[1]: no" }] });
    await store.apply("acme");
    expect(store.snapshot.feedback.company).toBe("acme");
  });

  it("is not left busy when its Apply was replaced by a load that then failed", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.outcomes.push(new EditorFailure("superseded", "replaced"));
    await store.apply("acme");
    expect(store.snapshot.feedback.busy).toBe(false);
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

describe("adding one unit of an action to the plan (from the tornado)", () => {
  it("asked before the editor has loaded, the item is appended to the form once it has, and not applied", async () => {
    const { editor, store } = make();
    store.append("acme", "hire");
    await store.load("acme");
    expect(store.snapshot.drafts.acme.hires).toEqual([...DEMO.hires, { segment: "mid_market", start: "2026-09", count: 1 }]);
    expect(editor.applied).toEqual([DEMO]);
  });

  it("asked with the editor already loaded, it is appended to the form as it stands", async () => {
    const { store } = make();
    await store.load("acme");
    store.append("acme", "program");
    expect(store.snapshot.drafts.acme.programs).toEqual([...DEMO.programs, { name: "Program pipeline", pipeline: 1000000, start: "2026-09" }]);
  });

  it("is asked for one company and leaves another's form alone", async () => {
    const { store } = make();
    store.append("acme", "hire");
    await store.load("other");
    expect(store.snapshot.drafts.other).toEqual(DEMO);
  });

  it("a full plan takes no more items", async () => {
    const { store } = make();
    await store.load("acme");
    for (let n = 0; n < 12; n++) store.append("acme", "hire");
    expect(store.snapshot.drafts.acme.hires.length + store.snapshot.drafts.acme.programs.length).toBe(8);
  });
});

describe("a draft action asked for from the worksheet or the grid", () => {
  const SEED = { slice: "company", target: "0.2220", origin: "tornado" as const };

  it("is added to the company's form, not applied, and named so the form can show it", async () => {
    const { editor, store } = make();
    await store.load("acme");
    editor.applied.length = 0;
    store.draftAction("acme", SEED);
    expect(store.snapshot.drafts.acme.actions).toEqual([expect.objectContaining({ id: "action-0", slice: "company", target: "0.2220", ramp_months: 0 })]);
    expect(store.snapshot.applied.acme.plan.actions).toBeUndefined();
    expect(editor.applied).toEqual([]);
    expect(store.snapshot.origins.acme).toEqual({ "action-0": "tornado" });
    expect(store.snapshot.revealed).toEqual({ company: "acme", id: "action-0" });
  });

  it("asked for before the company's form exists, is added to it when it does", async () => {
    const { store } = make();
    store.draftAction("acme", { slice: "enterprise", target: "0.2193", origin: "grid" });
    expect(store.snapshot.drafts.acme).toBeUndefined();
    await store.load("acme");
    expect(store.snapshot.drafts.acme.actions).toEqual([expect.objectContaining({ slice: "enterprise", target: "0.2193" })]);
    expect(store.snapshot.applied.acme.plan.actions).toBeUndefined();
    expect(store.snapshot.origins.acme).toEqual({ "action-0": "grid" });
  });

  it("asked for again on the same slice shows the action the form has, and does not add another", async () => {
    const { store } = make();
    await store.load("acme");
    store.draftAction("acme", SEED);
    const before = store.snapshot.drafts.acme;
    store.draftAction("acme", { ...SEED, target: "0.30" });
    expect(store.snapshot.drafts.acme).toBe(before);
    expect(store.snapshot.revealed).toEqual({ company: "acme", id: "action-0" });
  });

  it("is sent with Apply like any other item", async () => {
    const { editor, store } = make();
    await store.load("acme");
    store.draftAction("acme", SEED);
    await store.apply("acme");
    expect(editor.applied.slice(-1)[0].actions).toEqual([expect.objectContaining({ id: "action-0", target: "0.2220" })]);
  });
});
