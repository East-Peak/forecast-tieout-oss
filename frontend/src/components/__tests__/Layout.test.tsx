import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Layout from "../Layout";
import {
  PlanningSessionProvider,
  type PlanningSessionContextValue,
} from "../../context/PlanningSessionContext";
import { createFallbackOrgProfile, type OrgProfile } from "../../lib/orgProfiles";
import type { Snapshot } from "../../types/snapshot";

const NOW = new Date("2026-07-06T12:00:00Z").getTime();
const OLD_GENERATED_AT = "2026-07-01T12:00:00Z";

describe("Layout staleness banner", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not show a stale-data warning for old committed demo fixtures", () => {
    renderLayout({ demo: true });

    expect(screen.queryByText(/Run the engine to refresh/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Data Jul 1, 2026/i)).toBeInTheDocument();
  });

  it("continues to show stale-data warnings for old non-demo data", () => {
    renderLayout({ demo: false });

    expect(screen.getByText(/Data is 5 days old/i)).toBeInTheDocument();
  });
});

function renderLayout({ demo }: { demo: boolean }) {
  vi.spyOn(Date, "now").mockReturnValue(NOW);
  const profile = {
    ...createFallbackOrgProfile("/data"),
    id: "demo-org",
    slug: "demo-org",
    name: "Demo Org",
    demo,
  } as OrgProfile;

  return render(
    <MemoryRouter initialEntries={["/bookings"]}>
      <PlanningSessionProvider value={makeContext(profile)}>
        <Layout />
      </PlanningSessionProvider>
    </MemoryRouter>,
  );
}

function makeContext(profile: OrgProfile): PlanningSessionContextValue {
  const snapshot = {
    as_of: "2026-07-01",
    generated_at: OLD_GENERATED_AT,
    git_sha: "abc123",
    model_output: {
      bookings_bridge: {
        capacity_warnings: [],
      },
    },
    health_status: { overall_status: "healthy" },
  } as unknown as Snapshot;

  return {
    snapshot,
    orgProfiles: [profile],
    selectedOrgProfile: profile,
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
