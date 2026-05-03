import { describe, expect, it } from "vitest";

import {
  buildConnectorPolicyNotes,
  createFallbackOrgProfile,
  normalizeOrgProfile,
} from "../orgProfiles";
import type { RawOrgProfile } from "../orgProfiles";

describe("org profile helpers", () => {
  it("normalizes a raw profile with data urls", () => {
    const raw: RawOrgProfile = {
      id: "demo-org",
      slug: "demo-org",
      name: "Demo Org",
      description: "A demo org profile for testing.",
      version: 1,
      data: {
        snapshot: "./demo-org/snapshot.json",
        plan_manifest: "./demo-org/plans/index.json",
      },
      connectors: { crm: "CRM", warehouse: "Warehouse" },
    };

    const profile = normalizeOrgProfile(raw, {
      manifestId: "demo-org",
      profileUrl: "http://localhost:3000/data/profiles/demo-org.json",
      dataRoot: "http://localhost:3000/data",
    });

    expect(profile.id).toBe("demo-org");
    expect(profile.data.snapshotUrl).toBe("http://localhost:3000/data/profiles/demo-org/snapshot.json");
    expect(profile.data.planManifestUrl).toBe(
      "http://localhost:3000/data/profiles/demo-org/plans/index.json",
    );
    expect(profile.connectors.crm).toBe("CRM");
    expect(profile.connectors.warehouse).toBe("Warehouse");
  });

  it("builds connector priority notes from the profile contract", () => {
    const profile = createFallbackOrgProfile("/data");
    const notes = buildConnectorPolicyNotes(profile);

    expect(notes).toHaveLength(3);
    expect(notes[0]).toContain("Warehouse observed -> CRM observed -> Config fallback");
    expect(notes[2]).toContain("warehouse + roster.yaml -> roster.yaml -> Config fallback");
  });
});
