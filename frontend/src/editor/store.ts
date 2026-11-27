import type { TieoutReport } from "../generated/report";
import { EditorFailure } from "./client";
import type { EditorStatus } from "./client";
import type { ApplyOutcome, ComparisonRow, Facts, PlanDoc, PlanError } from "./protocol";

/** What the store needs of the client (the page's client, or a stand-in in tests). */
export interface Editor {
  readonly status: EditorStatus;
  subscribe(listener: () => void): () => void;
  open(company: string): Promise<Facts>;
  apply(company: string, plan: PlanDoc): Promise<ApplyOutcome>;
}

export interface Applied {
  report: TieoutReport;
  comparison: ComparisonRow;
  /** the plan this report is for */
  plan: PlanDoc;
}

interface Feedback {
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

const CLEAN: Feedback = { errors: [], problems: [], failure: null, busy: false };
const copy = <T>(value: T): T => structuredClone(value);

/**
 * The visitor's plans for the session: what the form holds, what was last applied and what the core said.
 * Memory only: nothing is written to storage or to the address.
 */
export class YourPlanStore {
  snapshot: Snapshot = { facts: {}, drafts: {}, applied: {}, feedback: CLEAN };
  private readonly listeners = new Set<() => void>();

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
    const applied = { report: outcome.report, comparison: outcome.comparison, plan };
    this.change({
      facts: { ...this.snapshot.facts, [company]: facts },
      drafts: { ...this.snapshot.drafts, [company]: copy(plan) },
      applied: { ...this.snapshot.applied, [company]: applied },
      feedback: CLEAN,
    });
    return applied;
  }

  setDraft(company: string, plan: PlanDoc) {
    this.change({ drafts: { ...this.snapshot.drafts, [company]: plan } });
  }

  /** Compute the company's form as it stands. A refusal or a failure is feedback; the last good report stays. */
  async apply(company: string): Promise<void> {
    const plan = copy(this.snapshot.drafts[company]);
    this.change({ feedback: { ...CLEAN, busy: true } });
    try {
      const outcome = await this.editor.apply(company, plan);
      if (outcome.kind === "report") {
        this.change({
          applied: { ...this.snapshot.applied, [company]: { report: outcome.report, comparison: outcome.comparison, plan } },
          feedback: CLEAN,
        });
      } else if (outcome.kind === "invalid") {
        this.change({ feedback: { ...CLEAN, errors: outcome.errors } });
      } else {
        this.change({ feedback: { ...CLEAN, problems: outcome.problems } });
      }
    } catch (e) {
      if (e instanceof EditorFailure && e.kind === "superseded") return;
      const failure = e instanceof EditorFailure && e.kind !== "superseded" ? { kind: e.kind, message: e.message } : { kind: "error" as const, message: e instanceof Error ? e.message : String(e) };
      this.change({ feedback: { ...CLEAN, failure } });
    }
  }
}
