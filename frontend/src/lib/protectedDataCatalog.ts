import type { Snapshot } from "../types/snapshot";
import {
  derivePlanId,
  normalizePlanPreset,
  PlanValidationError,
} from "./plans";
import type { PlanManifestEntry, PlanPreset, RawPlanPreset } from "./plans";
import {
  normalizeOrgProfile,
} from "./orgProfiles";
import type {
  OrgProfile,
  OrgProfileManifestEntry,
  RawOrgProfile,
} from "./orgProfiles";
import type {
  PlanCatalogDiagnostic,
  PlanCatalogFailureKind,
  PlanCatalogResult,
} from "./dataCatalog";
import {
  getProtectedArtifactBucket,
  getProtectedArtifactPrefix,
} from "./runtimeConfig";
import { getSupabaseClient } from "./supabase";

interface PlanManifest {
  plans?: PlanManifestEntry[];
}

interface OrgProfileManifest {
  profiles?: OrgProfileManifestEntry[];
}

type ProtectedDataFailureKind =
  | "auth-required"
  | "auth-denied"
  | "transient-fetch-failure"
  | "permanent-unavailable"
  | "schema-invalid";

export class ProtectedDataAccessError extends Error {
  kind: ProtectedDataFailureKind;

  constructor(kind: ProtectedDataFailureKind, message: string) {
    super(message);
    this.kind = kind;
  }
}

function trimSlashes(value: string): string {
  return value.replace(/^\/+|\/+$/g, "");
}

function buildArtifactKey(relativePath: string): string {
  const prefix = trimSlashes(getProtectedArtifactPrefix());
  const normalizedPath = trimSlashes(relativePath);
  if (
    prefix.length > 0 &&
    (normalizedPath === prefix || normalizedPath.startsWith(`${prefix}/`))
  ) {
    return normalizedPath;
  }
  return prefix.length > 0 ? `${prefix}/${normalizedPath}` : normalizedPath;
}

function buildProtectedUrl(key: string): string {
  return new URL(key, "https://protected.local/").toString();
}

function keyFromProtectedUrl(url: string): string {
  const parsed = new URL(url);
  return trimSlashes(parsed.pathname);
}

function normalizePlanError(error: unknown): {
  kind: PlanCatalogFailureKind;
  message: string;
} {
  if (error instanceof ProtectedDataAccessError) {
    throw error;
  }
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

async function ensureAuthenticatedSession(): Promise<void> {
  const client = getSupabaseClient();
  const {
    data: { session },
    error,
  } = await client.auth.getSession();
  if (error) {
    throw new ProtectedDataAccessError("auth-required", error.message);
  }
  if (!session) {
    throw new ProtectedDataAccessError(
      "auth-required",
      "You must sign in before protected forecast artifacts can be loaded.",
    );
  }
}

async function downloadJson<T>(relativePath: string): Promise<T> {
  await ensureAuthenticatedSession();
  const client = getSupabaseClient();
  const key = buildArtifactKey(relativePath);
  const { data, error } = await client.storage
    .from(getProtectedArtifactBucket())
    .download(key);

  if (error) {
    const rawStatus =
      typeof error === "object" && error !== null && "statusCode" in error
        ? Number.parseInt(String((error as { statusCode?: string }).statusCode ?? ""), 10)
        : Number.NaN;
    if (rawStatus === 401) {
      throw new ProtectedDataAccessError(
        "auth-required",
        "Your session expired before protected forecast artifacts could be loaded.",
      );
    }
    if (rawStatus === 403) {
      throw new ProtectedDataAccessError(
        "auth-denied",
        "You are not authorized to read protected forecast artifacts.",
      );
    }
    if (rawStatus === 404) {
      throw new ProtectedDataAccessError(
        "permanent-unavailable",
        `Protected artifact not found: ${relativePath}`,
      );
    }
    throw new ProtectedDataAccessError(
      "transient-fetch-failure",
      error.message || `Failed to read protected artifact: ${relativePath}`,
    );
  }

  try {
    return JSON.parse(await data.text()) as T;
  } catch (parseError) {
    throw new ProtectedDataAccessError(
      "schema-invalid",
      parseError instanceof Error ? parseError.message : `Invalid JSON for ${relativePath}`,
    );
  }
}

function resolveRelativePath(baseUrl: string, relativePath: string): string {
  return new URL(relativePath, baseUrl).toString();
}

export async function loadOrgProfileCatalog(): Promise<OrgProfile[]> {
  const manifestKey = "profiles/index.json";
  const manifestUrl = buildProtectedUrl(buildArtifactKey(manifestKey));
  const manifest = await downloadJson<OrgProfileManifest>(manifestKey);
  const profileEntries = Array.isArray(manifest.profiles) ? manifest.profiles : [];

  const loadedProfiles = await Promise.all(
    profileEntries
      .filter((entry): entry is OrgProfileManifestEntry => Boolean(entry?.path))
      .map(async (entry) => {
        const resolvedUrl = resolveRelativePath(manifestUrl, entry.path!);
        const profileKey = keyFromProtectedUrl(resolvedUrl);
        const profile = await downloadJson<RawOrgProfile>(profileKey);
        return normalizeOrgProfile(profile, {
          manifestId: entry.id ?? null,
          profileUrl: buildProtectedUrl(profileKey),
          dataRoot: "https://protected.local/",
        });
      }),
  );

  if (loadedProfiles.length === 0) {
    throw new ProtectedDataAccessError(
      "permanent-unavailable",
      "No org profiles were available from protected storage.",
    );
  }

  return loadedProfiles;
}

export async function loadSnapshotFile(profile?: OrgProfile | null): Promise<Snapshot> {
  const snapshotUrl =
    profile?.data.snapshotUrl ?? buildProtectedUrl(buildArtifactKey("profiles/default/snapshot.json"));
  return downloadJson<Snapshot>(keyFromProtectedUrl(snapshotUrl));
}

export async function loadPlanCatalog(profile?: OrgProfile | null): Promise<PlanCatalogResult> {
  const manifestUrl =
    profile?.data.planManifestUrl ??
    buildProtectedUrl(buildArtifactKey("profiles/default/plans/index.json"));
  const manifest = await downloadJson<PlanManifest>(keyFromProtectedUrl(manifestUrl));
  const planEntries = Array.isArray(manifest.plans) ? manifest.plans : [];
  const diagnostics: PlanCatalogDiagnostic[] = [];
  const loadedPlans: PlanPreset[] = [];

  for (const entry of planEntries.filter(
    (candidate): candidate is PlanManifestEntry => Boolean(candidate?.path),
  )) {
    const resolvedUrl = resolveRelativePath(manifestUrl, entry.path);
    const planKey = keyFromProtectedUrl(resolvedUrl);
    try {
      const plan = await downloadJson<RawPlanPreset>(planKey);
      loadedPlans.push(
        normalizePlanPreset(
          {
            ...plan,
            id:
              plan.schema_version === 2
                ? plan.id
                : entry.id || plan.id || derivePlanId(plan.name),
          },
          { manifestId: entry.id ?? null, path: planKey },
        ),
      );
    } catch (error) {
      const normalized = normalizePlanError(error);
      diagnostics.push({
        scope: "entry",
        kind: normalized.kind,
        message: normalized.message,
        entryId: entry.id ?? null,
        path: planKey,
      });
    }
  }

  return {
    plans: loadedPlans,
    diagnostics,
    status: "ok",
  };
}
