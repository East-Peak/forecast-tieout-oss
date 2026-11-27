import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { TieoutReport } from "../generated/report";

export interface Selection {
  company: string;
  scenario: string;
}

export interface SelectionRequest {
  company?: string | null;
  scenario?: string | null;
}

export type SessionState =
  | { status: "loading-index" }
  | { status: "index-error"; error: string }
  | { status: "loading"; index: ReportIndex; selection: Selection; notice: string | null; requestId: number }
  | { status: "error"; index: ReportIndex; selection: Selection; notice: string | null; requestId: number; error: string }
  | {
      status: "ready";
      index: ReportIndex;
      selection: Selection;
      notice: string | null;
      requestId: number;
      report: TieoutReport;
      comparison: ScenarioComparison;
    };

export type SessionAction =
  | { type: "indexLoaded"; index: ReportIndex; selection: Selection; notice: string | null }
  | { type: "indexFailed"; error: string }
  | { type: "select"; selection: Selection; notice: string | null }
  // an answer carries the id of the request it answers; only the current request's answer counts
  | { type: "loaded"; requestId: number; report: TieoutReport; comparison: ScenarioComparison }
  | { type: "failed"; requestId: number; error: string };

export const initialState: SessionState = { status: "loading-index" };

const same = (a: Selection, b: Selection) => a.company === b.company && a.scenario === b.scenario;

/**
 * Which company and scenario to show: what the URL asks for, else what the visitor
 * chose last time, else the index's default. A request the index cannot satisfy is
 * corrected and said so; a stale remembered choice is dropped quietly.
 */
export function resolveSelection(
  index: ReportIndex,
  requested: SelectionRequest,
  stored: Selection | null,
): { selection: Selection; notice: string | null } {
  const notes: string[] = [];
  const known = (id: string | null | undefined) => index.companies.find((c) => c.id === id);
  let company = known(requested.company);
  if (requested.company && !company) notes.push(`There is no company “${requested.company}”.`);
  const fromStore = !requested.company && stored ? known(stored.company) : undefined;
  company = company ?? fromStore ?? known(index.default_company) ?? index.companies[0];

  const wanted = requested.scenario ?? (fromStore ? stored?.scenario : null);
  let scenario = company.scenarios.find((s) => s.id === wanted);
  if (requested.scenario && !scenario) notes.push(`There is no scenario “${requested.scenario}” for ${company.name}.`);
  scenario = scenario ?? company.scenarios[0];
  return {
    selection: { company: company.id, scenario: scenario.id },
    notice: notes.length ? `${notes.join(" ")} Showing ${company.name}, ${scenario.label}.` : null,
  };
}

export function reduce(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "indexLoaded":
      if (state.status !== "loading-index") return state;
      return { status: "loading", index: action.index, selection: action.selection, notice: action.notice, requestId: 1 };
    case "indexFailed":
      return state.status === "loading-index" ? { status: "index-error", error: action.error } : state;
    case "select":
      if (state.status === "loading-index" || state.status === "index-error") return state;
      if (same(state.selection, action.selection)) {
        // already showing it (or loading it): nothing to fetch, but the correction's notice stands
        return action.notice === null || state.notice === action.notice ? state : { ...state, notice: action.notice };
      }
      return {
        status: "loading",
        index: state.index,
        selection: action.selection,
        notice: action.notice,
        requestId: state.requestId + 1, // arithmetic-ok: a request counter, not a report value
      };
    case "loaded":
      // An answer to any request but the current one (the visitor has moved on, even if back to the same
      // company) is ignored.
      if (state.status !== "loading" || state.requestId !== action.requestId) return state;
      return {
        status: "ready",
        index: state.index,
        selection: state.selection,
        notice: state.notice,
        requestId: state.requestId,
        report: action.report,
        comparison: action.comparison,
      };
    case "failed":
      if (state.status !== "loading" || state.requestId !== action.requestId) return state;
      return {
        status: "error",
        index: state.index,
        selection: state.selection,
        notice: state.notice,
        requestId: state.requestId,
        error: action.error,
      };
  }
}
