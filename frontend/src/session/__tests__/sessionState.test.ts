import { describe, expect, it } from "vitest";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { initialState, reduce, resolveSelection, type SessionState } from "../sessionState";

const scenario = (id: string) => ({ id, label: id, description: "", plan_file: null, report: `x/${id}.json` });
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
  const ready = (company: string): SessionState =>
    reduce(
      reduce(initialState, { type: "indexLoaded", index, selection: sel(company), notice: null }),
      { type: "loaded", selection: sel(company), report: report(company), comparison },
    );

  it("starts loading the index, and an index failure is an error, not a blank page", () => {
    expect(initialState.status).toBe("loading-index");
    const failed = reduce(initialState, { type: "indexFailed", error: "404" });
    expect(failed).toEqual({ status: "index-error", error: "404" });
  });

  it("loads the chosen report once the index is in", () => {
    const loading = reduce(initialState, { type: "indexLoaded", index, selection: sel("a"), notice: null });
    expect(loading.status).toBe("loading");
    const done = reduce(loading, { type: "loaded", selection: sel("a"), report: report("a"), comparison });
    expect(done.status).toBe("ready");
  });

  it("a response for a company the visitor has since left is ignored", () => {
    const loadingA = reduce(initialState, { type: "indexLoaded", index, selection: sel("a"), notice: null });
    const loadingB = reduce(loadingA, { type: "select", selection: sel("b") });
    expect(loadingB).toMatchObject({ status: "loading", selection: sel("b") });
    // A's response arrives late
    const afterLate = reduce(loadingB, { type: "loaded", selection: sel("a"), report: report("a"), comparison });
    expect(afterLate).toBe(loadingB);
    const afterLateError = reduce(loadingB, { type: "failed", selection: sel("a"), error: "boom" });
    expect(afterLateError).toBe(loadingB);
    // B's arrives and shows
    const done = reduce(loadingB, { type: "loaded", selection: sel("b"), report: report("b"), comparison });
    expect(done).toMatchObject({ status: "ready", report: { tag: "b" } });
  });

  it("a late response for the same company but another scenario is ignored too", () => {
    const loading = reduce(initialState, { type: "indexLoaded", index, selection: sel("a", "as-signed"), notice: null });
    const switched = reduce(loading, { type: "select", selection: sel("a", "demo-plan") });
    const late = reduce(switched, { type: "loaded", selection: sel("a", "as-signed"), report: report("old"), comparison });
    expect(late).toBe(switched);
  });

  it("switching from a ready report goes back to loading and keeps nothing of the old report", () => {
    const next = reduce(ready("a"), { type: "select", selection: sel("b") });
    expect(next).toMatchObject({ status: "loading", selection: sel("b") });
    expect("report" in next).toBe(false);
  });

  it("selecting what is already shown changes nothing", () => {
    const state = ready("a");
    expect(reduce(state, { type: "select", selection: sel("a") })).toBe(state);
  });

  it("a failed report load for the current choice is an error that names the choice", () => {
    const loading = reduce(initialState, { type: "indexLoaded", index, selection: sel("a"), notice: null });
    const failed = reduce(loading, { type: "failed", selection: sel("a"), error: "HTTP 404" });
    expect(failed).toMatchObject({ status: "error", selection: sel("a"), error: "HTTP 404" });
    // and the visitor can pick something else
    expect(reduce(failed, { type: "select", selection: sel("b") }).status).toBe("loading");
  });

  it("a response before the index has arrived is ignored", () => {
    expect(reduce(initialState, { type: "loaded", selection: sel("a"), report: report("a"), comparison })).toBe(initialState);
  });
});
