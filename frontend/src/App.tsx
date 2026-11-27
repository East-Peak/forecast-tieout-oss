import { lazy, Suspense } from "react";
import type { ComponentType, LazyExoticComponent, ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { fileLoaders } from "./data/reportFiles";
import { ReportSessionProvider } from "./session/ReportSession";
import type { Loaders } from "./session/ReportSession";
import { legacyRedirect } from "./shell/legacyRoutes";
import { SCREENS } from "./shell/screens";

/** The five screens, each loaded when first opened. */
const SCREEN_COMPONENTS: Record<string, LazyExoticComponent<ComponentType>> = {
  "/forecast": lazy(() => import("./screens/forecast/ForecastScreen")),
  "/capacity": lazy(() => import("./screens/capacity/CapacityScreen")),
  "/pipeline": lazy(() => import("./screens/pipeline/PipelineScreen")),
  "/plan": lazy(() => import("./screens/plan/PlanScreen")),
  "/trust": lazy(() => import("./screens/trust/TrustScreen")),
};

function RouteLoading() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <p className="text-sm text-text-secondary">Loading the screen...</p>
    </div>
  );
}

/** Any other address goes to Forecast, keeping the company and scenario in the query string. */
function ToForecast() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: "/forecast", search }} replace />;
}

/**
 * An address from the old app is sent to the screen that replaced it, with its company carried over.
 * It happens before the session mounts, so the session's first read of the URL is the new one.
 */
function OldAddresses({ children }: { children: ReactNode }) {
  const { pathname, search } = useLocation();
  const destination = legacyRedirect(pathname, search);
  return destination ? <Navigate to={destination} replace /> : <>{children}</>;
}

export default function App({ loaders = fileLoaders }: { loaders?: Loaders }) {
  return (
    <OldAddresses>
      <ReportSessionProvider loaders={loaders}>
        <Routes>
          <Route element={<Layout />}>
            {SCREENS.map((screen) => {
              const Screen = SCREEN_COMPONENTS[screen.path];
              return (
                <Route
                  key={screen.path}
                  path={screen.path}
                  element={
                    <Suspense fallback={<RouteLoading />}>
                      <Screen />
                    </Suspense>
                  }
                />
              );
            })}
            <Route path="*" element={<ToForecast />} />
          </Route>
        </Routes>
      </ReportSessionProvider>
    </OldAddresses>
  );
}
