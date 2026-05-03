export interface OrgProfileManifestEntry {
  id?: string;
  path?: string;
}

export interface RawOrgProfileData {
  snapshot?: string;
  plan_manifest?: string;
}

export interface RawOrgProfileConnectors {
  crm?: string;
  warehouse?: string;
  fallback_order?: Record<string, string[]>;
}

export interface RawOrgProfileTrust {
  finance_motion?: string;
  timing_semantics?: {
    wins?: string;
    losses?: string;
    pipeline_actuals?: string;
  };
}

export interface RawOrgProfile {
  id?: string;
  slug?: string;
  name?: string;
  description?: string;
  version?: number;
  data?: RawOrgProfileData;
  connectors?: RawOrgProfileConnectors;
  metadata?: Record<string, unknown>;
  trust?: RawOrgProfileTrust;
}

export interface OrgProfile {
  id: string;
  slug: string;
  name: string;
  description: string;
  version: number;
  data: {
    snapshotUrl: string;
    planManifestUrl: string;
  };
  connectors: {
    crm: string;
    warehouse: string;
    fallbackOrder: Record<string, string[]>;
  };
  metadata: Record<string, unknown>;
  trust: {
    financeMotion: string;
    timingSemantics: {
      wins: string;
      losses: string;
      pipelineActuals: string;
    };
  };
}

interface NormalizeOptions {
  manifestId?: string | null;
  profileUrl?: string | null;
  dataRoot: string;
}

const DEFAULT_CONNECTOR_FALLBACKS: Record<string, string[]> = {
  bookings: ["warehouse", "crm", "config"],
  losses: ["warehouse", "crm", "config"],
  roster: ["warehouse + roster.yaml", "roster.yaml", "config"],
};

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function resolveRelativeUrl(baseUrl: string, relativePath: string): string {
  return new URL(relativePath, baseUrl).toString();
}

export function createFallbackOrgProfile(dataRoot: string): OrgProfile {
  return {
    id: "default",
    slug: "default",
    name: "Default Org",
    description: "Default Forecast Tieout org profile.",
    version: 1,
    data: {
      snapshotUrl: `${dataRoot}/profiles/default/snapshot.json`,
      planManifestUrl: `${dataRoot}/profiles/default/plans/index.json`,
    },
    connectors: {
      crm: "CSV",
      warehouse: "CSV",
      fallbackOrder: DEFAULT_CONNECTOR_FALLBACKS,
    },
    metadata: {
      timezone: "America/Los_Angeles",
      fiscal_year: "",
      quarters: [],
    },
    trust: {
      financeMotion: "Sales-led",
      timingSemantics: {
        wins: "CloseDate",
        losses: "Closed At",
        pipelineActuals: "First S2 entry",
      },
    },
  };
}

export function normalizeOrgProfile(
  raw: RawOrgProfile,
  { manifestId, profileUrl, dataRoot }: NormalizeOptions,
): OrgProfile {
  const id =
    String(raw.id || manifestId || raw.slug || raw.name || "default").trim() ||
    "default";
  const name = String(raw.name || id).trim() || id;
  const slug = String(raw.slug || slugify(name) || id).trim() || id;
  const baseUrl = profileUrl || `${dataRoot}/profiles/${id}.json`;
  const fallback = createFallbackOrgProfile(dataRoot);
  const defaultSnapshotPath = `./${slug}/snapshot.json`;
  const defaultPlanManifestPath = `./${slug}/plans/index.json`;
  const fallbackOrder = raw.connectors?.fallback_order ?? {};

  return {
    id,
    slug,
    name,
    description: String(raw.description || fallback.description),
    version: Number(raw.version || fallback.version),
    data: {
      snapshotUrl: resolveRelativeUrl(
        baseUrl,
        raw.data?.snapshot || defaultSnapshotPath,
      ),
      planManifestUrl: resolveRelativeUrl(
        baseUrl,
        raw.data?.plan_manifest || defaultPlanManifestPath,
      ),
    },
    connectors: {
      crm: String(raw.connectors?.crm || fallback.connectors.crm),
      warehouse: String(raw.connectors?.warehouse || fallback.connectors.warehouse),
      fallbackOrder: {
        ...DEFAULT_CONNECTOR_FALLBACKS,
        ...fallbackOrder,
      },
    },
    metadata: {
      ...fallback.metadata,
      ...(raw.metadata || {}),
    },
    trust: {
      financeMotion: String(raw.trust?.finance_motion || fallback.trust.financeMotion),
      timingSemantics: {
        wins: String(
          raw.trust?.timing_semantics?.wins || fallback.trust.timingSemantics.wins,
        ),
        losses: String(
          raw.trust?.timing_semantics?.losses || fallback.trust.timingSemantics.losses,
        ),
        pipelineActuals: String(
          raw.trust?.timing_semantics?.pipeline_actuals ||
            fallback.trust.timingSemantics.pipelineActuals,
        ),
      },
    },
  };
}

function humanizeFallbackStep(step: string): string {
  if (step === "config") return "Config fallback";
  if (step === "warehouse") return "Warehouse observed";
  if (step === "crm") return "CRM observed";
  return step;
}

export function formatFallbackOrder(profile: OrgProfile, key: string): string {
  const values = profile.connectors.fallbackOrder[key] || [];
  return values.map(humanizeFallbackStep).join(" -> ");
}

export function buildConnectorPolicyNotes(profile: OrgProfile): string[] {
  return [
    `${profile.name} source priority for bookings: ${formatFallbackOrder(profile, "bookings")}.`,
    `${profile.name} source priority for losses: ${formatFallbackOrder(profile, "losses")}.`,
    `${profile.name} roster/capacity source priority: ${formatFallbackOrder(profile, "roster")}.`,
  ];
}
