import type { TieoutLanes } from "../generated/lanes";
import type { TieoutLanesOwners } from "../generated/lanesOwners";
import type { TieoutReport } from "../generated/report";
import { EditorFailure } from "./client";
import type { EditorStatus } from "./client";
import type { ApplyOutcome, ComparisonRow, Facts, LanesOutcome, PlanDoc, PlanError } from "./protocol";
import { withUnit } from "./yourPlan";
import type { UnitKind } from "./yourPlan";

/** What the store needs of the client (the page's client, or a stand-in in tests). */
export interface Editor {
  readonly status: EditorStatus;
  subscribe(listener: () => void): () => void;
  open(company: string): Promise<Facts>;
  apply(company: string, plan: PlanDoc): Promise<ApplyOutcome>;
  lanes(company: string, revision: number): Promise<LanesOutcome>;
}

/**
 * The swimlane grid's files for one Apply, which the worker computes after the report is returned. They are part of the
 * Apply's entry, so lanes that belong to an earlier Apply can never sit beside a later report.
 */
export type EditedLanes =
  | { status: "pending" }
  | { status: "ready"; lanes: TieoutLanes; owners: Record<string, TieoutLanesOwners> }
  | { status: "failed"; message: string };

const PENDING: EditedLanes = { status: "pending" };

export interface Applied {
  report: TieoutReport;
  comparison: ComparisonRow;
  /** the plan this report is for */
  plan: PlanDoc;
  /** which Apply made it: the lanes are asked for by this */
  revision: number;
  lanes: EditedLanes;
}

interface Feedback {
  /** the company this feedback is about: another company's form shows none of it */
  company: string | null;
  /** the core's own words for what it refused, with where */
  errors: PlanError[];
  /** a computed report that failed the contract or the core's checks: shown as a failure, never rendered */
  problems: string[];
  /** the editor stopped (timed out, crashed): trying again is the way on */
  failure: { kind: "timeout" | "crash" | "error"; message: string } | null;
  busy: boolean;
}

export interface Snapshot {
  facts: Record<string, Facts>;
  /** the form, as the visitor left it, per company: kept for the session, in memory only */
  drafts: Record<string, PlanDoc>;
  applied: Record<string, Applied>;
  feedback: Feedback;
}

const CLEAN: Feedback = { company: null, errors: [], problems: [], failure: null, busy: false };
const copy = <T>(value: T): T => structuredClone(value);

/**
 * The visitor's plans for the session: what the form holds, what was last applied and what the core said.
 * Memory only: nothing is written to storage or to the address.
 */
export class YourPlanStore {
  snapshot: Snapshot = { facts: {}, drafts: {}, applied: {}, feedback: CLEAN };
  private readonly listeners = new Set<() => void>();
  /** an item asked for before the company's form existed: added to it when it does */
  private readonly queued: Record<string, UnitKind[]> = {};
  /** the Apply in hand: an earlier one that ends late changes nothing it no longer owns */
  private latest: object = {};

  constructor(readonly editor: Editor) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private change(next: Partial<Snapshot>) {
    this.snapshot = { ...this.snapshot, ...next };
    this.listeners.forEach((l) => l());
  }

  /** The company's report for the session: what was applied last, or the demo plan's items on the first time. */
  async load(company: string): Promise<Applied> {
    const kept = this.snapshot.applied[company];
    if (kept) return kept;
    const facts = await this.editor.open(company);
    const plan = copy(facts.demo_plan);
    const outcome = await this.editor.apply(company, plan);
    if (outcome.kind !== "report") {
      throw new Error(outcome.kind === "invalid" ? outcome.errors.map((e) => e.message).join("; ") : outcome.problems.join("; "));
    }
    const applied: Applied = { report: outcome.report, comparison: outcome.comparison, plan, revision: outcome.revision, lanes: PENDING };
    const draft = (this.queued[company] ?? []).reduce((p, kind) => withUnit(p, facts, kind), copy(plan));
    delete this.queued[company];
    this.change({
      facts: { ...this.snapshot.facts, [company]: facts },
      drafts: { ...this.snapshot.drafts, [company]: draft },
      applied: { ...this.snapshot.applied, [company]: applied },
      feedback: CLEAN,
    });
    void this.computeLanes(company, applied);
    return applied;
  }

  /** Add one unit of an action (one hire, or one program of the action's size) to the company's form; not applied until the visitor applies it. */
  append(company: string, kind: UnitKind) {
    const facts = this.snapshot.facts[company];
    const draft = this.snapshot.drafts[company];
    if (facts && draft) this.setDraft(company, withUnit(draft, facts, kind));
    else this.queued[company] = [...(this.queued[company] ?? []), kind];
  }

  setDraft(company: string, plan: PlanDoc) {
    this.change({ drafts: { ...this.snapshot.drafts, [company]: plan } });
  }

  /** Compute the company's form as it stands. A refusal or a failure is feedback; the last good report stays. */
  async apply(company: string): Promise<void> {
    const plan = copy(this.snapshot.drafts[company]);
    const mine = (this.latest = {});
    this.change({ feedback: { ...CLEAN, company, busy: true } });
    try {
      const outcome = await this.editor.apply(company, plan);
      if (outcome.kind === "report") {
        const applied: Applied = { report: outcome.report, comparison: outcome.comparison, plan, revision: outcome.revision, lanes: PENDING };
        this.change({ applied: { ...this.snapshot.applied, [company]: applied }, feedback: CLEAN });
        void this.computeLanes(company, applied);
      } else if (outcome.kind === "invalid") {
        this.change({ feedback: { ...CLEAN, company, errors: outcome.errors } });
      } else {
        this.change({ feedback: { ...CLEAN, company, problems: outcome.problems } });
      }
    } catch (e) {
      if (e instanceof EditorFailure && e.kind === "superseded") {
        if (this.latest === mine) this.change({ feedback: CLEAN });
        return;
      }
      const failure = e instanceof EditorFailure && e.kind !== "superseded" ? { kind: e.kind, message: e.message } : { kind: "error" as const, message: e instanceof Error ? e.message : String(e) };
      this.change({ feedback: { ...CLEAN, company, failure } });
    }
  }

  /**
   * Ask the worker for the lanes of `applied`, whose report is already shown. The answer is kept only if `applied` is still
   * the company's entry: an Apply made since owns the company, and what was asked for the earlier one is no longer wanted.
   */
  private async computeLanes(company: string, applied: Applied): Promise<void> {
    const settle = (lanes: EditedLanes) => {
      if (this.snapshot.applied[company] === applied) this.change({ applied: { ...this.snapshot.applied, [company]: { ...applied, lanes } } });
    };
    try {
      const out = await this.editor.lanes(company, applied.revision);
      if (out.kind === "lanes") settle({ status: "ready", lanes: out.lanes, owners: out.owners });
      else if (out.kind === "stale") settle({ status: "failed", message: "the worker had moved on before it could compute them; apply the plan again to compute them" });
      else settle({ status: "failed", message: out.problems.join("; ") });
    } catch (e) {
      // a newer request for lanes replaced this one: that one owns the lanes now
      if (e instanceof EditorFailure && e.kind === "superseded") return;
      settle({ status: "failed", message: e instanceof Error ? e.message : String(e) });
    }
  }
}
