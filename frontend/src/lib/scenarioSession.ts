import {
  cloneScenarioOverrides,
} from "../engine/scenario";
import type {
  ScenarioOverrides,
  ScenarioQuarterKey,
  ScenarioQuarterOverride,
} from "../engine/scenario";

export const PLAN_STORAGE_KEY = "forecast-tieout.plan.v1";
export const SCENARIO_STORAGE_KEY = "forecast-tieout.scenario.v1";
export const PROFILE_STORAGE_KEY = "forecast-tieout.profile.v1";
export const PLAN_QUERY_PARAM = "plan";
export const SCENARIO_QUERY_PARAM = "scenario";
export const PROFILE_QUERY_PARAM = "profile";

export function getPlanStorageKey(profileId?: string | null): string {
  return profileId ? `${PLAN_STORAGE_KEY}.${profileId}` : PLAN_STORAGE_KEY;
}

export function getScenarioStorageKey(profileId?: string | null): string {
  return profileId ? `${SCENARIO_STORAGE_KEY}.${profileId}` : SCENARIO_STORAGE_KEY;
}

type QuarterDiff = Partial<ScenarioQuarterOverride> & {
  aeMonthTargets?: [number, number, number];
};

interface ScenarioSessionPayload {
  version: 1;
  quarters: Partial<Record<ScenarioQuarterKey, QuarterDiff>>;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function buildQuarterDiff(
  current: ScenarioQuarterOverride,
  baseline: ScenarioQuarterOverride,
): QuarterDiff | null {
  const diff: QuarterDiff = {};

  if (Math.abs(current.addAes - baseline.addAes) > 1e-9) diff.addAes = current.addAes;
  if (Math.abs(current.mqlChangePct - baseline.mqlChangePct) > 1e-9) {
    diff.mqlChangePct = current.mqlChangePct;
  }
  if (Math.abs(current.mqlToS0 - baseline.mqlToS0) > 1e-9) diff.mqlToS0 = current.mqlToS0;
  if (Math.abs(current.s0ToS1 - baseline.s0ToS1) > 1e-9) diff.s0ToS1 = current.s0ToS1;
  if (Math.abs(current.s1ToS2 - baseline.s1ToS2) > 1e-9) diff.s1ToS2 = current.s1ToS2;
  if (Math.abs(current.avgDealSize - baseline.avgDealSize) > 1e-9) {
    diff.avgDealSize = current.avgDealSize;
  }

  if (
    current.aeMonthTargets.some(
      (value, index) => Math.abs(value - baseline.aeMonthTargets[index]) > 1e-9,
    )
  ) {
    diff.aeMonthTargets = [...current.aeMonthTargets] as [number, number, number];
  }

  return Object.keys(diff).length > 0 ? diff : null;
}

export function serializeScenarioOverrides(
  current: ScenarioOverrides,
  baseline: ScenarioOverrides,
): string | null {
  // Iterate over the baseline overrides — same source of truth as
  // snapshot.scenario_building_blocks.overridable_quarters.
  const quarters = Object.fromEntries(
    Object.keys(baseline).map((quarter) => [
      quarter,
      buildQuarterDiff(current[quarter], baseline[quarter]),
    ]).filter(([, value]) => value !== null),
  ) as Partial<Record<ScenarioQuarterKey, QuarterDiff>>;

  if (Object.keys(quarters).length === 0) return null;

  return JSON.stringify({
    version: 1,
    quarters,
  } satisfies ScenarioSessionPayload);
}

function parsePayload(payload: string): ScenarioSessionPayload | null {
  try {
    return JSON.parse(payload) as ScenarioSessionPayload;
  } catch {
    return null;
  }
}

export function deserializeScenarioOverrides(
  encoded: string,
  baseline: ScenarioOverrides,
): ScenarioOverrides {
  const next = cloneScenarioOverrides(baseline);

  try {
    const parsed = parsePayload(encoded) ?? parsePayload(decodeURIComponent(encoded));
    if (!parsed || parsed.version !== 1 || !parsed.quarters || typeof parsed.quarters !== "object") {
      return next;
    }

    Object.keys(baseline).forEach((quarter) => {
      const incoming = parsed.quarters[quarter];
      if (!incoming || typeof incoming !== "object") return;

      const target = next[quarter];

      if (isFiniteNumber(incoming.addAes)) target.addAes = incoming.addAes;
      if (isFiniteNumber(incoming.mqlChangePct)) target.mqlChangePct = incoming.mqlChangePct;
      if (isFiniteNumber(incoming.mqlToS0)) target.mqlToS0 = incoming.mqlToS0;
      if (isFiniteNumber(incoming.s0ToS1)) target.s0ToS1 = incoming.s0ToS1;
      if (isFiniteNumber(incoming.s1ToS2)) target.s1ToS2 = incoming.s1ToS2;
      if (isFiniteNumber(incoming.avgDealSize)) target.avgDealSize = incoming.avgDealSize;

      if (
        Array.isArray(incoming.aeMonthTargets) &&
        incoming.aeMonthTargets.length === 3 &&
        incoming.aeMonthTargets.every(isFiniteNumber)
      ) {
        target.aeMonthTargets = [...incoming.aeMonthTargets] as [number, number, number];
      }
    });
  } catch {
    return next;
  }

  return next;
}
