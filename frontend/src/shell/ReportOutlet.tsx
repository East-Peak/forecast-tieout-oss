import { Outlet } from "react-router-dom";
import { Card } from "../components/ui";
import { useSyncExternalStore } from "react";
import { useYourPlan } from "../editor/YourPlanContext";
import { YOUR_PLAN } from "../editor/yourPlan";
import { useSession } from "../session/ReportSession";

/** The page body: what the session is doing (loading, failed) or, once a report is in, the screen. */
export function ReportOutlet() {
  const { state, retry } = useSession();
  const yourPlan = useYourPlan();
  const editor = yourPlan?.store.editor;
  const editorStatus = useSyncExternalStore(editor?.subscribe ?? NEVER, () => editor?.status ?? IDLE);
  switch (state.status) {
    case "loading-index":
      return <Status title="Loading the reports" detail="Reading the list of companies and scenarios." />;
    case "index-error":
      return <Status tone="error" title="The reports could not be loaded" detail={state.error} />;
    case "loading": {
      const company = state.index.companies.find((c) => c.id === state.selection.company);
      if (state.selection.scenario === YOUR_PLAN) {
        const doing = editorStatus.phase === "starting" ? editorStatus.progress : "Starting";
        return <Status title={`Computing your plan for ${company?.name ?? "this company"}`} detail={`${doing}. The core runs in your browser; the first time takes a few seconds, and nothing is sent anywhere.`} />;
      }
      return <Status title={`Loading ${company?.name ?? "the report"}`} detail="Reading the core's report for this scenario." />;
    }
    case "error":
      return (
        <Status
          tone="error"
          title="This report could not be loaded"
          detail={`${state.error}. Choose another company or scenario above.`}
          retry={state.selection.scenario === YOUR_PLAN ? retry : undefined}
        />
      );
    case "ready":
      return <Outlet />;
  }
}

const NEVER = () => () => {};
const IDLE = { phase: "idle" } as const;

function Status({ title, detail, tone, retry }: { title: string; detail: string; tone?: "error"; retry?: () => void }) {
  return (
    <Card className="mx-auto mt-8 max-w-xl p-6 text-center" role={tone === "error" ? "alert" : "status"} data-testid="session-status">
      <p className={`text-sm font-semibold ${tone === "error" ? "text-red-700" : "text-ft-brand"}`}>{title}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
      {retry ? (
        <button type="button" onClick={retry} className="mt-3 rounded-ft border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-slate-300">
          Try again
        </button>
      ) : null}
    </Card>
  );
}
