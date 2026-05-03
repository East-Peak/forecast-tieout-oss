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

const TARGET_SETTER_TAB = { to: "/targets", label: "Target Setter" } as const;
const SCENARIO_TAB = { to: "/scenario", label: "Scenario Planner" } as const;

// Per-profile descriptors and accent palettes. Drives the org-selector
// dropdown labels (so the company size is obvious at a glance) and the
// top-of-page accent stripe (so each demo profile feels distinct rather
// than under-branded).
const PROFILE_META: Record<
  string,
  { scale: string; accent: string }
> = {
  "sprout-labs": { scale: "$10M FY26 ARR target · early PMF", accent: "bg-teal-500" },
  "sapling-industries": { scale: "$100M FY26 ARR target · scale-up", accent: "bg-emerald-500" },
  "mighty-oak-holdings": { scale: "$800M FY26 ARR target · mature enterprise", accent: "bg-amber-600" },
};

function profileLabel(profile: { id: string; name: string }): string {
  const meta = PROFILE_META[profile.id];
  return meta ? `${profile.name} · ${meta.scale}` : profile.name;
}

function profileAccent(profileId: string | undefined): string {
  return (profileId && PROFILE_META[profileId]?.accent) || "bg-slate-400";
}

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
      {/* Sticky chrome: accent stripe + title/dropdowns + plan notice + tab strip
          stay pinned to the top while page content scrolls underneath, so the
          reader always knows which profile/plan they're looking at. */}
      <div className="sticky top-0 z-40 bg-surface shadow-sm">
      {/* Profile-colored accent stripe; thin enough to read as branding,
          not loud enough to compete with content. */}
      <div className={`h-1 ${profileAccent(selectedOrgProfile?.id)}`} />
      <header className="border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex flex-col leading-tight">
            <h1 className="text-lg font-semibold text-text-primary">Forecast Tieout</h1>
            <p className="text-xs text-text-muted">Plan vs. pipeline reality</p>
          </div>
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
                    {profileLabel(profile)}
                  </option>
                ))}
              </select>
            ) : (
              <span className="rounded-full border border-border bg-surface-raised px-3 py-1 text-xs font-medium text-text-secondary">
                {profileLabel(selectedOrgProfile)}
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

        {/* Spacer pushes the operator action buttons to the right */}
        <div className="flex-1" />

        {/* Target Setter — distinctive button (target/bullseye, emerald).
            Active state gets a darker fill + a contrasting ring so the user
            can see at a glance which operator action is currently selected. */}
        <NavLink
          to={withCurrentSearch(TARGET_SETTER_TAB.to)}
          className={({ isActive }) =>
            `px-4 py-1.5 text-sm whitespace-nowrap rounded-md transition-colors flex items-center gap-1.5 font-medium ${
              isActive
                ? "bg-emerald-700 text-white shadow-md ring-2 ring-emerald-300 ring-offset-2 ring-offset-surface"
                : "bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm"
            }`
          }
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
          </svg>
          {TARGET_SETTER_TAB.label}
        </NavLink>

        {/* Scenario Planner — distinctive button (bar chart, blue) */}
        <NavLink
          to={withCurrentSearch(SCENARIO_TAB.to)}
          className={({ isActive }) =>
            `px-4 py-1.5 text-sm whitespace-nowrap rounded-md transition-colors flex items-center gap-1.5 font-medium ${
              isActive
                ? "bg-blue-700 text-white shadow-md ring-2 ring-blue-300 ring-offset-2 ring-offset-surface"
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
      </div>
      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
