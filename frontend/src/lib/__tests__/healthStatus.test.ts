import { describe, expect, it } from "vitest";

import { normalizeToplineHealthStatus } from "../healthStatus";

describe("normalizeToplineHealthStatus", () => {
  it("treats diverged overall status as critical", () => {
    expect(normalizeToplineHealthStatus("diverged", 0)).toBe("critical");
  });

  it("maps green-style health states to healthy", () => {
    expect(normalizeToplineHealthStatus("green", 3)).toBe("healthy");
    expect(normalizeToplineHealthStatus("ok", 3)).toBe("healthy");
    expect(normalizeToplineHealthStatus("aligned", 3)).toBe("healthy");
  });

  it("falls back to capacity warnings when no explicit health status is present", () => {
    expect(normalizeToplineHealthStatus(undefined, 0)).toBe("healthy");
    expect(normalizeToplineHealthStatus(undefined, 1)).toBe("warning");
    expect(normalizeToplineHealthStatus(undefined, 3)).toBe("critical");
  });
});
