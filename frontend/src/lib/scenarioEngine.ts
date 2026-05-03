import {
  computeScenario as computeLocalScenario,
} from "../engine/scenario";
import type {
  ScenarioOverrides,
  ScenarioQuarterKey,
  ScenarioQuarterOverride,
  ScenarioResult,
} from "../engine/scenario";
import type { Snapshot } from "../types/snapshot";

export interface ScenarioServiceQuarterOverridePayload {
  addAes: number;
  aeMonthTargets: [number, number, number];
  mqlChangePct: number;
  mqlToS0: number;
  s0ToS1: number;
  s1ToS2: number;
  avgDealSize: number;
}

export interface ScenarioServiceRequestPayload {
  version: 1;
  profileId?: string;
  quarters: Record<ScenarioQuarterKey, ScenarioServiceQuarterOverridePayload>;
}

export interface ScenarioServiceResultPayload {
  months: string[];
  monthly_inventory_wins: number[];
  monthly_future_wins: number[];
  monthly_pipeline_created: number[];
  monthly_ae_creation: number[];
  monthly_mql_creation: number[];
  monthly_expected: number[];
  monthly_capped: number[];
  monthly_capacity: number[];
  monthly_ae_count: number[];
  monthly_overflow: number[];
  cumulative_expected: number[];
  cumulative_capped: number[];
  fy_expected: number;
  fy_capped: number;
}

export interface ScenarioServiceResponsePayload {
  profile_id?: string;
  snapshot_path?: string;
  overrides?: Partial<Record<ScenarioQuarterKey, ScenarioServiceQuarterOverridePayload>>;
  result: ScenarioServiceResultPayload;
}

export interface ScenarioComputation {
  engineId: string;
  engineLabel: string;
  request: ScenarioServiceRequestPayload;
  result: ScenarioResult;
}

export interface ScenarioEngineAdapter {
  id: string;
  label: string;
  buildRequest: (
    overrides: ScenarioOverrides,
    profileId?: string | null,
  ) => ScenarioServiceRequestPayload;
  compute: (
    snapshot: Snapshot,
    overrides: ScenarioOverrides,
    profileId?: string | null,
  ) => Promise<ScenarioComputation>;
  readResponse: (payload: ScenarioServiceResponsePayload) => ScenarioResult;
}

function cloneQuarterOverride(
  override: ScenarioQuarterOverride,
): ScenarioServiceQuarterOverridePayload {
  return {
    addAes: override.addAes,
    aeMonthTargets: [...override.aeMonthTargets] as [number, number, number],
    mqlChangePct: override.mqlChangePct,
    mqlToS0: override.mqlToS0,
    s0ToS1: override.s0ToS1,
    s1ToS2: override.s1ToS2,
    avgDealSize: override.avgDealSize,
  };
}

export function buildScenarioServiceRequest(
  overrides: ScenarioOverrides,
  profileId?: string | null,
): ScenarioServiceRequestPayload {
  return {
    version: 1,
    ...(profileId ? { profileId } : {}),
    // Iterate the overrides themselves — same source of truth as
    // snapshot.scenario_building_blocks.overridable_quarters via
    // buildDefaultScenarioOverrides.
    quarters: Object.fromEntries(
      Object.keys(overrides).map((quarter) => [
        quarter,
        cloneQuarterOverride(overrides[quarter]),
      ]),
    ) as Record<ScenarioQuarterKey, ScenarioServiceQuarterOverridePayload>,
  };
}

export function mapScenarioServiceResult(
  payload: ScenarioServiceResultPayload,
): ScenarioResult {
  return {
    monthly_inventory_wins: [...payload.monthly_inventory_wins],
    monthly_future_wins: [...payload.monthly_future_wins],
    monthly_pipeline_created: [...payload.monthly_pipeline_created],
    monthly_ae_creation: [...payload.monthly_ae_creation],
    monthly_mql_creation: [...payload.monthly_mql_creation],
    monthly_expected: [...payload.monthly_expected],
    monthly_capped: [...payload.monthly_capped],
    monthly_capacity: [...payload.monthly_capacity],
    monthly_ae_count: [...payload.monthly_ae_count],
    monthly_overflow: [...payload.monthly_overflow],
    cumulative_expected: [...payload.cumulative_expected],
    cumulative_capped: [...payload.cumulative_capped],
    fy_expected: payload.fy_expected,
    fy_capped: payload.fy_capped,
  };
}

const FRONTEND_LOCAL_SCENARIO_ENGINE_ID = "frontend-local";
const FRONTEND_LOCAL_SCENARIO_ENGINE_LABEL =
  "Frontend local adapter (backend-compatible contract)";
const BACKEND_SCENARIO_ENGINE_ID = "backend-snapshot-service";
const BACKEND_SCENARIO_ENGINE_LABEL = "Backend snapshot scenario service";

type ScenarioServiceAvailability = "unknown" | "available" | "unavailable";

let cachedScenarioServiceUrl: string | null | undefined;
let scenarioServiceAvailability: ScenarioServiceAvailability = "unknown";

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function resolveScenarioServiceUrl(): string | null {
  if (cachedScenarioServiceUrl !== undefined) return cachedScenarioServiceUrl;

  const configuredUrl = import.meta.env.VITE_SCENARIO_API_URL as string | undefined;
  if (configuredUrl && configuredUrl.trim().length > 0) {
    cachedScenarioServiceUrl = trimTrailingSlash(configuredUrl.trim());
    return cachedScenarioServiceUrl;
  }

  cachedScenarioServiceUrl = import.meta.env.DEV ? "/api/scenario" : null;
  return cachedScenarioServiceUrl;
}

function markScenarioServiceUnavailable() {
  scenarioServiceAvailability = "unavailable";
}

function markScenarioServiceAvailable() {
  scenarioServiceAvailability = "available";
}

export function resetScenarioServiceResolutionForTests() {
  cachedScenarioServiceUrl = undefined;
  scenarioServiceAvailability = "unknown";
}

async function tryComputeWithScenarioService(
  request: ScenarioServiceRequestPayload,
): Promise<ScenarioComputation> {
  const serviceUrl = resolveScenarioServiceUrl();
  if (!serviceUrl || scenarioServiceAvailability === "unavailable") {
    throw new Error("Scenario service not configured");
  }

  let response: Response;
  try {
    response = await fetch(serviceUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });
  } catch (error) {
    markScenarioServiceUnavailable();
    throw error;
  }

  if (!response.ok) {
    if (response.status === 404 || response.status >= 500) {
      markScenarioServiceUnavailable();
    }
    throw new Error(`Scenario service returned ${response.status}`);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    markScenarioServiceUnavailable();
    throw new Error("Scenario service returned a non-JSON response");
  }

  const payload = (await response.json()) as ScenarioServiceResponsePayload;
  markScenarioServiceAvailable();
  return {
    engineId: BACKEND_SCENARIO_ENGINE_ID,
    engineLabel: BACKEND_SCENARIO_ENGINE_LABEL,
    request,
    result: mapScenarioServiceResult(payload.result),
  };
}

function computeWithLocalAdapter(
  snapshot: Snapshot,
  overrides: ScenarioOverrides,
  profileId?: string | null,
): ScenarioComputation {
  return {
    engineId: FRONTEND_LOCAL_SCENARIO_ENGINE_ID,
    engineLabel: FRONTEND_LOCAL_SCENARIO_ENGINE_LABEL,
    request: buildScenarioServiceRequest(overrides, profileId),
    result: computeLocalScenario(snapshot, overrides),
  };
}

export const frontendLocalScenarioEngine: ScenarioEngineAdapter = {
  id: FRONTEND_LOCAL_SCENARIO_ENGINE_ID,
  label: FRONTEND_LOCAL_SCENARIO_ENGINE_LABEL,
  buildRequest: buildScenarioServiceRequest,
  async compute(snapshot, overrides, profileId) {
    return computeWithLocalAdapter(snapshot, overrides, profileId);
  },
  readResponse(payload) {
    return mapScenarioServiceResult(payload.result);
  },
};

export const backendScenarioServiceEngine: ScenarioEngineAdapter = {
  id: BACKEND_SCENARIO_ENGINE_ID,
  label: BACKEND_SCENARIO_ENGINE_LABEL,
  buildRequest: buildScenarioServiceRequest,
  async compute(_snapshot, overrides, profileId) {
    return tryComputeWithScenarioService(buildScenarioServiceRequest(overrides, profileId));
  },
  readResponse(payload) {
    return mapScenarioServiceResult(payload.result);
  },
};

export const defaultScenarioEngine: ScenarioEngineAdapter = {
  id: "scenario-engine:auto",
  label: "Auto scenario engine",
  buildRequest: buildScenarioServiceRequest,
  async compute(snapshot, overrides, profileId) {
    try {
      return await backendScenarioServiceEngine.compute(snapshot, overrides, profileId);
    } catch (error) {
      if (resolveScenarioServiceUrl()) {
        console.warn(
          "Scenario service unavailable; falling back to frontend-local adapter.",
          error,
        );
      }
      return computeWithLocalAdapter(snapshot, overrides, profileId);
    }
  },
  readResponse(payload) {
    return mapScenarioServiceResult(payload.result);
  },
};
