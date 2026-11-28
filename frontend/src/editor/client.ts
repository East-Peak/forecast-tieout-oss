import type { ApplyOutcome, ComparisonRow, Facts, FromWorker, LanesOutcome, PlanDoc, PlanError, ToWorker } from "./protocol";
import type { TieoutLanes } from "../generated/lanes";
import type { TieoutLanesOwners } from "../generated/lanesOwners";
import type { TieoutReport } from "../generated/report";

/** The part of a Worker the client uses; a fake stands in for it in tests. */
export interface WorkerLike {
  postMessage(message: ToWorker): void;
  terminate(): void;
  onmessage: ((event: { data: FromWorker }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessageerror: ((event: unknown) => void) | null;
}

export interface Timeouts {
  /** opening a company: the worker starting, its files arriving, the core preparing the company */
  startMs: number;
  /** one Apply: finishing a prepared company with a plan */
  applyMs: number;
  /** the very first start-up only, when set (the test hook below) */
  firstStartMs?: number;
}

export const TIMEOUTS: Timeouts = { startMs: 60_000, applyMs: 30_000 };

/**
 * A failed download never rejects and a dead worker never answers, so waiting is bounded here.
 * `superseded` is not a failure: a newer request replaced this one, and its answer is not wanted.
 */
export class EditorFailure extends Error {
  constructor(
    readonly kind: "timeout" | "crash" | "error" | "superseded",
    message: string,
  ) {
    super(message);
  }
}

export type EditorStatus =
  | { phase: "idle" }
  | { phase: "starting"; company: string; progress: string }
  | { phase: "ready"; company: string }
  | { phase: "computing"; company: string }
  | { phase: "failed"; kind: "timeout" | "crash" | "error"; message: string };

/**
 * The test hook: `?editorTimeout=short` lets the first start-up take three seconds instead of a minute, so a
 * test of the timeout state does not wait one. Every later attempt gets the normal allowance (a retry must be
 * able to finish a real start). Documented in ARCHITECTURE.md.
 */
export function timeoutsFromSearch(search: string, base: Timeouts): Timeouts {
  return new URLSearchParams(search).get("editorTimeout") === "short" ? { ...base, firstStartMs: 3000 } : base;
}

interface Pending {
  id: string;
  resolve: (value: never) => void;
  reject: (error: EditorFailure) => void;
  accept: (message: FromWorker) => void;
  timer: ReturnType<typeof setTimeout>;
}

interface Options {
  createWorker: () => WorkerLike;
  /** the folder the editor's files are served from, ending in "/" */
  assets: string;
  timeouts?: Timeouts;
}

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Talks to the plan editor's worker. The worker is made when a company is first opened, never before; it
 * stays for as long as it answers. One request is in hand at a time: a newer one replaces it, and an answer
 * to a request that is no longer in hand (by id) is ignored. A timeout or a crash ends the worker and fails
 * the request in hand; the next request starts a new one.
 */
export class PlanEditorClient {
  status: EditorStatus = { phase: "idle" };
  private worker: WorkerLike | null = null;
  private facts: Facts | null = null;
  private pending: Pending | null = null;
  private started = false;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly options: Options) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private set(status: EditorStatus) {
    this.status = status;
    this.listeners.forEach((l) => l());
  }

  private get timeouts() {
    return this.options.timeouts ?? TIMEOUTS;
  }

  /** Prepare `company` and say what the form needs; the same company again is already done. */
  open(company: string): Promise<Facts> {
    if (this.isOpen(company) && this.facts) {
      this.set({ phase: "ready", company });
      return Promise.resolve(this.facts);
    }
    const worker = this.ensureWorker();
    this.facts = null;
    this.set({ phase: "starting", company, progress: "Starting" });
    const limit = this.started ? this.timeouts.startMs : (this.timeouts.firstStartMs ?? this.timeouts.startMs);
    this.started = true;
    return this.request<Facts>(worker, limit, (id) => ({ type: "open", id, company, assets: this.options.assets }), (m, done) => {
      if (m.type === "progress") this.set({ phase: "starting", company, progress: m.text });
      else if (m.type === "opened") {
        this.facts = JSON.parse(m.facts) as Facts;
        this.set({ phase: "ready", company });
        done(this.facts);
      }
    });
  }

  /** The report for `plan` on `company`, preparing the company first if the worker is not on it. */
  apply(company: string, plan: PlanDoc): Promise<ApplyOutcome> {
    return this.isOpen(company) ? this.compute(company, plan) : this.open(company).then(() => this.compute(company, plan));
  }

  private isOpen(company: string): boolean {
    return this.worker !== null && this.facts?.company === company;
  }

  private compute(company: string, plan: PlanDoc): Promise<ApplyOutcome> {
    const worker = this.worker;
    if (!worker) return Promise.reject(new EditorFailure("superseded", "the worker was replaced"));
    this.set({ phase: "computing", company });
    return this.request<ApplyOutcome>(worker, this.timeouts.applyMs, (id) => ({ type: "apply", id, plan: JSON.stringify(plan) }), (m, done) => {
      if (m.type !== "applied") return;
      this.set({ phase: "ready", company });
      const meta = JSON.parse(m.meta) as { problems: string[]; errors: PlanError[]; comparison: ComparisonRow | null; revision: number | null };
      if (meta.problems.length > 0) done({ kind: "refused", problems: meta.problems });
      else if (meta.errors.length > 0) done({ kind: "invalid", errors: meta.errors });
      else {
        const report = JSON.parse(m.report) as TieoutReport;
        const identity = report.inputs?.identity;
        if (identity?.company !== company || identity.scenario !== "your-plan") {
          this.end(worker, "error", `the worker answered for ${identity?.company ?? "no company"}, not ${company}`);
        } else done({ kind: "report", report, comparison: meta.comparison as ComparisonRow, revision: meta.revision as number });
      }
    });
  }

  /**
   * The swimlane grid's files for the Apply `revision` of `company`, which the worker computes after it has returned that
   * Apply's report. Whatever is no longer the latest Apply of the company the worker holds is `stale`: nothing is
   * asked, or what comes back is dropped, and the caller decides what to show instead. The answer is checked to be for
   * this revision, this company and the visitor's plan before it is passed on.
   */
  lanes(company: string, revision: number): Promise<LanesOutcome> {
    const worker = this.worker;
    if (!worker || !this.isOpen(company)) return Promise.resolve({ kind: "stale" });
    return this.request<LanesOutcome>(worker, this.timeouts.applyMs, (id) => ({ type: "lanes", id, revision }), (m, done) => {
      if (m.type !== "lanes") return;
      const got = JSON.parse(m.lanes) as { revision: number; stale: boolean; problems?: string[]; lanes?: TieoutLanes | null; owners?: Record<string, TieoutLanesOwners> };
      if (got.revision !== revision) return this.end(worker, "error", `the worker answered for revision ${got.revision}, not ${revision}`);
      if (got.stale) return done({ kind: "stale" });
      if (!got.lanes) return done({ kind: "refused", problems: got.problems ?? [] });
      if (got.lanes.company !== company || got.lanes.scenario !== "your-plan") {
        return this.end(worker, "error", `the worker answered with the lanes of ${got.lanes.company} (${got.lanes.scenario}), not of ${company}'s plan`);
      }
      done({ kind: "lanes", lanes: got.lanes, owners: got.owners ?? {} });
    });
  }

  private ensureWorker(): WorkerLike {
    if (this.worker) return this.worker;
    const worker = this.options.createWorker();
    worker.onmessage = (event) => this.hear(worker, event.data);
    worker.onerror = (event) => this.end(worker, "crash", `the worker stopped: ${messageOf((event as { message?: unknown } | null)?.message ?? "no reason given")}`);
    worker.onmessageerror = () => this.end(worker, "crash", "the worker sent something that could not be read");
    this.worker = worker;
    return worker;
  }

  private request<T>(
    worker: WorkerLike,
    timeoutMs: number,
    message: (id: string) => ToWorker,
    accept: (m: FromWorker, done: (value: T) => void) => void,
  ): Promise<T> {
    this.pending?.reject(new EditorFailure("superseded", "a newer request replaced this one"));
    if (this.pending) clearTimeout(this.pending.timer);
    const id = crypto.randomUUID();
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => this.end(worker, "timeout", "no answer within the time allowed"), timeoutMs);
      const finish = (value: T) => {
        clearTimeout(timer);
        this.pending = null;
        resolve(value);
      };
      this.pending = { id, resolve: resolve as (v: never) => void, reject, timer, accept: (m) => accept(m, finish) };
      worker.postMessage(message(id));
    });
  }

  private hear(worker: WorkerLike, m: FromWorker) {
    if (worker !== this.worker || !this.pending || m.id !== this.pending.id) return;
    if (m.type === "failed") this.end(worker, "error", m.error);
    else this.pending.accept(m);
  }

  /** Give up on `worker`: end it, fail what it was asked, and leave the next request a new one. */
  private end(worker: WorkerLike, kind: "timeout" | "crash" | "error", message: string) {
    if (worker !== this.worker) return;
    worker.terminate();
    this.worker = null;
    this.facts = null;
    const pending = this.pending;
    this.pending = null;
    if (pending) clearTimeout(pending.timer);
    this.set({ phase: "failed", kind, message });
    pending?.reject(new EditorFailure(kind, message));
  }
}
