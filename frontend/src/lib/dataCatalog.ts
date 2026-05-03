import type { Snapshot } from "../types/snapshot";
import {
  derivePlanId,
  normalizePlanPreset,
  PlanValidationError,
} from "./plans";
import type { PlanManifestEntry, PlanPreset, RawPlanPreset } from "./plans";
import {
  createFallbackOrgProfile,
  normalizeOrgProfile,
} from "./orgProfiles";
import type {
  OrgProfile,
  OrgProfileManifestEntry,
  RawOrgProfile,
} from "./orgProfiles";

interface PlanManifest {
  plans?: PlanManifestEntry[];
}

export type PlanCatalogFailureKind =
  | "transient-fetch-failure"
  | "permanent-unavailable"
  | "schema-invalid"
  | "duplicate-id"
  | "id-name-collision";

export interface PlanCatalogDiagnostic {
  scope: "manifest" | "entry";
  kind: PlanCatalogFailureKind;
  message: string;
  entryId?: string | null;
  path?: string | null;
}

export interface PlanCatalogResult {
  plans: PlanPreset[];
  diagnostics: PlanCatalogDiagnostic[];
  status: "ok" | "transient-fetch-failure" | "permanent-unavailable" | "schema-invalid";
}

interface OrgProfileManifest {
  profiles?: OrgProfileManifestEntry[];
}

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function getOrigin(): string {
  return typeof window !== "undefined" ? window.location.origin : "http://localhost";
}

export function getDataRoot(): string {
  const configured = import.meta.env.VITE_DATA_BASE_URL;
  return trimTrailingSlash(configured || "/data");
}

async function fetchJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch (error) {
    const failure = new Error(
      error instanceof Error ? error.message : `Network failure for ${url}`,
    ) as Error & { kind?: PlanCatalogFailureKind };
    failure.kind = "transient-fetch-failure";
    throw failure;
  }
  if (!response.ok) {
    const failure = new Error(`Fetch failed for ${url}: ${response.status}`) as Error & {
      kind?: PlanCatalogFailureKind;
    };
    failure.kind =
      response.status === 404 || response.status === 410
        ? "permanent-unavailable"
        : "transient-fetch-failure";
    throw failure;
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    const failure = new Error(
      error instanceof Error ? error.message : `Invalid JSON for ${url}`,
    ) as Error & { kind?: PlanCatalogFailureKind };
    failure.kind = "schema-invalid";
    throw failure;
  }
}

function resolveRelativeUrl(baseUrl: string, relativePath: string): string {
  const manifestLocation = new URL(baseUrl, getOrigin());
  return new URL(relativePath, manifestLocation).toString();
}

export async function loadOrgProfileCatalog(): Promise<OrgProfile[]> {
  const dataRoot = getDataRoot();
  const manifestUrl = `${dataRoot}/profiles/index.json`;

  try {
    const manifest = await fetchJson<OrgProfileManifest>(manifestUrl);
    const profileEntries = Array.isArray(manifest.profiles) ? manifest.profiles : [];
    const loadedProfiles = await Promise.all(
      profileEntries
        .filter((entry): entry is OrgProfileManifestEntry => Boolean(entry?.path))
        .map(async (entry) => {
          const resolvedPath = resolveRelativeUrl(manifestUrl, entry.path!);
          const profile = await fetchJson<RawOrgProfile>(resolvedPath);
          return normalizeOrgProfile(profile, {
            manifestId: entry.id ?? null,
            profileUrl: resolvedPath,
            dataRoot,
          });
        }),
    );

    if (loadedProfiles.length > 0) return loadedProfiles;
  } catch {
    // Fall back to a single legacy/default profile.
  }

  return [createFallbackOrgProfile(dataRoot)];
}

export async function loadSnapshotFile(profile?: OrgProfile | null): Promise<Snapshot> {
  return fetchJson<Snapshot>(
    profile?.data.snapshotUrl || `${getDataRoot()}/profiles/default/snapshot.json`,
  );
}

function normalizePlanError(error: unknown): {
  kind: PlanCatalogFailureKind;
  message: string;
} {
  if (error instanceof PlanValidationError) {
    return { kind: "schema-invalid", message: error.message };
  }
  if (error instanceof Error && "kind" in error && typeof error.kind === "string") {
    return {
      kind: error.kind as PlanCatalogFailureKind,
      message: error.message,
    };
  }
  return {
    kind: "schema-invalid",
    message: error instanceof Error ? error.message : "Unknown plan catalog error",
  };
}

function invalidateAmbiguousPlans(
  plans: PlanPreset[],
): { plans: PlanPreset[]; diagnostics: PlanCatalogDiagnostic[] } {
  const diagnostics: PlanCatalogDiagnostic[] = [];
  const duplicateIds = new Set<string>();
  const idCounts = new Map<string, number>();
  const nameCounts = new Map<string, number>();

  plans.forEach((plan) => {
    idCounts.set(plan.id, (idCounts.get(plan.id) ?? 0) + 1);
    nameCounts.set(plan.name, (nameCounts.get(plan.name) ?? 0) + 1);
  });

  for (const [id, count] of idCounts.entries()) {
    if (count > 1) duplicateIds.add(id);
  }

  const collidingNames = new Set<string>();
  plans.forEach((plan) => {
    if (idCounts.has(plan.name) || nameCounts.has(plan.id)) {
      collidingNames.add(plan.id);
      collidingNames.add(plan.name);
    }
  });

  const filtered = plans.filter((plan) => {
    if (duplicateIds.has(plan.id)) {
      diagnostics.push({
        scope: "entry",
        kind: "duplicate-id",
        message: `Duplicate normalized plan id ${plan.id}; excluding conflicting entries.`,
        entryId: plan.id,
        path: plan.source.path,
      });
      return false;
    }
    if (collidingNames.has(plan.id) || collidingNames.has(plan.name)) {
      diagnostics.push({
        scope: "entry",
        kind: "id-name-collision",
        message: `Ambiguous plan id/name collision for ${plan.id}; excluding conflicting entries.`,
        entryId: plan.id,
        path: plan.source.path,
      });
      return false;
    }
    return true;
  });

  return { plans: filtered, diagnostics };
}

export async function loadPlanCatalog(profile?: OrgProfile | null): Promise<PlanCatalogResult> {
  const dataRoot = getDataRoot();
  const manifestUrl =
    profile?.data.planManifestUrl || `${dataRoot}/profiles/default/plans/index.json`;

  try {
    const manifest = await fetchJson<PlanManifest>(manifestUrl);
    const planEntries = Array.isArray(manifest.plans) ? manifest.plans : [];
    const diagnostics: PlanCatalogDiagnostic[] = [];
    const loadedPlans: PlanPreset[] = [];

    for (const entry of planEntries.filter(
      (candidate): candidate is PlanManifestEntry => Boolean(candidate?.path),
    )) {
      const resolvedPath = resolveRelativeUrl(manifestUrl, entry.path);
      try {
        const plan = await fetchJson<RawPlanPreset>(resolvedPath);
        loadedPlans.push(
          normalizePlanPreset(
            {
              ...plan,
              id: plan.schema_version === 2 ? plan.id : entry.id || plan.id || derivePlanId(plan.name),
            },
            { manifestId: entry.id ?? null, path: entry.path },
          ),
        );
      } catch (error) {
        const normalized = normalizePlanError(error);
        diagnostics.push({
          scope: "entry",
          kind: normalized.kind,
          message: normalized.message,
          entryId: entry.id ?? null,
          path: entry.path,
        });
      }
    }

    const ambiguity = invalidateAmbiguousPlans(loadedPlans);
    return {
      plans: ambiguity.plans,
      diagnostics: [...diagnostics, ...ambiguity.diagnostics],
      status: "ok",
    };
  } catch (error) {
    const normalized = normalizePlanError(error);
    return {
      plans: [],
      diagnostics: [
        {
          scope: "manifest",
          kind: normalized.kind,
          message: normalized.message,
          path: manifestUrl,
        },
      ],
      status:
        normalized.kind === "permanent-unavailable" ||
        normalized.kind === "transient-fetch-failure" ||
        normalized.kind === "schema-invalid"
          ? normalized.kind
          : "schema-invalid",
    };
  }
}
