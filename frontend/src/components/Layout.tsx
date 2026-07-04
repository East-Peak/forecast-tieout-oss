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
      <div className="sticky top-0 z-40 bg-surface shadow-sm">
        <div className={`h-1 ${profileAccent(selectedOrgProfile?.id)}`} />
        <header className="border-b border-border px-6 py-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-col leading-tight">
              <h1 className="font-display text-2xl font-semibold text-ft-brand">Forecast Tieout</h1>
              <p className="text-sm text-text-muted">Reconcile the revenue plan against pipeline reality.</p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex flex-wrap items-end gap-3 rounded-ft border border-slate-200 bg-slate-50/80 px-3 py-2">
                {selectedOrgProfile && (
                  <label className="grid min-w-[240px] gap-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500">Company</span>
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className={`inline-block h-2.5 w-2.5 rounded-full ${profileAccent(selectedOrgProfile.id)}`}
                      />
                      {orgProfiles.length > 1 ? (
                        <select
                          id="org-profile-selector"
                          name="org-profile-selector"
                          value={selectedOrgProfile.id}
                          onChange={(e) => selectOrgProfile(e.target.value)}
                          className="min-w-0 flex-1 rounded-ft border border-slate-200 bg-white px-3 py-1.5 text-sm text-text-primary shadow-ft outline-none focus:border-ft-accent focus:ring-2 focus:ring-ft-accentSoft"
                        >
                          {orgProfiles.map((profile) => (
                            <option key={profile.id} value={profile.id}>
                              {profileLabel(profile)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="rounded-ft border border-border bg-white px-3 py-1.5 text-sm font-medium text-text-secondary">
                          {profileLabel(selectedOrgProfile)}
                        </span>
                      )}
                    </span>
                  </label>
                )}
                {plans.length > 0 && (
                  <label className="grid min-w-[180px] gap-1">
                    <span className="text-[11px] font-semibold uppercase text-slate-500">Plan</span>
                    <select
                      id="plan-selector"
                      name="plan-selector"
                      value={activeRenderedPlanId ?? ""}
                      onChange={(e) => selectPlan(e.target.value)}
                      className="rounded-ft border border-slate-200 bg-white px-3 py-1.5 text-sm text-text-primary shadow-ft outline-none focus:border-ft-accent focus:ring-2 focus:ring-ft-accentSoft"
                    >
                      {plans.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>

              {generatedAt && (
                <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-text-secondary shadow-ft">
                  {healthStatus && (
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
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
                  Data {new Date(generatedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}
                </span>
              )}

              {user?.email && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted">{user.email}</span>
                  <button
                    type="button"
                    onClick={() => void signOut()}
                    className="rounded-ft px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-surface-raised hover:text-text-primary"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
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
        <nav className="flex items-center gap-1 overflow-x-auto border-b border-border px-6">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={withCurrentSearch(tab.to)}
              className={({ isActive }) =>
                `whitespace-nowrap border-b-2 px-4 py-2 text-sm transition-colors ${
                  isActive
                    ? "border-ft-accent text-ft-accent"
                    : "border-transparent text-text-secondary hover:text-text-primary"
                }`
              }
            >
              {tab.label}
            </NavLink>
          ))}

          <div className="flex-1" />

          <div className="ml-3 flex items-center gap-1 rounded-ft border border-ft-brand bg-white p-1">
            <span className="px-2 text-[11px] font-semibold uppercase text-ft-brand">Tools</span>
            {[TARGET_SETTER_TAB, SCENARIO_TAB].map((tab) => (
              <NavLink
                key={tab.to}
                to={withCurrentSearch(tab.to)}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 whitespace-nowrap rounded-ft border px-3 py-1.5 text-sm font-medium text-ft-brand transition-colors ${
                    isActive
                      ? "border-ft-brand bg-ft-accentSoft"
                      : "border-transparent hover:bg-ft-accentSoft"
                  }`
                }
              >
                {tab.to === TARGET_SETTER_TAB.to ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
                  </svg>
                )}
                {tab.label}
              </NavLink>
            ))}
          </div>
        </nav>
        {showStaleBanner && <StalenessBanner staleDays={staleDays} />}
      </div>
      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
