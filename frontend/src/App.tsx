import { lazy, Suspense } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { fileLoaders } from "./data/reportFiles";
import { ReportSessionProvider } from "./session/ReportSession";
import type { Loaders } from "./session/ReportSession";
import { NotBuilt } from "./shell/NotBuilt";
import { SCREENS } from "./shell/screens";

/** The screens that are built; the rest of the five are placeholders until they are. */
const BUILT: Record<string, LazyExoticComponent<ComponentType>> = {
  "/forecast": lazy(() => import("./screens/forecast/ForecastScreen")),
  "/capacity": lazy(() => import("./screens/capacity/CapacityScreen")),
  "/pipeline": lazy(() => import("./screens/pipeline/PipelineScreen")),
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

export default function App({ loaders = fileLoaders }: { loaders?: Loaders }) {
  return (
    <ReportSessionProvider loaders={loaders}>
      <Routes>
        <Route element={<Layout />}>
          {SCREENS.map((screen) => {
            const Built = BUILT[screen.path];
            return (
              <Route
                key={screen.path}
                path={screen.path}
                element={
                  Built ? (
                    <Suspense fallback={<RouteLoading />}>
                      <Built />
                    </Suspense>
                  ) : (
                    <NotBuilt screen={screen} />
                  )
                }
              />
            );
          })}
          <Route path="*" element={<ToForecast />} />
        </Route>
      </Routes>
    </ReportSessionProvider>
  );
}
