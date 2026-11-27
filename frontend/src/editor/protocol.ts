import type { ScenarioComparison } from "../generated/appFiles";
import type { TieoutReport } from "../generated/report";

/** What the form needs from the core, written by the core when a company is prepared. */
export interface Facts {
  company: string;
  segments: Array<{ value: string; label: string }>;
  /** the twelve months a plan may start in, as "YYYY-MM" */
  months: string[];
  /** the largest dollar figure a field accepts (ten times the year's target), as a decimal string */
  max_dollars: string;
  demo_plan: PlanDoc;
}

export interface HireDoc {
  segment: string;
  start: string;
  count: number;
}
export interface ProgramDoc {
  name: string;
  pipeline: number;
  start: string;
  ramp_months?: number;
  cost?: number;
}
/** A plan as the core's loader reads it (the same shape as plan.yaml, as data). */
export interface PlanDoc {
  hires: HireDoc[];
  programs: ProgramDoc[];
}

export type ComparisonRow = ScenarioComparison["rows"][number];

/** Why the core refused an item, in its own words, and where. */
export interface PlanError {
  section: "hires" | "programs" | null;
  /** as the core counts items in its messages, from one */
  index: number | null;
  /** the same item's place in the list, from zero */
  position: number | null;
  message: string;
}

export type ApplyOutcome =
  | { kind: "report"; report: TieoutReport; comparison: ComparisonRow }
  | { kind: "invalid"; errors: PlanError[] }
  /** the computed report failed the contract or its own checks: shown as a failure, never rendered */
  | { kind: "refused"; problems: string[] };

export type ToWorker =
  | { type: "open"; id: string; company: string; assets: string }
  | { type: "apply"; id: string; plan: string };

export type FromWorker =
  | { type: "progress"; id: string; text: string }
  | { type: "opened"; id: string; facts: string }
  | { type: "applied"; id: string; report: string; meta: string }
  | { type: "failed"; id: string; error: string };
