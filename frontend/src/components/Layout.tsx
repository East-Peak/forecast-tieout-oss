import { NavLink, useLocation } from "react-router-dom";
import { BindingProvider, Bound, bind } from "../binding/Bound";
import { ReportOutlet } from "../shell/ReportOutlet";
import { SCREENS } from "../shell/screens";
import { useSession } from "../session/ReportSession";

// Each company keeps its accent stripe and dot (the header's look); the label and the description come from index.json.
const ACCENTS: Record<string, string> = {
  "sprout-labs": "bg-teal-500",
  "sapling-industries": "bg-emerald-500",
  "mighty-oak-holdings": "bg-amber-600",
};
const accentOf = (id: string | undefined) => (id && ACCENTS[id]) || "bg-slate-400";

const AS_OF = bind({ id: "header.as-of", source: "index", path: "/companies/{id={company}}/as_of", unit: "date", format: "date" });
const DESCRIPTION = bind({
  id: "header.description",
  source: "index",
  path: "/companies/{id={company}}/description",
  unit: "text",
  format: "text",
});

const selectClass =
  "min-w-0 flex-1 rounded-ft border border-slate-200 bg-white px-3 py-1.5 text-sm text-text-primary shadow-ft outline-none focus:border-ft-accent focus:ring-2 focus:ring-ft-accentSoft";

export default function Layout() {
  const location = useLocation();
  const { state, choose } = useSession();
  const index = "index" in state ? state.index : null;
  const selection = "selection" in state ? state.selection : null;
  const company = index?.companies.find((c) => c.id === selection?.company);
  const withCurrentSearch = (pathname: string) => ({ pathname, search: location.search });

  const header = (
    <div className="sticky top-0 z-40 bg-surface shadow-sm">
      <div className={`h-1 ${accentOf(company?.id)}`} />
      <header className="border-b border-border px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col leading-tight">
            <h1 className="font-display text-2xl font-semibold text-ft-brand">Forecast Tieout</h1>
            <p className="text-sm text-text-muted">Reconcile the revenue plan against pipeline reality.</p>
          </div>

          {index && company && selection ? (
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex flex-wrap items-end gap-3 rounded-ft border border-slate-200 bg-slate-50/80 px-3 py-2">
                <label className="grid min-w-[200px] flex-1 gap-1 sm:min-w-[220px]">
                  <span className="text-[11px] font-semibold uppercase text-slate-500">Company</span>
                  <span className="flex items-center gap-2">
                    <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-full ${accentOf(company.id)}`} />
                    <select
                      id="company-selector"
                      name="company-selector"
                      value={company.id}
                      onChange={(e) => choose(e.target.value, selection.scenario)}
                      className={selectClass}
                    >
                      {index.companies.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </span>
                </label>
                <label className="grid min-w-[160px] flex-1 gap-1">
                  <span className="text-[11px] font-semibold uppercase text-slate-500">Scenario</span>
                  <select
                    id="scenario-selector"
                    name="scenario-selector"
                    value={selection.scenario}
                    onChange={(e) => choose(company.id, e.target.value)}
                    className={selectClass}
                  >
                    {company.scenarios.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {state.status === "ready" ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-text-secondary shadow-ft">
                  Data as of <Bound binding={AS_OF} />
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
        {state.status === "ready" ? (
          <p className="mt-2 text-xs text-text-muted lg:max-w-3xl" data-testid="company-description">
            <Bound binding={DESCRIPTION} />
          </p>
        ) : null}
      </header>
      {"notice" in state && state.notice ? (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 sm:px-6" role="status">
          {state.notice}
        </div>
      ) : null}
      <nav className="flex items-center gap-1 overflow-x-auto border-b border-border px-2 sm:px-6" aria-label="Screens">
        {SCREENS.map((screen) => (
          <NavLink
            key={screen.path}
            to={withCurrentSearch(screen.path)}
            className={({ isActive }) =>
              `whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors sm:px-4 ${
                isActive ? "border-ft-accent text-ft-accent" : "border-transparent text-text-secondary hover:text-text-primary"
              }`
            }
          >
            {screen.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );

  const page = (
    <div className="min-h-screen bg-surface">
      {header}
      <main className="p-4 sm:p-6">
        <ReportOutlet />
      </main>
    </div>
  );

  return state.status === "ready" && selection ? (
    <BindingProvider
      company={selection.company}
      scenario={selection.scenario}
      files={{ report: state.report, index: state.index, comparison: state.comparison }}
      choose={choose}
    >
      {page}
    </BindingProvider>
  ) : (
    page
  );
}
