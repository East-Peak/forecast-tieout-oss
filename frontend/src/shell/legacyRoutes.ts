/**
 * The old app's nine addresses, kept alive as redirects to the five screens that replaced them.
 * `/capacity` is not listed: the new Capacity screen answers on the same address.
 */
export const LEGACY_ROUTES: Readonly<Record<string, string>> = {
  "/bookings": "/forecast", // Bookings Bridge became Forecast
  "/scenario": "/plan", // Scenario Planner became Plan
  "/targets": "/plan", // Target Setter became Plan (what closes the gap alone)
  "/inventory": "/pipeline", // Pipeline Inventory became Pipeline
  "/funnel": "/pipeline", // Funnel Health is retired; Pipeline is the nearest screen
  "/audit": "/trust", // Audit, Methodology and Export Pack became Trust
  "/methodology": "/trust",
  "/export": "/trust",
};

export interface Destination {
  pathname: string;
  search: string;
}

/**
 * Where an old address should go, or null when it is already a new one. The old app named the
 * company `?profile=`; the new one says `?company=`. The old `?plan=` named one of its own plans,
 * which no scenario matches, so it is dropped.
 */
export function legacyRedirect(pathname: string, search: string): Destination | null {
  const normal = pathname.toLowerCase().replace(/\/+$/, "");
  const moved = LEGACY_ROUTES[normal];
  const params = new URLSearchParams(search);
  const hadOldQuery = params.has("profile") || params.has("plan");
  if (!moved && !hadOldQuery) return null;
  const profile = params.get("profile");
  params.delete("profile");
  params.delete("plan");
  if (profile && !params.has("company")) params.set("company", profile);
  const text = params.toString();
  return { pathname: moved ?? pathname, search: text ? `?${text}` : "" };
}
