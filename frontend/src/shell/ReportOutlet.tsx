import { Outlet } from "react-router-dom";
import { Card } from "../components/ui";
import { useSession } from "../session/ReportSession";

/** The page body: what the session is doing (loading, failed) or, once a report is in, the screen. */
export function ReportOutlet() {
  const { state } = useSession();
  switch (state.status) {
    case "loading-index":
      return <Status title="Loading the reports" detail="Reading the list of companies and scenarios." />;
    case "index-error":
      return <Status tone="error" title="The reports could not be loaded" detail={state.error} />;
    case "loading": {
      const company = state.index.companies.find((c) => c.id === state.selection.company);
      return <Status title={`Loading ${company?.name ?? "the report"}`} detail="Reading the core's report for this scenario." />;
    }
    case "error":
      return (
        <Status
          tone="error"
          title="This report could not be loaded"
          detail={`${state.error}. Choose another company or scenario above.`}
        />
      );
    case "ready":
      return <Outlet />;
  }
}

function Status({ title, detail, tone }: { title: string; detail: string; tone?: "error" }) {
  return (
    <Card className="mx-auto mt-8 max-w-xl p-6 text-center" role={tone === "error" ? "alert" : "status"} data-testid="session-status">
      <p className={`text-sm font-semibold ${tone === "error" ? "text-red-700" : "text-ft-brand"}`}>{title}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </Card>
  );
}
