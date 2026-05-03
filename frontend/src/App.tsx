import { lazy, Suspense } from "react";
import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthGate } from "./components/auth/AuthGate";
import Layout from "./components/Layout";
import { AuthProvider } from "./context/AuthContext";
import { PlanningSessionProvider } from "./context/PlanningSessionContext";
import { usePlanningSession } from "./hooks/usePlanningSession";
import { normalizeToplineHealthStatus } from "./lib/healthStatus";
import { isProtectedDataModeEnabled } from "./lib/runtimeConfig";

const ScenarioPlanner = lazy(() => import("./pages/ScenarioPlanner"));
const BookingsBridge = lazy(() => import("./pages/BookingsBridge"));
const CapacityHeadcount = lazy(() => import("./pages/CapacityHeadcount"));
const FunnelHealth = lazy(() => import("./pages/FunnelHealth"));
const PipelineInventory = lazy(() => import("./pages/PipelineInventory"));
const ExportPack = lazy(() => import("./pages/ExportPack"));
const Methodology = lazy(() => import("./pages/Methodology"));
const AuditReadiness = lazy(() => import("./pages/AuditReadiness"));
const TargetSetter = lazy(() => import("./pages/TargetSetter"));

function RouteLoading() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <p className="text-sm text-text-secondary">Loading page...</p>
    </div>
  );
}

function ProtectedApp() {
  const {
    snapshot,
    orgProfiles,
    selectedOrgProfile,
    plans,
    selectedPlan,
    requestedPlanId,
    activeRenderedPlanId,
    planSelectionNotice,
    planCatalogDiagnostics,
    loading,
    error,
    selectOrgProfile,
    selectPlan,
  } = usePlanningSession();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <p className="text-sm text-text-secondary">Loading snapshot...</p>
      </div>
    );
  }

  if (error || !snapshot) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <div className="text-center">
          <p className="mb-1 text-sm font-medium text-red-400">
            Failed to load snapshot
          </p>
          <p className="text-xs text-text-muted">{error ?? "Unknown error"}</p>
        </div>
      </div>
    );
  }

  const capacityWarnings = snapshot.model_output.bookings_bridge.capacity_warnings ?? [];
  const healthStatusRaw =
    (snapshot.health_status?.overall_status as string | undefined) ??
    (snapshot.health_status?.status as string | undefined);
  const healthStatus = normalizeToplineHealthStatus(
    healthStatusRaw,
    capacityWarnings.length,
  );

  function renderRoute(element: ReactNode) {
    return <Suspense fallback={<RouteLoading />}>{element}</Suspense>;
  }

  return (
    <PlanningSessionProvider
      value={{
        snapshot,
        orgProfiles,
        selectedOrgProfile,
        selectOrgProfile,
        plans,
        selectedPlan,
        requestedPlanId,
        activeRenderedPlanId,
        planSelectionNotice,
        planCatalogDiagnostics,
        selectPlan,
        healthStatus,
        snapshotMeta: {
          as_of: snapshot.as_of,
          generated_at: snapshot.generated_at,
          git_sha: snapshot.git_sha,
        },
      }}
    >
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/bookings" replace />} />
          <Route path="/" element={<Navigate to="/bookings" replace />} />
          <Route path="/scenario" element={renderRoute(<ScenarioPlanner />)} />
          <Route path="/bookings" element={renderRoute(<BookingsBridge />)} />
          <Route path="/capacity" element={renderRoute(<CapacityHeadcount />)} />
          <Route path="/funnel" element={renderRoute(<FunnelHealth />)} />
          <Route path="/inventory" element={renderRoute(<PipelineInventory />)} />
          <Route path="/audit" element={renderRoute(<AuditReadiness />)} />
          <Route path="/export" element={renderRoute(<ExportPack />)} />
          <Route path="/methodology" element={renderRoute(<Methodology />)} />
          <Route path="/targets" element={renderRoute(<TargetSetter />)} />
        </Route>
      </Routes>
    </PlanningSessionProvider>
  );
}

export default function App() {
  if (!isProtectedDataModeEnabled()) {
    return <ProtectedApp />;
  }

  return (
    <AuthProvider>
      <AuthGate>
        <ProtectedApp />
      </AuthGate>
    </AuthProvider>
  );
}
