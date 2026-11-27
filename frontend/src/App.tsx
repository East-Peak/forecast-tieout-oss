import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { fileLoaders } from "./data/reportFiles";
import { ReportSessionProvider } from "./session/ReportSession";
import type { Loaders } from "./session/ReportSession";
import { NotBuilt } from "./shell/NotBuilt";
import { SCREENS } from "./shell/screens";

const ForecastScreen = lazy(() => import("./screens/forecast/ForecastScreen"));

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
          <Route
            path="/forecast"
            element={
              <Suspense fallback={<RouteLoading />}>
                <ForecastScreen />
              </Suspense>
            }
          />
          {SCREENS.filter((s) => s.path !== "/forecast").map((screen) => (
            <Route key={screen.path} path={screen.path} element={<NotBuilt screen={screen} />} />
          ))}
          <Route path="*" element={<ToForecast />} />
        </Route>
      </Routes>
    </ReportSessionProvider>
  );
}
