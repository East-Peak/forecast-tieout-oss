import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getSupabaseClientMock } = vi.hoisted(() => ({
  getSupabaseClientMock: vi.fn(),
}));

vi.mock("../supabase", () => ({
  getSupabaseClient: getSupabaseClientMock,
}));

import type { OrgProfile } from "../orgProfiles";
import {
  ProtectedDataAccessError,
  loadOrgProfileCatalog,
  loadPlanCatalog,
  loadSnapshotFile,
} from "../protectedDataCatalog";

function makeBlobJson(value: unknown): Blob {
  return new Blob([JSON.stringify(value)], { type: "application/json" });
}

function makeClient({
  session = { access_token: "token", user: { email: "user@example.com" } },
  downloads = {},
}: {
  session?: { access_token: string; user: { email?: string } } | null;
  downloads?: Record<string, { data?: Blob | null; error?: unknown }>;
}) {
  return {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session },
        error: null,
      })),
    },
    storage: {
      from: vi.fn(() => ({
        download: vi.fn(async (path: string) => {
          const match = downloads[path];
          if (!match) {
            return {
              data: null,
              error: { message: `missing ${path}`, statusCode: "404" },
            };
          }
          return {
            data: match.data ?? null,
            error: match.error ?? null,
          };
        }),
      })),
    },
  };
}

describe("protectedDataCatalog", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_PROTECTED_DATA_MODE", "supabase-private");
    vi.stubEnv("VITE_SUPABASE_ARTIFACT_BUCKET", "forecast-data");
    vi.stubEnv("VITE_SUPABASE_ARTIFACT_PREFIX", "");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it("fails hard when no authenticated session exists", async () => {
    getSupabaseClientMock.mockReturnValue(makeClient({ session: null }));

    await expect(loadOrgProfileCatalog()).rejects.toMatchObject({
      kind: "auth-required",
    } satisfies Partial<ProtectedDataAccessError>);
  });

  it("loads protected snapshot artifacts from storage without public fallback", async () => {
    getSupabaseClientMock.mockReturnValue(
      makeClient({
        downloads: {
          "profiles/demo-org/snapshot.json": {
            data: makeBlobJson({ as_of: "2026-03-31", model_output: {}, roster: {}, rates: {} }),
          },
        },
      }),
    );

    const profile = {
      id: "demo-org",
      slug: "demo-org",
      name: "Demo Org",
      description: "",
      version: 1,
      data: {
        snapshotUrl: "https://protected.local/profiles/demo-org/snapshot.json",
        planManifestUrl: "https://protected.local/profiles/demo-org/plans/index.json",
      },
      connectors: {
        crm: "Salesforce",
        warehouse: "warehouse",
        fallbackOrder: {},
      },
      metadata: {},
      trust: {
        financeMotion: "Sales-led",
        timingSemantics: {
          wins: "CloseDate",
          losses: "Closed At",
          pipelineActuals: "First S2 entry",
        },
      },
    } satisfies OrgProfile;

    const snapshot = await loadSnapshotFile(profile);

    expect(snapshot.as_of).toBe("2026-03-31");
  });

  it("does not double-prefix artifact keys when storage uses a nested prefix", async () => {
    vi.stubEnv("VITE_SUPABASE_ARTIFACT_PREFIX", "prod/forecast");

    getSupabaseClientMock.mockReturnValue(
      makeClient({
        downloads: {
          "prod/forecast/profiles/index.json": {
            data: makeBlobJson({
              profiles: [{ id: "demo-org", path: "./demo-org.json" }],
            }),
          },
          "prod/forecast/profiles/demo-org.json": {
            data: makeBlobJson({
              id: "demo-org",
              slug: "demo-org",
              name: "Demo Org",
              data: {
                snapshot: "./demo-org/snapshot.json",
                plan_manifest: "./demo-org/plans/index.json",
              },
            }),
          },
          "prod/forecast/profiles/demo-org/snapshot.json": {
            data: makeBlobJson({ as_of: "2026-03-31", model_output: {}, roster: {}, rates: {} }),
          },
        },
      }),
    );

    const profiles = await loadOrgProfileCatalog();
    const snapshot = await loadSnapshotFile(profiles[0]);

    expect(profiles[0]?.data.snapshotUrl).toBe(
      "https://protected.local/prod/forecast/profiles/demo-org/snapshot.json",
    );
    expect(snapshot.as_of).toBe("2026-03-31");
  });

  it("rethrows authorization failures instead of degrading them into plan diagnostics", async () => {
    getSupabaseClientMock.mockReturnValue(
      makeClient({
        downloads: {
          "profiles/demo-org/plans/index.json": {
            data: makeBlobJson({
              plans: [{ id: "draft", path: "./mar-fy26-operating-draft.json" }],
            }),
          },
          "profiles/demo-org/plans/mar-fy26-operating-draft.json": {
            error: { message: "forbidden", statusCode: "403" },
          },
        },
      }),
    );

    const profile = {
      id: "demo-org",
      slug: "demo-org",
      name: "Demo Org",
      description: "",
      version: 1,
      data: {
        snapshotUrl: "https://protected.local/profiles/demo-org/snapshot.json",
        planManifestUrl: "https://protected.local/profiles/demo-org/plans/index.json",
      },
      connectors: {
        crm: "Salesforce",
        warehouse: "warehouse",
        fallbackOrder: {},
      },
      metadata: {},
      trust: {
        financeMotion: "Sales-led",
        timingSemantics: {
          wins: "CloseDate",
          losses: "Closed At",
          pipelineActuals: "First S2 entry",
        },
      },
    } satisfies OrgProfile;

    await expect(loadPlanCatalog(profile)).rejects.toMatchObject({
      kind: "auth-denied",
    } satisfies Partial<ProtectedDataAccessError>);
  });
});
