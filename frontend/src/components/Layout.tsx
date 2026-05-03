import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuthContext } from "../context/AuthContext";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { StalenessBanner } from "./StalenessBanner";

const TABS = [
  { to: "/bookings", label: "Bookings Bridge" },
  { to: "/capacity", label: "Capacity & Headcount" },
  { to: "/funnel", label: "Funnel Health" },
  { to: "/inventory", label: "Pipeline Inventory" },
  { to: "/audit", label: "Audit" },
  { to: "/export", label: "Export Pack" },
  { to: "/methodology", label: "Methodology" },
] as const;

const SCENARIO_TAB = { to: "/scenario", label: "Scenario Planner" } as const;

export default function Layout() {
  const location = useLocation();
  const { user, signOut } = useAuthContext();
  const {
    snapshot,
    orgProfiles,
    selectedOrgProfile,
    selectOrgProfile,
    plans,
    requestedPlanId,
    activeRenderedPlanId,
    planSelectionNotice,
    selectPlan,
    healthStatus,
  } =
    usePlanningSessionContext();
  const generatedAt = snapshot.generated_at;

  const staleDays = generatedAt
    ? Math.floor((Date.now() - new Date(generatedAt).getTime()) / (1000 * 60 * 60 * 24))
    : 0;
  const showStaleBanner = staleDays > 1;

  function withCurrentSearch(pathname: string) {
    return {
      pathname,
      search: location.search,
    };
  }

  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-text-primary">Forecast Tieout</h1>
          {selectedOrgProfile && (
            orgProfiles.length > 1 ? (
              <select
                id="org-profile-selector"
                name="org-profile-selector"
                value={selectedOrgProfile.id}
                onChange={(e) => selectOrgProfile(e.target.value)}
                className="bg-surface-raised border border-border rounded px-3 py-1 text-sm text-text-primary"
              >
                {orgProfiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            ) : (
              <span className="rounded-full border border-border bg-surface-raised px-3 py-1 text-xs font-medium text-text-secondary">
                {selectedOrgProfile.name}
              </span>
            )
          )}
          {plans.length > 0 && (
            <select
              id="plan-selector"
              name="plan-selector"
              value={activeRenderedPlanId ?? ""}
              onChange={(e) => selectPlan(e.target.value)}
              className="bg-surface-raised border border-border rounded px-3 py-1 text-sm text-text-primary"
            >
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-2">
          {healthStatus && (
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                healthStatus === "healthy"
                  ? "bg-green-500"
                  : healthStatus === "warning"
                    ? "bg-yellow-500"
                    : healthStatus === "critical"
                      ? "bg-red-500"
                      : "bg-gray-400"
              }`}
              title={`Status: ${healthStatus}`}
            />
          )}
          {generatedAt && (
            <span className="text-xs text-text-muted">
              Data: {new Date(generatedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}
            </span>
          )}
          {user?.email && (
            <>
              <span className="text-xs text-text-muted">{user.email}</span>
              <button
                type="button"
                onClick={() => void signOut()}
                className="rounded px-2 py-1 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-raised transition-colors"
              >
                Sign out
              </button>
            </>
          )}
        </div>
      </header>
      {planSelectionNotice ? (
        <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-900">
          {planSelectionNotice.message}
          {requestedPlanId && requestedPlanId !== activeRenderedPlanId ? (
            <span className="ml-2 text-amber-700">
              Requested `{requestedPlanId}`, active `{activeRenderedPlanId ?? "none"}`.
            </span>
          ) : null}
        </div>
      ) : null}
      <nav className="border-b border-border px-6 flex gap-1 overflow-x-auto items-center">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={withCurrentSearch(tab.to)}
            className={({ isActive }) =>
              `px-4 py-2 text-sm whitespace-nowrap border-b-2 transition-colors ${
                isActive
                  ? "border-accent-blue text-accent-blue"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}

        {/* Spacer pushes Scenario Planner to the right */}
        <div className="flex-1" />

        {/* Scenario Planner — distinctive tab on the far right */}
        <NavLink
          to={withCurrentSearch(SCENARIO_TAB.to)}
          className={({ isActive }) =>
            `px-4 py-1.5 text-sm whitespace-nowrap rounded-md transition-colors flex items-center gap-1.5 font-medium ${
              isActive
                ? "bg-blue-600 text-white shadow-sm"
                : "bg-blue-500 text-white hover:bg-blue-600 shadow-sm"
            }`
          }
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
          </svg>
          {SCENARIO_TAB.label}
        </NavLink>
      </nav>
      {showStaleBanner && <StalenessBanner staleDays={staleDays} />}
      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
