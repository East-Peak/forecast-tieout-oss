import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "../types/snapshot";
import {
  loadOrgProfileCatalog,
  loadPlanCatalog,
  loadSnapshotFile,
} from "../lib/dataCatalog";
import {
  loadOrgProfileCatalog as loadProtectedOrgProfileCatalog,
  loadPlanCatalog as loadProtectedPlanCatalog,
  loadSnapshotFile as loadProtectedSnapshotFile,
} from "../lib/protectedDataCatalog";
import type { OrgProfile } from "../lib/orgProfiles";
import type { PlanPreset } from "../lib/plans";
import { isProtectedDataModeEnabled } from "../lib/runtimeConfig";
import {
  PROFILE_STORAGE_KEY,
  getPlanStorageKey,
} from "../lib/scenarioSession";
import type { PlanCatalogDiagnostic, PlanCatalogResult } from "../lib/dataCatalog";

interface PlanSelectionNotice {
  kind:
    | "catalog_unavailable"
    | "catalog_invalid"
    | "invalid_selection"
    | "transient_fetch_failure"
    | "catalog_health"
    | "no_valid_plan";
  message: string;
}

interface SnapshotState {
  snapshot: Snapshot | null;
  orgProfiles: OrgProfile[];
  selectedOrgProfile: OrgProfile | null;
  plans: PlanPreset[];
  selectedPlan: PlanPreset | null;
  requestedPlanId: string | null;
  activeRenderedPlanId: string | null;
  planCatalogDiagnostics: PlanCatalogDiagnostic[];
  planCatalogStatus: PlanCatalogResult["status"];
  planSelectionNotice: PlanSelectionNotice | null;
  canPersistActivePlanSelection: boolean;
  loading: boolean;
  error: string | null;
  selectOrgProfile: (id: string) => void;
  selectPlan: (id: string) => void;
}

function readStoredPlanId(profileId?: string | null): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(getPlanStorageKey(profileId));
}

function readStoredProfileId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PROFILE_STORAGE_KEY);
}

function resolveSelectedOrgProfile(
  profiles: OrgProfile[],
  preferredId: string | null | undefined,
): OrgProfile | null {
  if (profiles.length === 0) return null;
  const desiredKey = preferredId || readStoredProfileId();
  return (
    profiles.find((profile) => profile.id === desiredKey || profile.slug === desiredKey) ??
    profiles[0] ??
    null
  );
}

function resolveSelectedPlan(
  plans: PlanPreset[],
  preferredId: string | null | undefined,
): PlanPreset | null {
  if (plans.length === 0) return null;
  const desiredKey = preferredId;
  return (
    plans.find((plan) => plan.id === desiredKey) ??
    plans.find((plan) => plan.schemaVersion === 1 && plan.name === desiredKey) ??
    null
  );
}

function resolveRequestedPlanId(
  preferredId: string | null | undefined,
  profileId?: string | null,
): string | null {
  return preferredId || readStoredPlanId(profileId);
}

function matchingEntryDiagnostic(
  diagnostics: PlanCatalogDiagnostic[],
  requestedPlanId: string | null,
): PlanCatalogDiagnostic | null {
  if (!requestedPlanId) return null;
  return (
    diagnostics.find((diagnostic) => diagnostic.entryId === requestedPlanId) ??
    null
  );
}

function resolvePlanSelectionState(
  plans: PlanPreset[],
  requestedPlanId: string | null,
  diagnostics: PlanCatalogDiagnostic[],
  status: PlanCatalogResult["status"],
  lastValidatedPlan: PlanPreset | null,
): {
  selectedPlan: PlanPreset | null;
  notice: PlanSelectionNotice | null;
  canPersist: boolean;
} {
  if (status === "transient-fetch-failure" || status === "permanent-unavailable") {
    return {
      selectedPlan: lastValidatedPlan,
      notice: {
        kind: "catalog_unavailable",
        message:
          "Plan catalog is temporarily unavailable. The last validated selected plan remains active until the catalog can be retried.",
      },
      canPersist: false,
    };
  }

  if (status === "schema-invalid") {
    return {
      selectedPlan: lastValidatedPlan,
      notice: {
        kind: "catalog_invalid",
        message:
          "Plan catalog metadata is invalid. The app keeps the last validated selected plan rather than silently choosing a new one.",
      },
      canPersist: false,
    };
  }

  if (plans.length === 0) {
    return {
      selectedPlan: null,
      notice: {
        kind: "no_valid_plan",
        message: "No valid plans remain after catalog validation.",
      },
      canPersist: true,
    };
  }

  if (!requestedPlanId) {
    return {
      selectedPlan: plans[0] ?? null,
      notice:
        diagnostics.length > 0
          ? {
              kind: "catalog_health",
              message:
                "One or more plan assets were excluded during validation. The selector shows the remaining valid catalog only.",
            }
          : null,
      canPersist: true,
    };
  }

  const requestedPlan = resolveSelectedPlan(plans, requestedPlanId);
  if (requestedPlan) {
    return {
      selectedPlan: requestedPlan,
      notice:
        diagnostics.length > 0
          ? {
              kind: "catalog_health",
              message:
                "Some plan assets were excluded during validation. The selected plan is valid and active.",
            }
          : null,
      canPersist: true,
    };
  }

  const requestDiagnostic = matchingEntryDiagnostic(diagnostics, requestedPlanId);
  if (requestDiagnostic?.kind === "transient-fetch-failure") {
    return {
      selectedPlan: lastValidatedPlan,
      notice: {
        kind: "transient_fetch_failure",
        message:
          "The requested plan could not be fetched yet. The app keeps the last validated plan active and preserves the requested id for retry.",
      },
      canPersist: false,
    };
  }

  return {
    selectedPlan: plans[0] ?? null,
    notice: {
      kind: "invalid_selection",
      message:
        "The requested plan is unavailable or invalid. The app selected the first valid plan explicitly instead of silently reusing stale selection state.",
    },
    canPersist: true,
  };
}

export function useSnapshot(
  preferredPlanId?: string | null,
  preferredProfileId?: string | null,
): SnapshotState {
  const loadProfiles = isProtectedDataModeEnabled()
    ? loadProtectedOrgProfileCatalog
    : loadOrgProfileCatalog;
  const loadSnapshot = isProtectedDataModeEnabled()
    ? loadProtectedSnapshotFile
    : loadSnapshotFile;
  const loadPlans = isProtectedDataModeEnabled()
    ? loadProtectedPlanCatalog
    : loadPlanCatalog;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [orgProfiles, setOrgProfiles] = useState<OrgProfile[]>([]);
  const [selectedOrgProfile, setSelectedOrgProfile] = useState<OrgProfile | null>(null);
  const [plans, setPlans] = useState<PlanPreset[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<PlanPreset | null>(null);
  const [requestedPlanId, setRequestedPlanId] = useState<string | null>(null);
  const [planCatalogDiagnostics, setPlanCatalogDiagnostics] = useState<PlanCatalogDiagnostic[]>([]);
  const [planCatalogStatus, setPlanCatalogStatus] =
    useState<PlanCatalogResult["status"]>("ok");
  const [planSelectionNotice, setPlanSelectionNotice] = useState<PlanSelectionNotice | null>(null);
  const [canPersistActivePlanSelection, setCanPersistActivePlanSelection] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastValidatedPlanRef = useRef<PlanPreset | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const profileData = await loadProfiles();
        const activeProfile = resolveSelectedOrgProfile(profileData, preferredProfileId);
        const nextRequestedPlanId = resolveRequestedPlanId(preferredPlanId, activeProfile?.id);
        const [snapData, planData] = await Promise.all([
          loadSnapshot(activeProfile),
          loadPlans(activeProfile),
        ]);
        setOrgProfiles(profileData);
        setSelectedOrgProfile(activeProfile);
        setSnapshot(snapData);
        setPlans(planData.plans);
        setRequestedPlanId(nextRequestedPlanId);
        setPlanCatalogDiagnostics(planData.diagnostics);
        setPlanCatalogStatus(planData.status);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [loadPlans, loadProfiles, loadSnapshot, preferredPlanId, preferredProfileId]);

  useEffect(() => {
    if (orgProfiles.length === 0) return;
    setSelectedOrgProfile((current) => {
      const next = resolveSelectedOrgProfile(orgProfiles, preferredProfileId);
      return current?.id === next?.id ? current : next;
    });
  }, [orgProfiles, preferredProfileId]);

  useEffect(() => {
    setRequestedPlanId(resolveRequestedPlanId(preferredPlanId, selectedOrgProfile?.id));
  }, [preferredPlanId, selectedOrgProfile?.id]);

  useEffect(() => {
    const resolved = resolvePlanSelectionState(
      plans,
      requestedPlanId,
      planCatalogDiagnostics,
      planCatalogStatus,
      lastValidatedPlanRef.current,
    );
    setSelectedPlan(resolved.selectedPlan);
    setPlanSelectionNotice(resolved.notice);
    setCanPersistActivePlanSelection(resolved.canPersist);
  }, [plans, requestedPlanId, planCatalogDiagnostics, planCatalogStatus]);

  useEffect(() => {
    if (selectedPlan) {
      lastValidatedPlanRef.current = selectedPlan;
    }
  }, [selectedPlan]);

  function selectOrgProfile(id: string) {
    const profile = orgProfiles.find((p) => p.id === id) ?? null;
    setSelectedOrgProfile(profile);
  }

  function selectPlan(id: string) {
    const plan = plans.find((p) => p.id === id) ?? null;
    setRequestedPlanId(id);
    setSelectedPlan(plan);
    setPlanSelectionNotice(null);
    setCanPersistActivePlanSelection(true);
  }

  return {
    snapshot,
    orgProfiles,
    selectedOrgProfile,
    plans,
    selectedPlan,
    requestedPlanId,
    activeRenderedPlanId: selectedPlan?.id ?? null,
    planCatalogDiagnostics,
    planCatalogStatus,
    planSelectionNotice,
    canPersistActivePlanSelection,
    loading,
    error,
    selectOrgProfile,
    selectPlan,
  };
}
