import type { ScenarioComparison } from "../generated/appFiles";
import type { TieoutLanes } from "../generated/lanes";
import type { TieoutLanesOwners } from "../generated/lanesOwners";
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
/** The drivers an action can change: the win rate, the size of a win, and how many deals people create. */
export type ActionDriver = "win_rate" | "won_arr" | "productivity";

/** A change to one driver in one slice: "slice" is "company" or a segment, "target" in the driver's own terms (a probability, dollars per won deal, deals per ramped AE-month or per day; a decimal string, as the core reads it). */
export interface ActionDoc {
  id: string;
  name?: string;
  driver: ActionDriver;
  slice: string;
  start: string;
  ramp_months?: number;
  target: number | string;
}
/** A plan as the core's loader reads it (the same shape as plan.yaml, as data). */
export interface PlanDoc {
  hires: HireDoc[];
  programs: ProgramDoc[];
  actions?: ActionDoc[];
}

export type ComparisonRow = ScenarioComparison["rows"][number];

/** Why the core refused an item, in its own words, and where. */
export interface PlanError {
  section: "hires" | "programs" | "actions" | null;
  /** as the core counts items in its messages, from one */
  index: number | null;
  /** the same item's place in the list, from zero */
  position: number | null;
  message: string;
  /** which rule refused it (for an action), for a program: the message is for a person */
  code?: string;
}

export type ApplyOutcome =
  /** `revision` names this Apply: the lanes of this report are asked for by it, and only the latest Apply has any */
  | { kind: "report"; report: TieoutReport; comparison: ComparisonRow; revision: number }
  | { kind: "invalid"; errors: PlanError[] }
  /** the computed report failed the contract or its own checks: shown as a failure, never rendered */
  | { kind: "refused"; problems: string[] };

/** What the swimlane grid needs for an Apply's report, written by the core after the report was returned. */
export type LanesOutcome =
  | { kind: "lanes"; lanes: TieoutLanes; owners: Record<string, TieoutLanesOwners> }
  /** the worker has moved on (another Apply, another company): these lanes would belong to something no longer shown */
  | { kind: "stale" }
  /** the lanes failed the contract, or their goals were not the committed ones: shown as a failure, never rendered */
  | { kind: "refused"; problems: string[] };

export type ToWorker =
  | { type: "open"; id: string; company: string; assets: string }
  | { type: "apply"; id: string; plan: string }
  | { type: "lanes"; id: string; revision: number };

export type FromWorker =
  | { type: "progress"; id: string; text: string }
  | { type: "opened"; id: string; facts: string }
  | { type: "applied"; id: string; report: string; meta: string }
  /** the lanes, owners and findings of one revision, as JSON text */
  | { type: "lanes"; id: string; lanes: string }
  | { type: "failed"; id: string; error: string };
