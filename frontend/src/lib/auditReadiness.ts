import type { MetricItem } from "../components/workbook";
import type { Snapshot } from "../types/snapshot";
import type { OrgProfile } from "./orgProfiles";
import {
  buildPlanTimingSemantics,
  type PlanPreset,
  type PlanTimingSemantics,
} from "./plans";
import {
  buildActualMonthLockRows,
  buildAcceptedScopeExclusions,
  buildCriticalSignals,
  buildFallbackExceptions,
  buildInactiveFallbackDebt,
  buildQuarterTieoutRows,
  getAuditHealthRows,
  getAuditOverallStatus,
  statusLabel,
} from "./audit";
import { formatMoney } from "./format";
import { buildConnectorPolicyNotes } from "./orgProfiles";

function isObservedSource(source: string): boolean {
  const normalized = source.trim().toLowerCase();
  return !normalized.includes("config") && !normalized.includes("static") && !normalized.includes("plan");
}

export interface AuditReadinessViewModel {
  orgProfileName: string;
  connectorPolicyNotes: string[];
  overallStatus: string;
  healthRows: ReturnType<typeof getAuditHealthRows>;
  criticalSignals: ReturnType<typeof buildCriticalSignals>;
  fallbackExceptions: ReturnType<typeof buildFallbackExceptions>;
  acceptedScopeExclusions: ReturnType<typeof buildAcceptedScopeExclusions>;
  inactiveFallbackDebt: ReturnType<typeof buildInactiveFallbackDebt>;
  quarterTieoutRows: ReturnType<typeof buildQuarterTieoutRows>;
  monthLockRows: ReturnType<typeof buildActualMonthLockRows>;
  planTimingSemantics: PlanTimingSemantics;
  topMetrics: MetricItem[];
}

export function buildAuditReadinessViewModel(
  snapshot: Snapshot,
  orgProfile: OrgProfile | null = null,
  plan: PlanPreset | null = null,
): AuditReadinessViewModel {
  const overallStatus = getAuditOverallStatus(snapshot);
  const healthRows = getAuditHealthRows(snapshot);
  const criticalSignals = buildCriticalSignals(snapshot);
  const fallbackExceptions = buildFallbackExceptions(snapshot);
  const acceptedScopeExclusions = buildAcceptedScopeExclusions(snapshot);
  const inactiveFallbackDebt = buildInactiveFallbackDebt(snapshot);
  const quarterTieoutRows = buildQuarterTieoutRows(snapshot);
  const monthLockRows = buildActualMonthLockRows(snapshot);
  // Pick the first quarter row (the in-progress / locked quarter, since
  // tieout rows are ordered chronologically). Profile-agnostic.
  const q1Row = quarterTieoutRows[0] ?? null;
  const liveCriticalCount = criticalSignals.filter((row) => isObservedSource(row.source)).length;
  const tiedQuarterCount = quarterTieoutRows.filter((row) => row.status === "green").length;
  const lockedMonthCount = monthLockRows.filter((row) => row.status === "green").length;
  const orgProfileName = orgProfile?.name ?? "Default org profile";
  const planTimingSemantics = buildPlanTimingSemantics(
    snapshot.scenario_building_blocks.months,
    plan,
  );

  return {
    orgProfileName,
    connectorPolicyNotes: orgProfile ? buildConnectorPolicyNotes(orgProfile) : [],
    overallStatus,
    healthRows,
    criticalSignals,
    fallbackExceptions,
    acceptedScopeExclusions,
    inactiveFallbackDebt,
    quarterTieoutRows,
    monthLockRows,
    planTimingSemantics,
    topMetrics: [
      {
        label: "Snapshot Status",
        value: statusLabel(overallStatus),
        delta: `As of ${snapshot.as_of}`,
        deltaType: overallStatus === "green" ? "increase" : "decrease",
      },
      {
        label: q1Row ? `${q1Row.quarter} Sales-Led Forecast` : "Sales-Led Forecast",
        value: q1Row ? formatMoney(q1Row.bookings) : "—",
        delta: `${tiedQuarterCount}/${quarterTieoutRows.length || 0} quarters tied`,
        deltaType:
          quarterTieoutRows.length > 0 && tiedQuarterCount === quarterTieoutRows.length
            ? "increase"
            : "decrease",
      },
      {
        label: "Actual Months Locked",
        value: `${lockedMonthCount}/${monthLockRows.length || 0}`,
        delta:
          monthLockRows.length > 0 && lockedMonthCount === monthLockRows.length
            ? "All actual months locked"
            : "Actual lock check failed",
        deltaType:
          monthLockRows.length > 0 && lockedMonthCount === monthLockRows.length
            ? "increase"
            : "decrease",
      },
      {
        label: "Live Critical Signals",
        value: `${liveCriticalCount}/${criticalSignals.length || 0}`,
        delta:
          fallbackExceptions.length === 0
            ? "No fallback exceptions"
            : `${fallbackExceptions.length} explicit exceptions`,
        deltaType: fallbackExceptions.length === 0 ? "increase" : "decrease",
      },
    ],
  };
}
