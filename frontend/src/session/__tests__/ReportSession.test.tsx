import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { ReportSessionProvider, useSession, type Loaders } from "../ReportSession";
import { STORAGE_KEY } from "../storage";

const scenario = (id: string) => ({ id, label: `scenario ${id}`, description: "", plan_file: null, report: `${id}.json`, report_markdown: `${id}.md` });
const company = (id: string) => ({
  id,
  name: `Company ${id}`,
  description: "",
  as_of: "2026-08-31",
  fiscal_year: "FY26",
  comparison: `${id}/comparison.json`,
  scenarios: [scenario("as-signed"), scenario("demo-plan")].map((s) => ({ ...s, report: `${id}/${s.id}.json` })),
});
const index: ReportIndex = { schema_version: "1.0.0", default_company: "b", companies: [company("a"), company("b")] };

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e: Error) => void;
}
function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
const report = (tag: string, identity?: { company: string; scenario: string }) =>
  ({ schema_version: "1.0.0", tag, ...(identity ? { inputs: { identity } } : {}) }) as unknown as TieoutReport;
/** The identity a report file's path says it has: "a/demo-plan.json" is company a, scenario demo-plan. */
const named = (path: string) => ({ company: path.split("/")[0], scenario: (path.split("/")[1] ?? "").replace(".json", "") });

function harness() {
  const pending = new Map<string, Deferred<TieoutReport>>();
  const calls: Array<{ path: string; d: Deferred<TieoutReport> }> = [];
  const loaders: Loaders = {
    index: () => Promise.resolve(index),
    report: (path) => {
      const d = deferred<TieoutReport>();
      pending.set(path, d);
      calls.push({ path, d });
      // a fake that names no identity is taken to be the file asked for; one that names its own is believed
      return d.promise.then((r) => ("inputs" in r ? r : ({ ...(r as object), inputs: { identity: named(path) } } as TieoutReport)));
    },
    comparison: (path) => Promise.resolve({ company: path.split("/")[0], rows: [] } as unknown as ScenarioComparison),
  };
  return { pending, calls, loaders };
}

let choose: ReturnType<typeof useSession>["choose"];
let go: ReturnType<typeof useNavigate>;
function Probe() {
  const { state, choose: c } = useSession();
  choose = c;
  go = useNavigate();
  const where = useLocation();
  return (
    <div>
      <div data-testid="status">{state.status}</div>
      <div data-testid="selection">{"selection" in state ? `${state.selection.company}/${state.selection.scenario}` : "-"}</div>
      <div data-testid="shown">{state.status === "ready" ? (state.report as unknown as { tag: string }).tag : "-"}</div>
      <div data-testid="error">{"error" in state ? state.error : ""}</div>
      <div data-testid="notice">{"notice" in state ? (state.notice ?? "") : ""}</div>
      <div data-testid="url">{where.search}</div>
    </div>
  );
}

function mount(loaders: Loaders, url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ReportSessionProvider loaders={loaders}>
        <Probe />
      </ReportSessionProvider>
    </MemoryRouter>,
  );
}
const text = (id: string) => screen.getByTestId(id).textContent;

afterEach(() => localStorage.clear());

describe("the report-backed session", () => {
  it("reads company and scenario from the URL, loads that report, and shows it", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a&scenario=demo-plan");
    await waitFor(() => expect(pending.has("a/demo-plan.json")).toBe(true));
    expect(text("status")).toBe("loading");
    await act(async () => pending.get("a/demo-plan.json")!.resolve(report("A demo")));
    expect(text("status")).toBe("ready");
    expect(text("shown")).toBe("A demo");
  });

  it("with nothing in the URL uses the index default, then writes the choice into the URL", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast");
    await waitFor(() => expect(pending.has("b/as-signed.json")).toBe(true));
    await waitFor(() => expect(text("url")).toBe("?company=b&scenario=as-signed"));
  });

  it("remembers the choice under the new storage key", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () => pending.get("a/as-signed.json")!.resolve(report("A")));
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toEqual({ company: "a", scenario: "as-signed" });
  });

  it("uses a remembered choice only when the URL says nothing", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ company: "a", scenario: "demo-plan" }));
    const { pending, loaders } = harness();
    mount(loaders, "/forecast");
    await waitFor(() => expect(pending.has("a/demo-plan.json")).toBe(true));
  });

  it("a late response for the company the visitor has left never reaches the screen", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () => choose("b", "as-signed"));
    await waitFor(() => expect(pending.has("b/as-signed.json")).toBe(true));
    await act(async () => pending.get("b/as-signed.json")!.resolve(report("B")));
    expect(text("shown")).toBe("B");
    await act(async () => pending.get("a/as-signed.json")!.resolve(report("A late")));
    expect(text("shown")).toBe("B");
    expect(text("selection")).toBe("b/as-signed");
  });

  it("a late failure for a company left behind does not turn the screen into an error", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () => choose("b", "as-signed"));
    await waitFor(() => expect(pending.has("b/as-signed.json")).toBe(true));
    await act(async () => pending.get("a/as-signed.json")!.reject(new Error("A broke")));
    expect(text("status")).toBe("loading");
    await act(async () => pending.get("b/as-signed.json")!.resolve(report("B")));
    expect(text("status")).toBe("ready");
  });

  it("a report that fails to load is an error naming the problem, and another choice recovers", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () => pending.get("a/as-signed.json")!.reject(new Error("HTTP 404")));
    expect(text("status")).toBe("error");
    expect(text("error")).toContain("HTTP 404");
    await act(async () => choose("b", "as-signed"));
    await waitFor(() => expect(pending.has("b/as-signed.json")).toBe(true));
    await act(async () => pending.get("b/as-signed.json")!.resolve(report("B")));
    expect(text("status")).toBe("ready");
  });

  it("an index that fails to load is an error, not a blank page", async () => {
    const loaders: Loaders = { ...harness().loaders, index: () => Promise.reject(new Error("index 500")) };
    mount(loaders, "/forecast");
    await waitFor(() => expect(text("status")).toBe("index-error"));
    expect(text("error")).toContain("index 500");
  });

  it("a report from another schema version is refused, not shown", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () =>
      pending.get("a/as-signed.json")!.resolve({ schema_version: "9.9.9" } as unknown as TieoutReport),
    );
    expect(text("status")).toBe("error");
    expect(text("error")).toMatch(/schema/i);
  });

  it("says so when the URL names a company that does not exist", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=zzz");
    await waitFor(() => expect(pending.has("b/as-signed.json")).toBe(true));
    expect(text("notice")).toMatch(/zzz/);
  });

  it("A then B then A: the first A's late answer, success or failure, never touches the latest A", async () => {
    const { calls, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(calls.length).toBe(1));
    await act(async () => choose("b", "as-signed"));
    await waitFor(() => expect(calls.length).toBe(2));
    await act(async () => choose("a", "as-signed"));
    await waitFor(() => expect(calls.length).toBe(3));
    // the first A fails while the latest A is still loading: that must not put the screen in error
    await act(async () => calls[0].d.reject(new Error("first A broke")));
    expect(text("status")).toBe("loading");
    await act(async () => calls[0].d.resolve(report("first A late")));
    await act(async () => calls[2].d.resolve(report("A latest")));
    expect(text("shown")).toBe("A latest");
    await act(async () => calls[1].d.resolve(report("B late")));
    expect(text("shown")).toBe("A latest");
  });

  it("a later URL change to an unknown company is corrected in the URL and keeps its notice", async () => {
    const { calls, loaders } = harness();
    mount(loaders, "/forecast?company=a");
    await waitFor(() => expect(calls.length).toBe(1));
    await act(async () => calls[0].d.resolve(report("A")));
    await act(async () => go("/forecast?company=zzz&scenario=demo-plan"));
    await waitFor(() => expect(text("url")).toBe("?company=b&scenario=demo-plan"));
    expect(text("notice")).toMatch(/zzz/);
  });

  it("an unknown company that resolves to the very choice on screen still gets its URL corrected", async () => {
    const { calls, loaders } = harness();
    mount(loaders, "/forecast");
    await waitFor(() => expect(calls.length).toBe(1)); // b/as-signed, the default
    await act(async () => calls[0].d.resolve(report("B")));
    await act(async () => go("/forecast?company=zzz"));
    await waitFor(() => expect(text("url")).toBe("?company=b&scenario=as-signed"));
    expect(text("notice")).toMatch(/zzz/);
    expect(text("status")).toBe("ready");
  });

  it("a report that names another scenario than the one asked for is refused, not shown", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a&scenario=demo-plan");
    await waitFor(() => expect(pending.has("a/demo-plan.json")).toBe(true));
    await act(async () => pending.get("a/demo-plan.json")!.resolve(report("wrong file", { company: "a", scenario: "as-signed" })));
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    expect(screen.getByTestId("error").textContent).toMatch(/a\/as-signed/);
    expect(screen.getByTestId("error").textContent).toMatch(/a\/demo-plan/);
    expect(screen.getByTestId("shown").textContent).toBe("-");
  });

  it("a report that names another company than the one asked for is refused", async () => {
    const { pending, loaders } = harness();
    mount(loaders, "/forecast?company=a&scenario=as-signed");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () => pending.get("a/as-signed.json")!.resolve(report("wrong file", { company: "b", scenario: "as-signed" })));
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    expect(screen.getByTestId("shown").textContent).toBe("-");
  });

  it("a report with no identity at all is refused", async () => {
    const { loaders } = harness();
    const bare: Loaders = { ...loaders, report: () => Promise.resolve(report("no identity") as TieoutReport) };
    mount(bare, "/forecast?company=a&scenario=as-signed");
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
  });

  it("a comparison file for another company is refused", async () => {
    const { pending, loaders } = harness();
    const wrong: Loaders = { ...loaders, comparison: () => Promise.resolve({ company: "b", rows: [] } as unknown as ScenarioComparison) };
    mount(wrong, "/forecast?company=a&scenario=as-signed");
    await waitFor(() => expect(pending.has("a/as-signed.json")).toBe(true));
    await act(async () => pending.get("a/as-signed.json")!.resolve(report("A")));
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    expect(screen.getByTestId("error").textContent).toMatch(/comparison/);
  });
});
