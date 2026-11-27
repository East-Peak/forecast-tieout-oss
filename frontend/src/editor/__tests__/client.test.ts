import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EditorFailure, PlanEditorClient, timeoutsFromSearch } from "../client";
import type { Facts, FromWorker, PlanDoc, ToWorker } from "../protocol";

class FakeWorker {
  sent: ToWorker[] = [];
  terminated = false;
  onmessage: ((event: { data: FromWorker }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessageerror: ((event: unknown) => void) | null = null;
  postMessage(m: ToWorker) {
    this.sent.push(m);
  }
  terminate() {
    this.terminated = true;
  }
  say(m: FromWorker) {
    this.onmessage?.({ data: m });
  }
  last<T extends ToWorker["type"]>(type: T) {
    return this.sent.filter((m) => m.type === type).slice(-1)[0] as Extract<ToWorker, { type: T }>;
  }
}

const PLAN: PlanDoc = { hires: [{ segment: "mid_market", start: "2026-10", count: 1 }], programs: [] };
const facts = (company: string): Facts => ({ company, segments: [], months: [], max_dollars: "1", demo_plan: PLAN });
const REPORT = { schema_version: "x", inputs: { identity: { company: "acme", scenario: "your-plan" } } };
const ROW = { scenario: "your-plan", label: "Your plan" };

function setup(timeouts = { startMs: 1000, applyMs: 500 }) {
  const workers: FakeWorker[] = [];
  const client = new PlanEditorClient({
    createWorker: () => {
      const w = new FakeWorker();
      workers.push(w);
      return w;
    },
    assets: "/editor/abc/",
    timeouts,
  });
  const statuses: string[] = [];
  client.subscribe(() => statuses.push(client.status.phase));
  return { client, workers, statuses };
}

/** Answer the open request the worker last received. */
const opened = (w: FakeWorker, company: string) => w.say({ type: "opened", id: w.last("open").id, facts: JSON.stringify(facts(company)) });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("starting", () => {
  it("makes no worker until a company is opened", () => {
    const { workers, client } = setup();
    expect(workers).toHaveLength(0);
    expect(client.status.phase).toBe("idle");
  });

  it("starts one worker on the first open, shows its progress, and resolves with the form's facts", async () => {
    const { client, workers } = setup();
    const result = client.open("acme");
    expect(workers).toHaveLength(1);
    expect(workers[0].last("open")).toMatchObject({ company: "acme", assets: "/editor/abc/" });
    workers[0].say({ type: "progress", id: workers[0].last("open").id, text: "Loading Python" });
    expect(client.status).toEqual({ phase: "starting", company: "acme", progress: "Loading Python" });
    opened(workers[0], "acme");
    await expect(result).resolves.toEqual(facts("acme"));
    expect(client.status).toEqual({ phase: "ready", company: "acme" });
  });

  it("does not ask again for a company it has already prepared", async () => {
    const { client, workers } = setup();
    const first = client.open("acme");
    opened(workers[0], "acme");
    await first;
    await expect(client.open("acme")).resolves.toEqual(facts("acme"));
    expect(workers[0].sent).toHaveLength(1);
  });

  it("re-prepares for another company on the same worker", async () => {
    const { client, workers } = setup();
    const a = client.open("acme");
    opened(workers[0], "acme");
    await a;
    const b = client.open("birch");
    opened(workers[0], "birch");
    await expect(b).resolves.toMatchObject({ company: "birch" });
    expect(workers).toHaveLength(1);
    expect(workers[0].sent.filter((m) => m.type === "open")).toHaveLength(2);
  });
});

describe("timing out", () => {
  it("gives up on a start-up that never answers (a failed download never rejects), and says so", async () => {
    const { client, workers } = setup();
    const result = client.open("acme");
    const caught = result.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1000);
    const error = (await caught) as EditorFailure;
    expect(error).toBeInstanceOf(EditorFailure);
    expect(error.kind).toBe("timeout");
    expect(workers[0].terminated).toBe(true);
    expect(client.status).toMatchObject({ phase: "failed", kind: "timeout" });
  });

  it("retries on a fresh worker, as if for the first time", async () => {
    const { client, workers } = setup();
    const first = client.open("acme").catch(() => null);
    await vi.advanceTimersByTimeAsync(1000);
    await first;
    const again = client.open("acme");
    expect(workers).toHaveLength(2);
    opened(workers[1], "acme");
    await expect(again).resolves.toEqual(facts("acme"));
  });

  it("times an Apply out on its own shorter clock, and a retry re-prepares before applying", async () => {
    const { client, workers } = setup();
    const o = client.open("acme");
    opened(workers[0], "acme");
    await o;
    const applying = client.apply("acme", PLAN).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(500);
    expect(await applying).toMatchObject({ kind: "timeout" });
    expect(workers[0].terminated).toBe(true);
    const retry = client.apply("acme", PLAN);
    expect(workers).toHaveLength(2);
    opened(workers[1], "acme");
    await vi.advanceTimersByTimeAsync(0);
    workers[1].say({ type: "applied", id: workers[1].last("apply").id, report: JSON.stringify(REPORT), meta: JSON.stringify({ problems: [], errors: [], comparison: ROW }) });
    await expect(retry).resolves.toMatchObject({ kind: "report" });
  });
});

describe("applying", () => {
  async function ready() {
    const s = setup();
    const o = s.client.open("acme");
    opened(s.workers[0], "acme");
    await o;
    return s;
  }

  it("sends the plan as text and returns the report and its comparison row", async () => {
    const { client, workers } = await ready();
    const result = client.apply("acme", PLAN);
    expect(client.status).toEqual({ phase: "computing", company: "acme" });
    expect(JSON.parse(workers[0].last("apply").plan)).toEqual(PLAN);
    workers[0].say({ type: "applied", id: workers[0].last("apply").id, report: JSON.stringify(REPORT), meta: JSON.stringify({ problems: [], errors: [], comparison: ROW }) });
    await expect(result).resolves.toEqual({ kind: "report", report: REPORT, comparison: ROW });
    expect(client.status).toEqual({ phase: "ready", company: "acme" });
  });

  it("returns the core's words for a plan it refused, and the worker stays warm", async () => {
    const { client, workers } = await ready();
    const result = client.apply("acme", PLAN);
    const errors = [{ section: "hires", index: 1, position: 0, message: "hires[1]: count must be a whole number of at least 1" }];
    workers[0].say({ type: "applied", id: workers[0].last("apply").id, report: "", meta: JSON.stringify({ problems: [], errors, comparison: null }) });
    await expect(result).resolves.toEqual({ kind: "invalid", errors });
    expect(client.status.phase).toBe("ready");
    expect(workers[0].terminated).toBe(false);
  });

  it("returns a report that failed its checks as a refusal, with the report withheld", async () => {
    const { client, workers } = await ready();
    const result = client.apply("acme", PLAN);
    workers[0].say({ type: "applied", id: workers[0].last("apply").id, report: "", meta: JSON.stringify({ problems: ["/plan: bad"], errors: [], comparison: null }) });
    await expect(result).resolves.toEqual({ kind: "refused", problems: ["/plan: bad"] });
  });

  it("opens the company first when the worker was recycled or is on another company", async () => {
    const { client, workers } = await ready();
    const result = client.apply("birch", PLAN);
    expect(workers[0].last("open")).toMatchObject({ company: "birch" });
    opened(workers[0], "birch");
    await vi.advanceTimersByTimeAsync(0);
    workers[0].say({ type: "applied", id: workers[0].last("apply").id, report: JSON.stringify(REPORT), meta: JSON.stringify({ problems: [], errors: [], comparison: ROW }) });
    await expect(result).resolves.toMatchObject({ kind: "report" });
  });
});

describe("stale answers", () => {
  it("ignores an answer to a request that has been replaced", async () => {
    const { client, workers } = setup();
    const a = client.open("acme").catch((e: unknown) => e);
    const staleId = workers[0].last("open").id;
    const b = client.open("birch");
    workers[0].say({ type: "opened", id: staleId, facts: JSON.stringify(facts("acme")) });
    expect(client.status.phase).toBe("starting");
    opened(workers[0], "birch");
    await expect(b).resolves.toMatchObject({ company: "birch" });
    expect(await a).toMatchObject({ kind: "superseded" });
  });

  it("ignores an answer that matches no request at all", async () => {
    const { client, workers } = setup();
    const result = client.open("acme");
    workers[0].say({ type: "opened", id: "no-such-request", facts: JSON.stringify(facts("zzz")) });
    expect(client.status.phase).toBe("starting");
    opened(workers[0], "acme");
    await expect(result).resolves.toMatchObject({ company: "acme" });
  });

  it("ignores a late answer from a worker that was already given up on", async () => {
    const { client, workers } = setup();
    const first = client.open("acme").catch(() => null);
    await vi.advanceTimersByTimeAsync(1000);
    await first;
    const oldId = workers[0].last("open").id;
    const again = client.open("acme");
    workers[0].say({ type: "opened", id: oldId, facts: JSON.stringify(facts("late")) });
    expect(client.status.phase).toBe("starting");
    opened(workers[1], "acme");
    await expect(again).resolves.toMatchObject({ company: "acme" });
  });
});

describe("crashes", () => {
  it("fails the request in hand when the worker dies, and uses a new worker next time", async () => {
    const { client, workers } = setup();
    const result = client.open("acme").catch((e: unknown) => e);
    workers[0].onerror?.({ message: "boom" });
    expect(await result).toMatchObject({ kind: "crash" });
    expect(workers[0].terminated).toBe(true);
    expect(client.status).toMatchObject({ phase: "failed", kind: "crash" });
    const again = client.open("acme");
    expect(workers).toHaveLength(2);
    opened(workers[1], "acme");
    await expect(again).resolves.toMatchObject({ company: "acme" });
  });

  it("reports the worker's own failure message and recycles", async () => {
    const { client, workers } = setup();
    const result = client.open("acme").catch((e: unknown) => e);
    workers[0].say({ type: "failed", id: workers[0].last("open").id, error: "HTTP 404: pyodide.asm.wasm" });
    const error = (await result) as EditorFailure;
    expect(error).toMatchObject({ kind: "error" });
    expect(error.message).toContain("HTTP 404");
    expect(workers[0].terminated).toBe(true);
  });
});

describe("the test hook for shorter timeouts", () => {
  const base = { startMs: 60_000, applyMs: 30_000 };
  it("shortens both clocks when the address asks for it, and otherwise leaves them", () => {
    expect(timeoutsFromSearch("?editorTimeout=short", base)).toEqual({ startMs: 3000, applyMs: 3000 });
    expect(timeoutsFromSearch("?editorTimeout=long", base)).toEqual(base);
    expect(timeoutsFromSearch("", base)).toEqual(base);
  });
});
