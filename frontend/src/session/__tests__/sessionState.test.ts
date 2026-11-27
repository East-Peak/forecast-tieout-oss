import { describe, expect, it } from "vitest";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { initialState, reduce, resolveSelection, type SessionState } from "../sessionState";

const scenario = (id: string) => ({ id, label: id, description: "", plan_file: null, report: `x/${id}.json`, report_markdown: `x/${id}.md` });
const company = (id: string) => ({
  id,
  name: id,
  description: "",
  as_of: "2026-08-31",
  fiscal_year: "FY26",
  comparison: `${id}/comparison.json`,
  scenarios: [scenario("as-signed"), scenario("demo-plan")],
});
const index: ReportIndex = {
  schema_version: "1.0.0",
  default_company: "b",
  companies: [company("a"), company("b")],
};
const report = (tag: string) => ({ tag }) as unknown as TieoutReport;
const comparison = {} as ScenarioComparison;

describe("resolveSelection: the URL, then the stored choice, then the index's defaults", () => {
  it("takes a valid request as it is", () => {
    expect(resolveSelection(index, { company: "a", scenario: "demo-plan" }, null)).toEqual({
      selection: { company: "a", scenario: "demo-plan" },
      notice: null,
    });
  });
  it("falls back to the stored choice, then to the index default", () => {
    const stored = { company: "a", scenario: "as-signed" };
    expect(resolveSelection(index, {}, stored).selection).toEqual(stored);
    expect(resolveSelection(index, {}, null).selection).toEqual({ company: "b", scenario: "as-signed" });
  });
  it("says so when the request names a company or scenario the index does not have", () => {
    const r = resolveSelection(index, { company: "zzz", scenario: "demo-plan" }, null);
    expect(r.selection.company).toBe("b");
    expect(r.notice).toMatch(/zzz/);
    const s = resolveSelection(index, { company: "a", scenario: "nope" }, null);
    expect(s.selection).toEqual({ company: "a", scenario: "as-signed" });
    expect(s.notice).toMatch(/nope/);
  });
  it("a stored choice that no longer exists is dropped without a notice", () => {
    const r = resolveSelection(index, {}, { company: "gone", scenario: "as-signed" });
    expect(r.selection.company).toBe("b");
    expect(r.notice).toBeNull();
  });
});

describe("the session's states", () => {
  const sel = (company: string, scenario = "as-signed") => ({ company, scenario });
  const first = (company: string): SessionState =>
    reduce(initialState, { type: "indexLoaded", index, selection: sel(company), notice: null });
  const id = (state: SessionState) => ("requestId" in state ? state.requestId : -1);
  const ready = (company: string): SessionState => {
    const loading = first(company);
    return reduce(loading, { type: "loaded", requestId: id(loading), report: report(company), comparison });
  };

  it("starts loading the index, and an index failure is an error, not a blank page", () => {
    expect(initialState.status).toBe("loading-index");
    expect(reduce(initialState, { type: "indexFailed", error: "404" })).toEqual({ status: "index-error", error: "404" });
  });

  it("loads the chosen report once the index is in", () => {
    const loading = first("a");
    expect(loading.status).toBe("loading");
    expect(reduce(loading, { type: "loaded", requestId: id(loading), report: report("a"), comparison }).status).toBe("ready");
  });

  it("an answer to a request the visitor has since replaced is ignored, success or failure", () => {
    const loadingA = first("a");
    const loadingB = reduce(loadingA, { type: "select", selection: sel("b"), notice: null });
    expect(loadingB).toMatchObject({ status: "loading", selection: sel("b") });
    expect(id(loadingB)).toBeGreaterThan(id(loadingA));
    expect(reduce(loadingB, { type: "loaded", requestId: id(loadingA), report: report("a"), comparison })).toBe(loadingB);
    expect(reduce(loadingB, { type: "failed", requestId: id(loadingA), error: "boom" })).toBe(loadingB);
    const done = reduce(loadingB, { type: "loaded", requestId: id(loadingB), report: report("b"), comparison });
    expect(done).toMatchObject({ status: "ready", report: { tag: "b" } });
  });

  it("A, then B, then A again: the first A's answer is stale though the company is the same", () => {
    const a1 = first("a");
    const b = reduce(a1, { type: "select", selection: sel("b"), notice: null });
    const a2 = reduce(b, { type: "select", selection: sel("a"), notice: null });
    expect(id(a2)).toBeGreaterThan(id(b));
    expect(reduce(a2, { type: "failed", requestId: id(a1), error: "old A broke" })).toBe(a2);
    expect(reduce(a2, { type: "loaded", requestId: id(a1), report: report("old A"), comparison })).toBe(a2);
    expect(reduce(a2, { type: "loaded", requestId: id(a2), report: report("A"), comparison }).status).toBe("ready");
  });

  it("a late answer for the same company but another scenario is ignored too", () => {
    const loading = first("a");
    const switched = reduce(loading, { type: "select", selection: sel("a", "demo-plan"), notice: null });
    expect(reduce(switched, { type: "loaded", requestId: id(loading), report: report("old"), comparison })).toBe(switched);
  });

  it("switching from a ready report goes back to loading and keeps nothing of the old report", () => {
    const next = reduce(ready("a"), { type: "select", selection: sel("b"), notice: null });
    expect(next).toMatchObject({ status: "loading", selection: sel("b") });
    expect("report" in next).toBe(false);
  });

  it("selecting what is already shown changes nothing, except that a correction's notice is kept", () => {
    const state = ready("a");
    expect(reduce(state, { type: "select", selection: sel("a"), notice: null })).toBe(state);
    expect(reduce(state, { type: "select", selection: sel("a"), notice: "There is no company zzz." })).toMatchObject({
      status: "ready",
      notice: "There is no company zzz.",
    });
  });

  it("a failed report load for the current request is an error that names the choice, and another choice recovers", () => {
    const loading = first("a");
    const failed = reduce(loading, { type: "failed", requestId: id(loading), error: "HTTP 404" });
    expect(failed).toMatchObject({ status: "error", selection: sel("a"), error: "HTTP 404" });
    expect(reduce(failed, { type: "select", selection: sel("b"), notice: null }).status).toBe("loading");
  });

  it("an answer before the index has arrived is ignored", () => {
    expect(reduce(initialState, { type: "loaded", requestId: 1, report: report("a"), comparison })).toBe(initialState);
  });
  it("a retry loads the failed choice again under a new request, and a late answer to the first try is ignored", () => {
    const loading = first("a");
    const failed = reduce(loading, { type: "failed", requestId: id(loading), error: "no answer" });
    const again = reduce(failed, { type: "retry" });
    expect(again).toMatchObject({ status: "loading", selection: sel("a") });
    expect(id(again)).toBeGreaterThan(id(loading));
    expect(reduce(again, { type: "loaded", requestId: id(loading), report: report("old"), comparison })).toBe(again);
    expect(reduce(ready("a"), { type: "retry" }).status).toBe("ready");
  });

  it("a replaced report swaps what a ready screen shows without loading again, for the choice it was computed for", () => {
    const shown = ready("a");
    const now = reduce(shown, { type: "replaced", selection: sel("a"), report: report("new"), comparison });
    expect(now).toMatchObject({ status: "ready", report: { tag: "new" }, requestId: id(shown) });
    // computed for a choice no longer on the screen: nothing happens
    expect(reduce(shown, { type: "replaced", selection: sel("b"), report: report("elsewhere"), comparison })).toBe(shown);
    expect(reduce(first("a"), { type: "replaced", selection: sel("a"), report: report("early"), comparison }).status).toBe("loading");
  });
});
