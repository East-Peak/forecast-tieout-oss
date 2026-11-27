import { createContext, useContext, useEffect, useMemo, useReducer, useRef, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { TieoutReport } from "../generated/report";
import type { YourPlanStore } from "../editor/store";
import { YOUR_PLAN, withYourPlan, withYourPlanRow } from "../editor/yourPlan";
import { initialState, reduce, resolveSelection } from "./sessionState";
import type { SessionState } from "./sessionState";
import { readStoredSelection, writeStoredSelection } from "./storage";

export interface Loaders {
  index(): Promise<ReportIndex>;
  report(path: string): Promise<TieoutReport>;
  comparison(path: string): Promise<ScenarioComparison>;
}

interface SessionValue {
  state: SessionState;
  /** Show this company's scenario: writes it to the URL, which the session follows. */
  choose(company: string, scenario: string): void;
  /** Try the choice that failed to load again. */
  retry(): void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession needs a ReportSessionProvider");
  return value;
}

const NO_SUBSCRIPTION = () => () => {};
const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * The company and scenario in the URL (?company=…&scenario=…) decide which report file is
 * loaded. A response that arrives after the visitor has moved on is dropped by the reducer.
 */
export function ReportSessionProvider({
  loaders,
  yourPlan,
  desktop = false,
  children,
}: {
  loaders: Loaders;
  /** The visitor's own plan, computed in the browser: offered only where `desktop` is true. */
  yourPlan?: YourPlanStore;
  desktop?: boolean;
  children: ReactNode;
}) {
  const offered = yourPlan !== undefined && desktop;
  const [state, dispatch] = useReducer(reduce, initialState);
  const [params, setParams] = useSearchParams();
  const company = params.get("company");
  const scenario = params.get("scenario");
  const firstRequest = useRef({ company, scenario });

  useEffect(() => {
    loaders.index().then(
      (index) =>
        dispatch({
          type: "indexLoaded",
          index: offered ? withYourPlan(index) : index,
          ...resolveSelection(offered ? withYourPlan(index) : index, firstRequest.current, readStoredSelection()),
        }),
      (e: unknown) => dispatch({ type: "indexFailed", error: messageOf(e) }),
    );
  }, [loaders, offered]);

  // The URL changed after the first load (a link, the back button, a selector): follow it.
  const index = "index" in state ? state.index : null;
  useEffect(() => {
    if (!index || !company) return;
    const { selection, notice } = resolveSelection(index, { company, scenario }, null);
    dispatch({ type: "select", selection, notice });
    // an address the index cannot satisfy is corrected where the visitor can see it
    if (company !== selection.company || scenario !== selection.scenario) {
      setParams({ company: selection.company, scenario: selection.scenario }, { replace: true });
    }
  }, [index, company, scenario, setParams]);

  // A choice the session settled on (a default, a correction) is written into the URL.
  const settled = "selection" in state ? state.selection : null;
  useEffect(() => {
    if (!settled) return;
    if (params.get("company") !== settled.company || params.get("scenario") !== settled.scenario) {
      setParams({ company: settled.company, scenario: settled.scenario }, { replace: true });
    }
    // only when the session's own choice changes; the URL leading it is handled above
  }, [settled?.company, settled?.scenario]);

  // Load the report for the choice being waited on.
  const waiting = state.status === "loading" ? state.selection : null;
  const requestId = state.status === "loading" ? state.requestId : 0;
  useEffect(() => {
    if (!waiting || !index) return;
    const entry = index.companies.find((c) => c.id === waiting.company);
    const chosen = entry?.scenarios.find((s) => s.id === waiting.scenario);
    if (!entry || !chosen) {
      dispatch({ type: "failed", requestId, error: "the index does not list this report" });
      return;
    }
    const own = chosen.id === YOUR_PLAN && yourPlan ? yourPlan.load(waiting.company) : null;
    Promise.all([own ? own.then((a) => a.report) : loaders.report(chosen.report), loaders.comparison(entry.comparison)]).then(
      ([report, fileComparison]) => {
        const comparison = own ? withYourPlanRow(fileComparison, yourPlan!.snapshot.applied[waiting.company].comparison) : fileComparison;
        if (report.schema_version !== index.schema_version) {
          dispatch({
            type: "failed",
            requestId,
            error: `${chosen.report} is schema ${String(report.schema_version)}; this app reads ${index.schema_version}`,
          });
        } else {
          const asked = `${waiting.company}/${waiting.scenario}`;
          const identity = report.inputs?.identity;
          const got = identity ? `${identity.company}/${identity.scenario}` : "no company or scenario";
          if (got !== asked) {
            dispatch({ type: "failed", requestId, error: `${chosen.report} is the report for ${got}, not ${asked}` });
          } else if (comparison.company !== waiting.company) {
            dispatch({ type: "failed", requestId, error: `${entry.comparison} is the comparison for ${String(comparison.company)}, not ${waiting.company}` });
          } else {
            dispatch({ type: "loaded", requestId, report, comparison });
          }
        }
      },
      (e: unknown) => dispatch({ type: "failed", requestId, error: messageOf(e) }),
    );
  }, [waiting?.company, waiting?.scenario, requestId, index, loaders, yourPlan]);

  // The visitor applied a plan while their plan is on screen: show it, with no new load.
  const applied = useSyncExternalStore(
    yourPlan?.subscribe ?? NO_SUBSCRIPTION,
    () => (yourPlan && state.status === "ready" && state.selection.scenario === YOUR_PLAN ? yourPlan.snapshot.applied[state.selection.company] : undefined),
  );
  useEffect(() => {
    if (applied && state.status === "ready" && applied.report !== state.report) {
      dispatch({
        type: "replaced",
        selection: state.selection,
        report: applied.report,
        comparison: withYourPlanRow(state.comparison, applied.comparison),
      });
    }
  }, [applied, state]);

  useEffect(() => {
    // the visitor's own plan is for this visit only: it is never the choice remembered for the next one
    if (state.status === "ready" && state.selection.scenario !== YOUR_PLAN) writeStoredSelection(state.selection);
  }, [state]);

  const value = useMemo<SessionValue>(
    () => ({ state, choose: (c, s) => setParams({ company: c, scenario: s }), retry: () => dispatch({ type: "retry" }) }),
    [state, setParams],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
