import { lazy, Suspense, useMemo } from "react";
import type { ComponentType, LazyExoticComponent, ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { fileLoaders } from "./data/reportFiles";
import { browserEditor } from "./editor/browserEditor";
import { YourPlanStore } from "./editor/store";
import type { Editor } from "./editor/store";
import { YourPlanProvider, useDesktop } from "./editor/YourPlanContext";
import { ReportSessionProvider } from "./session/ReportSession";
import type { Loaders } from "./session/ReportSession";
import { legacyRedirect } from "./shell/legacyRoutes";
import { LANDING, SCREENS } from "./shell/screens";

/** The five screens, each loaded when first opened. */
const SCREEN_COMPONENTS: Record<string, LazyExoticComponent<ComponentType>> = {
  "/forecast": lazy(() => import("./screens/forecast/ForecastScreen")),
  "/capacity": lazy(() => import("./screens/capacity/CapacityScreen")),
  "/pipeline": lazy(() => import("./screens/pipeline/PipelineScreen")),
  "/plan": lazy(() => import("./screens/plan/PlanScreen")),
  "/trust": lazy(() => import("./screens/trust/TrustScreen")),
};

/** The swimlane prototype: a scratch route, not one of the five screens, so it is not in `SCREENS`. */
const Lanes = lazy(() => import("./lanes/LanesScreen"));

function RouteLoading() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <p className="text-sm text-text-secondary">Loading the screen...</p>
    </div>
  );
}

/** `/` and any other address go to the landing screen, keeping the company and scenario in the query string. */
function ToLanding() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: LANDING, search }} replace />;
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

/** `editor` and `desktop` are the page's own plan editor and whether the window is wide enough for it; tests pass others. */
export default function App({ loaders = fileLoaders, editor = browserEditor, desktop }: { loaders?: Loaders; editor?: Editor; desktop?: boolean }) {
  const wide = useDesktop();
  const store = useMemo(() => new YourPlanStore(editor), [editor]);
  const canEdit = desktop ?? wide;
  return (
    <YourPlanProvider store={store} desktop={canEdit}>
      <OldAddresses>
        <ReportSessionProvider loaders={loaders} yourPlan={store} desktop={canEdit}>
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
              <Route
                path="/lanes"
                element={
                  <Suspense fallback={<RouteLoading />}>
                    <Lanes />
                  </Suspense>
                }
              />
              <Route path="*" element={<ToLanding />} />
            </Route>
          </Routes>
        </ReportSessionProvider>
      </OldAddresses>
    </YourPlanProvider>
  );
}
