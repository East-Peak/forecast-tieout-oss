import { describe, expect, it } from "vitest";
import { LEGACY_ROUTES, legacyRedirect } from "../legacyRoutes";

// The old app's nine routes, from main's router before the rebuild.
const OLD_ROUTES = ["/bookings", "/capacity", "/funnel", "/inventory", "/scenario", "/targets", "/audit", "/export", "/methodology"];

describe("the old route map", () => {
  it.each([
    ["/bookings", "/forecast"],
    ["/scenario", "/plan"],
    ["/targets", "/plan"],
    ["/inventory", "/pipeline"],
    ["/funnel", "/pipeline"],
    ["/audit", "/trust"],
    ["/methodology", "/trust"],
    ["/export", "/trust"],
  ])("%s goes to %s", (from, to) => {
    expect(legacyRedirect(from, "")).toEqual({ pathname: to, search: "" });
  });

  it("/capacity stays where it is: the new Capacity replaces it in place", () => {
    expect(legacyRedirect("/capacity", "")).toBeNull();
  });

  it("every old route is either mapped or replaced in place", () => {
    for (const route of OLD_ROUTES) {
      expect(route === "/capacity" || route in LEGACY_ROUTES).toBe(true);
    }
    expect(Object.keys(LEGACY_ROUTES).sort()).toEqual(OLD_ROUTES.filter((r) => r !== "/capacity").sort());
  });

  it("the old ?profile= becomes ?company=, on a moved route and on a route that stayed", () => {
    expect(legacyRedirect("/bookings", "?profile=sprout-labs")).toEqual({ pathname: "/forecast", search: "?company=sprout-labs" });
    expect(legacyRedirect("/capacity", "?profile=sapling-industries")).toEqual({ pathname: "/capacity", search: "?company=sapling-industries" });
  });

  it("the old ?plan= named a plan of the old app; no scenario matches it, so it is dropped", () => {
    expect(legacyRedirect("/scenario", "?profile=sprout-labs&plan=sprout-fy26-pmf")).toEqual({
      pathname: "/plan",
      search: "?company=sprout-labs",
    });
  });

  it("a company already asked for in the new way wins over the old name", () => {
    expect(legacyRedirect("/bookings", "?company=sprout-labs&profile=sapling-industries")).toEqual({
      pathname: "/forecast",
      search: "?company=sprout-labs",
    });
  });

  it("other query parameters are kept", () => {
    expect(legacyRedirect("/audit", "?profile=sprout-labs&scenario=hires-only")).toEqual({
      pathname: "/trust",
      search: "?scenario=hires-only&company=sprout-labs",
    });
  });

  it("a trailing slash or different case still matches", () => {
    expect(legacyRedirect("/Bookings/", "")).toEqual({ pathname: "/forecast", search: "" });
  });

  it("the new routes with new-style queries are left alone", () => {
    for (const path of ["/forecast", "/capacity", "/pipeline", "/plan", "/trust"]) {
      expect(legacyRedirect(path, "?company=sprout-labs&scenario=as-signed")).toBeNull();
    }
  });
});
