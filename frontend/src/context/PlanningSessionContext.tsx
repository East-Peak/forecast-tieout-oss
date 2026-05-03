import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type { OrgProfile } from "../lib/orgProfiles";
import type { Snapshot } from "../types/snapshot";
import type { PlanPreset } from "../lib/plans";
import type { PlanCatalogDiagnostic } from "../lib/dataCatalog";

interface SnapshotMeta {
  as_of: string;
  generated_at: string;
  git_sha?: string;
}

export interface PlanningSessionContextValue {
  snapshot: Snapshot;
  orgProfiles: OrgProfile[];
  selectedOrgProfile: OrgProfile | null;
  selectOrgProfile: (id: string) => void;
  plans: PlanPreset[];
  selectedPlan: PlanPreset | null;
  requestedPlanId: string | null;
  activeRenderedPlanId: string | null;
  planSelectionNotice: {
    kind:
      | "catalog_unavailable"
      | "catalog_invalid"
      | "invalid_selection"
      | "transient_fetch_failure"
      | "catalog_health"
      | "no_valid_plan";
    message: string;
  } | null;
  planCatalogDiagnostics: PlanCatalogDiagnostic[];
  selectPlan: (id: string) => void;
  healthStatus: string;
  snapshotMeta: SnapshotMeta;
}

const PlanningSessionContext = createContext<PlanningSessionContextValue | null>(null);

interface PlanningSessionProviderProps {
  value: PlanningSessionContextValue;
  children: ReactNode;
}

export function PlanningSessionProvider({
  value,
  children,
}: PlanningSessionProviderProps) {
  return (
    <PlanningSessionContext.Provider value={value}>
      {children}
    </PlanningSessionContext.Provider>
  );
}

export function usePlanningSessionContext(): PlanningSessionContextValue {
  const value = useContext(PlanningSessionContext);
  if (!value) {
    throw new Error(
      "usePlanningSessionContext must be used within PlanningSessionProvider",
    );
  }
  return value;
}
