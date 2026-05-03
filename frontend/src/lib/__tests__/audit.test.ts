import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Snapshot } from "../../types/snapshot";
import {
  buildActualMonthLockRows,
  buildAcceptedScopeExclusions,
  buildFallbackExceptions,
  buildAuditReportText,
  buildQuarterTieoutRows,
} from "../audit";

function loadSnapshot(): Snapshot {
  const snapshotPath = resolve(
    fileURLToPath(new URL("../../../public/data/profiles/acme-saas/snapshot.json", import.meta.url))
  );
  return JSON.parse(readFileSync(snapshotPath, "utf-8")) as Snapshot;
}

describe("audit readiness helpers", () => {
  it("shows quarter tie-out across finance-facing pages", () => {
    const snapshot = loadSnapshot();
    const rows = buildQuarterTieoutRows(snapshot);

    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.status === "green")).toBe(true);
    expect(rows.every((row) => row.maxDelta <= 1)).toBe(true);
  });

  it("shows actual months as locked in the saved snapshot", () => {
    const snapshot = loadSnapshot();
    const rows = buildActualMonthLockRows(snapshot);

    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.status === "green")).toBe(true);
    expect(rows.every((row) => Math.abs(row.futureWins) <= 1)).toBe(true);
  });

  it("includes tie-out and lock sections in the exported audit report", () => {
    const snapshot = loadSnapshot();
    const report = buildAuditReportText(snapshot);

    expect(report).toContain("Quarter Tie-Out");
    expect(report).toContain("Actual Month Locks");
    expect(report).toContain("Accepted Scope Exclusions");
    expect(report).toContain("Inactive Fallback Debt");
  });

  it("keeps finance-critical exceptions empty for the saved snapshot", () => {
    const snapshot = loadSnapshot();
    const rows = buildFallbackExceptions(snapshot);

    expect(rows).toEqual([]);
  });

  it("normalizes legacy PLG scope exclusions onto the stage-1 key", () => {
    const rows = buildAcceptedScopeExclusions({
      provenance: {
        funnel_rates: {
          plg_signup_to_pql: { source: "static" },
          plg_pql_to_s0: { source: "static" },
        },
      },
      health_status: {},
      model_output: {
        bookings_bridge: { trajectory_quarters: [] },
        funnel_health: { trajectory_quarters: [] },
        capacity_headcount: { trajectory_quarters: [] },
      },
      scenario_building_blocks: {
        months: [],
        monthly_inventory_wins: [],
        monthly_total_expected: [],
        monthly_future_wins: [],
        monthly_is_actual: [],
      },
    } as unknown as Snapshot);

    expect(rows.map((row) => row.label)).toEqual([
      "plg_signup_to_pql",
      "plg_pql_to_s1",
    ]);
  });
});
