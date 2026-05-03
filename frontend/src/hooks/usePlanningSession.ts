import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useSnapshot } from "./useSnapshot";
import {
  PLAN_QUERY_PARAM,
  PROFILE_QUERY_PARAM,
  PROFILE_STORAGE_KEY,
  getPlanStorageKey,
} from "../lib/scenarioSession";

interface PlanningSessionState {
  snapshot: ReturnType<typeof useSnapshot>["snapshot"];
  orgProfiles: ReturnType<typeof useSnapshot>["orgProfiles"];
  selectedOrgProfile: ReturnType<typeof useSnapshot>["selectedOrgProfile"];
  plans: ReturnType<typeof useSnapshot>["plans"];
  selectedPlan: ReturnType<typeof useSnapshot>["selectedPlan"];
  requestedPlanId: ReturnType<typeof useSnapshot>["requestedPlanId"];
  activeRenderedPlanId: ReturnType<typeof useSnapshot>["activeRenderedPlanId"];
  planSelectionNotice: ReturnType<typeof useSnapshot>["planSelectionNotice"];
  planCatalogDiagnostics: ReturnType<typeof useSnapshot>["planCatalogDiagnostics"];
  loading: boolean;
  error: string | null;
  selectOrgProfile: (id: string) => void;
  selectPlan: (id: string) => void;
}

export function usePlanningSession(): PlanningSessionState {
  const [searchParams, setSearchParams] = useSearchParams();
  const preferredProfileId = searchParams.get(PROFILE_QUERY_PARAM);
  const preferredPlanId = searchParams.get(PLAN_QUERY_PARAM);
  const {
    snapshot,
    orgProfiles,
    selectedOrgProfile,
    plans,
    selectedPlan,
    requestedPlanId,
    activeRenderedPlanId,
    planSelectionNotice,
    planCatalogDiagnostics,
    canPersistActivePlanSelection,
    loading,
    error,
    selectOrgProfile,
    selectPlan,
  } = useSnapshot(preferredPlanId, preferredProfileId);

  // Persist org profile selection to localStorage and URL
  useEffect(() => {
    if (!selectedOrgProfile || typeof window === "undefined") return;
    window.localStorage.setItem(PROFILE_STORAGE_KEY, selectedOrgProfile.id);
    if (preferredProfileId === selectedOrgProfile.id) return;

    const next = new URLSearchParams(searchParams);
    next.set(PROFILE_QUERY_PARAM, selectedOrgProfile.id);
    setSearchParams(next, { replace: true });
  }, [preferredProfileId, searchParams, selectedOrgProfile, setSearchParams]);

  // Persist plan selection to localStorage and URL
  useEffect(() => {
    if (typeof window === "undefined" || loading || !canPersistActivePlanSelection) return;

    const storageKey = getPlanStorageKey(selectedOrgProfile?.id);
    const next = new URLSearchParams(searchParams);
    const allowResolvedFallbackRewrite =
      planSelectionNotice?.kind === "invalid_selection" ||
      planSelectionNotice?.kind === "no_valid_plan";
    const effectiveRequestedPlanId = requestedPlanId ?? preferredPlanId;
    const hasPendingRequestedSelection =
      effectiveRequestedPlanId !== null &&
      effectiveRequestedPlanId !== activeRenderedPlanId &&
      !allowResolvedFallbackRewrite;

    if (hasPendingRequestedSelection) {
      return;
    }

    if (activeRenderedPlanId) {
      window.localStorage.setItem(storageKey, activeRenderedPlanId);
      if (preferredPlanId === activeRenderedPlanId) return;
      next.set(PLAN_QUERY_PARAM, activeRenderedPlanId);
      setSearchParams(next, { replace: true });
      return;
    }

    window.localStorage.removeItem(storageKey);
    if (!preferredPlanId) return;
    next.delete(PLAN_QUERY_PARAM);
    setSearchParams(next, { replace: true });
  }, [
    activeRenderedPlanId,
    canPersistActivePlanSelection,
    loading,
    planSelectionNotice?.kind,
    preferredPlanId,
    requestedPlanId,
    searchParams,
    selectedOrgProfile?.id,
    setSearchParams,
  ]);

  return {
    snapshot,
    orgProfiles,
    selectedOrgProfile,
    plans,
    selectedPlan,
    requestedPlanId,
    activeRenderedPlanId,
    planSelectionNotice,
    planCatalogDiagnostics,
    loading,
    error,
    selectOrgProfile,
    selectPlan,
  };
}
