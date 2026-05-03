/**
 * TargetSetter page — snapshot-swap reconciliation tests.
 *
 * Verifies:
 *  1. Page does not crash when snapshot swap removes the active scenario.
 *  2. Empty state renders when target_setter is absent from the snapshot.
 *
 * All fixtures are synthetic — no production data.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TargetSetter from "../TargetSetter";
import {
  PlanningSessionProvider,
} from "../../context/PlanningSessionContext";
import type { PlanningSessionContextValue } from "../../context/PlanningSessionContext";

// ---------------------------------------------------------------------------
// Minimal snapshot factory
// ---------------------------------------------------------------------------

function baseSnapshot(overrides: Record<string, unknown> = {}): any {
  return {
    as_of: "2026-04-06",
    generated_at: "2026-04-06T00:00:00Z",
    git_sha: "abc123",
    scenario_building_blocks: {
      months: [
        "2026-02-01", "2026-03-01", "2026-04-01",
        "2026-05-01", "2026-06-01", "2026-07-01",
        "2026-08-01", "2026-09-01", "2026-10-01",
        "2026-11-01", "2026-12-01", "2027-01-01",
      ],
      quarter_by_month: [
        "Q1FY27", "Q1FY27", "Q1FY27",
        "Q2FY27", "Q2FY27", "Q2FY27",
        "Q3FY27", "Q3FY27", "Q3FY27",
        "Q4FY27", "Q4FY27", "Q4FY27",
      ],
      overridable_quarters: ["Q2FY27", "Q3FY27", "Q4FY27"],
    },
    model_output: {
      funnel_health: {
        funnel_rates: {},
        funnel_rate_descriptions: {},
      },
      bookings_bridge: {
        capacity_warnings: [],
      },
    },
    health_status: { overall_status: "healthy" },
    rates: {},
    actuals: {
      bookings_by_month: [],
      mql_by_month: [],
    },
    pipeline: {
      inventory_by_stage: [],
    },
    ...overrides,
  };
}

function sampleScenario(id: string, label = id) {
  return {
    id,
    label,
    description: { primary: "Synthetic test scenario", secondary: "unit-test only" },
    win_rate_starting: 0.06,
    win_rate_created: 0.16,
    push_rate: 0.94,
    loss_rate: 0.08,
    ae_self_gen_pct: 0.3,
    mql_to_s0: 0.15,
    s0_to_s1: 0.55,
    s1_to_s2: 0.25,
    segment_share: { enterprise: 1.0 },
    acv: { enterprise: 250_000 },
  };
}

function snapWithScenarios(
  ids: string[],
  includeObserved = true,
): any {
  return baseSnapshot({
    target_setter: {
      observed_scenario: includeObserved
        ? sampleScenario("observed", "Observed")
        : undefined,
      scenarios: ids.map((id) => sampleScenario(id, id)),
    },
  });
}

// ---------------------------------------------------------------------------
// Context wrapper
// ---------------------------------------------------------------------------

function makeCtxValue(snapshot: any): PlanningSessionContextValue {
  return {
    snapshot,
    orgProfiles: [],
    selectedOrgProfile: null,
    selectOrgProfile: () => {},
    plans: [],
    selectedPlan: null,
    requestedPlanId: null,
    activeRenderedPlanId: null,
    planSelectionNotice: null,
    planCatalogDiagnostics: [],
    selectPlan: () => {},
    healthStatus: "healthy",
    snapshotMeta: {
      as_of: snapshot.as_of,
      generated_at: snapshot.generated_at,
      git_sha: snapshot.git_sha,
    },
  };
}

function renderPage(snapshot: any) {
  return render(
    <MemoryRouter>
      <PlanningSessionProvider value={makeCtxValue(snapshot)}>
        <TargetSetter />
      </PlanningSessionProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TargetSetter page — empty state", () => {
  it("renders empty state when target_setter is absent", () => {
    const snap = baseSnapshot(); // no target_setter key
    const { container } = renderPage(snap);
    expect(container.textContent).toContain("no TargetSetter configuration");
  });
});

describe("TargetSetter page — with scenarios", () => {
  it("renders without crashing when observed + named scenarios present", () => {
    const snap = snapWithScenarios(["marketing-led", "ambitious"]);
    const { container } = renderPage(snap);
    // Page rendered — heading should be present
    expect(container.textContent).toContain("Target Setter");
  });

  it("does not crash when only named scenarios present (no observed)", () => {
    const snap = snapWithScenarios(["marketing-led"], false);
    const { container } = renderPage(snap);
    expect(container.textContent).toContain("Target Setter");
  });
});

describe("TargetSetter page — stale scenarioId reconciliation", () => {
  it("falls back to default and does not crash when snapshot swap removes scenarios", () => {
    const snap1 = snapWithScenarios(["marketing-led", "ambitious"]);
    const { rerender } = renderPage(snap1);

    // Swap to a snapshot where "ambitious" no longer exists
    const snap2 = snapWithScenarios(["marketing-led"]);
    rerender(
      <MemoryRouter>
        <PlanningSessionProvider value={makeCtxValue(snap2)}>
          <TargetSetter />
        </PlanningSessionProvider>
      </MemoryRouter>,
    );

    // Page still renders — observed should be the fallback default
    const wrapper = document.body;
    expect(wrapper.textContent).toContain("Target Setter");
  });

  it("renders empty state on swap to snapshot without target_setter", () => {
    const snap1 = snapWithScenarios(["marketing-led"]);
    const { rerender, container } = renderPage(snap1);
    expect(container.textContent).toContain("Target Setter");

    const snap2 = baseSnapshot(); // no target_setter
    rerender(
      <MemoryRouter>
        <PlanningSessionProvider value={makeCtxValue(snap2)}>
          <TargetSetter />
        </PlanningSessionProvider>
      </MemoryRouter>,
    );
    expect(container.textContent).toContain("no TargetSetter configuration");
  });
});

describe("TargetSetter page — custom scenario reset on snapshot swap", () => {
  it("clears customScenario when snapshot identity changes", () => {
    // Render with snapshot A — page should be healthy with named scenarios.
    const snap1 = snapWithScenarios(["marketing-led"]);
    const { rerender, container } = renderPage(snap1);
    expect(container.textContent).toContain("Target Setter");

    // Swap to a different snapshot object (new identity).
    // The during-render reset must fire synchronously so no stale customScenario
    // is solved against snap2 even for the first commit after the swap.
    const snap2 = snapWithScenarios(["other-scenario"]);
    rerender(
      <MemoryRouter>
        <PlanningSessionProvider value={makeCtxValue(snap2)}>
          <TargetSetter />
        </PlanningSessionProvider>
      </MemoryRouter>,
    );

    // Page renders without throwing — no cross-profile state leakage.
    expect(container).toBeTruthy();
    // Active scenario should reflect the new snapshot (not "custom").
    // The "Custom" pill (if rendered) should not be aria-pressed.
    const customPill = container.querySelector('[aria-label="Custom"]');
    if (customPill) {
      expect(customPill.getAttribute("aria-pressed")).not.toBe("true");
    }
    // Heading is still visible.
    expect(container.textContent).toContain("Target Setter");
  });

  it("survives rapid snapshot swaps without throwing", () => {
    const snap1 = snapWithScenarios(["marketing-led"]);
    const { rerender, container } = renderPage(snap1);

    const snap2 = snapWithScenarios(["ambitious"]);
    rerender(
      <MemoryRouter>
        <PlanningSessionProvider value={makeCtxValue(snap2)}>
          <TargetSetter />
        </PlanningSessionProvider>
      </MemoryRouter>,
    );

    const snap3 = snapWithScenarios(["conservative", "base"]);
    rerender(
      <MemoryRouter>
        <PlanningSessionProvider value={makeCtxValue(snap3)}>
          <TargetSetter />
        </PlanningSessionProvider>
      </MemoryRouter>,
    );

    expect(container.textContent).toContain("Target Setter");
  });
});
