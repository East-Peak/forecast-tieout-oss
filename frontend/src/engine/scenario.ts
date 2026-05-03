import type { Snapshot } from "../types/snapshot";

/**
 * Quarter label used as a key in `ScenarioOverrides`. Sourced from the
 * snapshot's `overridable_quarters` field at runtime, so the scenario engine
 * adapts to any fiscal calendar declared by the snapshot.
 */
export type ScenarioQuarterKey = string;

/**
 * Read the overridable-quarters list from the snapshot. Returns an empty array
 * if the snapshot does not carry the field — pages should render empty state
 * rather than substitute a default quarter list.
 */
export function getOverridableQuarters(snapshot: Snapshot): readonly string[] {
  const fromSnapshot = snapshot.scenario_building_blocks.overridable_quarters;
  return Array.isArray(fromSnapshot) ? fromSnapshot : [];
}

/**
 * Return the quarter label for a given month, sourced from the snapshot's
 * `quarter_by_month` parallel array. Returns null if the snapshot does not
 * carry the field or the month is not in the snapshot's months list.
 */
export function quarterForMonth(snapshot: Snapshot, month: string): string | null {
  const months = snapshot.scenario_building_blocks.months;
  const map = snapshot.scenario_building_blocks.quarter_by_month;
  if (Array.isArray(map) && map.length === months.length) {
    const idx = months.indexOf(month);
    if (idx !== -1) return map[idx];
  }
  return null;
}

/**
 * Return ALL quarters from the snapshot in first-occurrence (fiscal-calendar)
 * order. Unlike `getOverridableQuarters`, this includes locked quarters too.
 */
export function allQuartersFromSnapshot(snapshot: Snapshot): string[] {
  const qbm = snapshot.scenario_building_blocks?.quarter_by_month ?? [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const q of qbm) {
    if (q && !seen.has(q)) {
      seen.add(q);
      out.push(q);
    }
  }
  return out;
}

/**
 * Return the ISO month strings (e.g. "2026-02-01") that belong to `quarter`.
 * Returns [] if the quarter is not in the snapshot.
 */
export function monthsForQuarter(snapshot: Snapshot, quarter: string): string[] {
  const months = snapshot.scenario_building_blocks?.months ?? [];
  const qbm = snapshot.scenario_building_blocks?.quarter_by_month ?? [];
  const out: string[] = [];
  for (let i = 0; i < months.length; i++) {
    if (qbm[i] === quarter) out.push(months[i]);
  }
  return out;
}

/**
 * Return the last ISO month string for `quarter`, or null if unknown.
 */
export function lastMonthOfQuarter(snapshot: Snapshot, quarter: string): string | null {
  const ms = monthsForQuarter(snapshot, quarter);
  return ms.length ? ms[ms.length - 1] : null;
}

/**
 * Count calendar days from `asOf` (inclusive) to the last day of `quarter`.
 * Returns 0 if the quarter is unknown or `asOf` is past the quarter end.
 *
 * "Last day" is computed as the final day of the last month in the quarter
 * (e.g. last month "2026-04-01" → last day is 2026-04-30).
 */
export function daysUntilQuarterEnd(
  snapshot: Snapshot,
  asOf: string,
  quarter: string,
): number {
  const last = lastMonthOfQuarter(snapshot, quarter);
  if (!last) return 0;
  // Last day of `last` month = first day of next month minus 1 day.
  const d = new Date(last);
  const lastDay = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
  const ms = lastDay.getTime() - new Date(asOf).getTime();
  return Math.max(0, Math.round(ms / (1000 * 60 * 60 * 24)));
}

export interface ScenarioQuarterOverride {
  addAes: number;
  aeMonthTargets: [number, number, number];
  mqlChangePct: number;
  mqlToS0: number;
  s0ToS1: number;
  s1ToS2: number;
  avgDealSize: number;
}

export type ScenarioOverrides = Record<ScenarioQuarterKey, ScenarioQuarterOverride>;

export interface ScenarioResult {
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

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function toNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/**
 * Indexes of months belonging to the given quarter, sourced from the
 * snapshot's `quarter_by_month` parallel array. Returns empty if the snapshot
 * doesn't carry the field — there is no parser fallback; the engine is
 * snapshot-driven by design.
 */
export function getQuarterMonthIndexes(snapshot: Snapshot, quarter: string): number[] {
  const months = snapshot.scenario_building_blocks.months;
  const map = snapshot.scenario_building_blocks.quarter_by_month;
  if (!Array.isArray(map) || map.length !== months.length) return [];
  const result: number[] = [];
  for (let i = 0; i < map.length; i += 1) {
    if (map[i] === quarter) result.push(i);
  }
  return result;
}

function firstProjectedMonthIndex(snapshot: Snapshot): number {
  const flags = snapshot.scenario_building_blocks.monthly_is_actual;
  const index = flags.findIndex((value) => !value);
  return index === -1 ? flags.length : index;
}

function stackCohorts(monthlyCreation: number[], decayCurve: number[]): number[] {
  const result = new Array<number>(monthlyCreation.length + decayCurve.length - 1).fill(0);
  monthlyCreation.forEach((creation, monthIndex) => {
    decayCurve.forEach((rate, bucketIndex) => {
      result[monthIndex + bucketIndex] += creation * rate;
    });
  });
  return result;
}

function applyCapacityCeiling(expected: number[], capacity: number[]): number[] {
  const result = new Array<number>(expected.length).fill(0);
  let carry = 0;

  expected.forEach((value, index) => {
    const available = value + carry;
    const monthCapacity = capacity[index] ?? 0;
    if (available <= monthCapacity) {
      result[index] = available;
      carry = 0;
      return;
    }
    result[index] = monthCapacity;
    carry = available - monthCapacity;
  });

  return result;
}

function computeOverflow(expected: number[], capacity: number[]): number[] {
  const overflow = new Array<number>(expected.length).fill(0);
  let carry = 0;

  expected.forEach((value, index) => {
    const available = value + carry;
    const monthCapacity = capacity[index] ?? 0;
    if (available <= monthCapacity) {
      overflow[index] = 0;
      carry = 0;
      return;
    }
    overflow[index] = available - monthCapacity;
    carry = overflow[index];
  });

  return overflow;
}

function getObservedRampCurve(snapshot: Snapshot): Record<number, number> {
  const curveSource =
    (snapshot.roster.observed_ramp_curve as Record<string, unknown> | undefined)?.curve_by_segment_serialized ??
    (snapshot.roster.observed_ramp_curve as Record<string, unknown> | undefined)?.curve_by_segment ??
    {};
  const enterpriseCurve =
    (curveSource as Record<string, unknown>).enterprise as Record<string, unknown> | undefined;
  if (!enterpriseCurve) return {};

  const parsed: Record<number, number> = {};
  Object.entries(enterpriseCurve).forEach(([key, value]) => {
    if (key.startsWith("month_")) {
      const month = Number(key.slice(6));
      if (Number.isFinite(month)) parsed[month] = toNumber(value);
      return;
    }
    const month = Number(key);
    if (Number.isFinite(month)) parsed[month] = toNumber(value);
  });
  return parsed;
}

function getRampFactor(curve: Record<number, number>, monthsSinceStart: number): number {
  const key = monthsSinceStart + 1;
  if (key in curve) return toNumber(curve[key], 0);
  const maxKey = Math.max(0, ...Object.keys(curve).map((value) => Number(value)));
  if (maxKey === 0) return monthsSinceStart >= 5 ? 1 : 0;
  if (key > maxKey) return toNumber(curve[maxKey], 1);
  return 0;
}

function getFutureGenerationWinRates(snapshot: Snapshot, length: number): number[] {
  const provenance = (snapshot.model_output.bookings_bridge.provenance ?? {}) as Record<string, unknown>;
  const winRates = Array.isArray(provenance.future_generation_win_rates)
    ? provenance.future_generation_win_rates.map((value) => toNumber(value))
    : [];
  const fallback = toNumber(snapshot.rates.overall_win_rate, 0);
  return Array.from({ length }, (_, index) => winRates[index] ?? fallback);
}

function estimateCapacityPerAe(snapshot: Snapshot): number[] {
  const bb = snapshot.scenario_building_blocks;
  const raw = bb.monthly_ae_capacity.map((capacity, index) => {
    const aeCount = toNumber(bb.monthly_ae_count[index], 0);
    if (aeCount <= 0) return 0;
    return capacity / aeCount;
  });
  const nonZero = raw.filter((value) => value > 0);
  const fallback =
    nonZero.length > 0 ? nonZero[nonZero.length - 1] : 0;
  return raw.map((value) => (value > 0 ? value : fallback));
}

function cumulative(values: number[]): number[] {
  const result: number[] = [];
  let running = 0;
  values.forEach((value) => {
    running += value;
    result.push(running);
  });
  return result;
}

export function buildDefaultScenarioOverrides(snapshot: Snapshot): ScenarioOverrides {
  const baseRates = snapshot.rates.funnel_rates;
  const aeCounts = snapshot.scenario_building_blocks.monthly_ae_count.map((value) => toNumber(value, 0));
  const avgDealSize =
    toNumber(snapshot.scenario_building_blocks.observed_values.avg_deal_size, 0) || 300_000;
  const overridable = getOverridableQuarters(snapshot);

  function buildAeTargets(quarter: ScenarioQuarterKey): [number, number, number] {
    const indexes = getQuarterMonthIndexes(snapshot, quarter);
    const values = indexes.map((index) => aeCounts[index] ?? 0);
    return [
      values[0] ?? values[values.length - 1] ?? 0,
      values[1] ?? values[values.length - 1] ?? 0,
      values[2] ?? values[values.length - 1] ?? 0,
    ];
  }

  const result: ScenarioOverrides = {};
  for (const quarter of overridable) {
    result[quarter] = {
      addAes: 0,
      aeMonthTargets: buildAeTargets(quarter),
      mqlChangePct: 0,
      mqlToS0: toNumber(baseRates.mql_to_s0, 0),
      s0ToS1: toNumber(baseRates.s0_to_s1, 0),
      s1ToS2: toNumber(baseRates.s1_to_s2, 0),
      avgDealSize,
    };
  }
  return result;
}

export function cloneScenarioOverrides(overrides: ScenarioOverrides): ScenarioOverrides {
  const result: ScenarioOverrides = {};
  for (const quarter of Object.keys(overrides)) {
    const src = overrides[quarter];
    result[quarter] = {
      ...src,
      aeMonthTargets: [...src.aeMonthTargets] as [number, number, number],
    };
  }
  return result;
}

export function hasQuarterOverride(
  quarter: ScenarioQuarterKey,
  current: ScenarioOverrides,
  baseline: ScenarioOverrides,
): boolean {
  const currentQuarter = current[quarter];
  const baselineQuarter = baseline[quarter];

  const scalarChanged =
    Math.abs(currentQuarter.mqlChangePct - baselineQuarter.mqlChangePct) > 1e-9 ||
    Math.abs(currentQuarter.mqlToS0 - baselineQuarter.mqlToS0) > 1e-9 ||
    Math.abs(currentQuarter.s0ToS1 - baselineQuarter.s0ToS1) > 1e-9 ||
    Math.abs(currentQuarter.s1ToS2 - baselineQuarter.s1ToS2) > 1e-9 ||
    Math.abs(currentQuarter.avgDealSize - baselineQuarter.avgDealSize) > 1e-9 ||
    Math.abs(currentQuarter.addAes - baselineQuarter.addAes) > 1e-9;

  const aeTargetsChanged = currentQuarter.aeMonthTargets.some(
    (value, index) => Math.abs(value - baselineQuarter.aeMonthTargets[index]) > 1e-9,
  );

  return scalarChanged || aeTargetsChanged;
}

export function hasAnyScenarioOverride(
  current: ScenarioOverrides,
  baseline: ScenarioOverrides,
): boolean {
  return Object.keys(current).some((quarter) =>
    hasQuarterOverride(quarter, current, baseline),
  );
}

interface OrderedAeTargetRef {
  quarter: ScenarioQuarterKey;
  monthOffset: number;
  current: number;
  baseline: number;
}

function orderedAeTargetRefs(
  current: ScenarioOverrides,
  baseline: ScenarioOverrides,
): OrderedAeTargetRef[] {
  return Object.keys(current).flatMap((quarter) =>
    current[quarter].aeMonthTargets.map((value, monthOffset) => ({
      quarter,
      monthOffset,
      current: Math.round(toNumber(value, 0)),
      baseline: Math.round(toNumber(baseline[quarter]?.aeMonthTargets[monthOffset], 0)),
    })),
  );
}

export function applyAeSeatTargetEdit(
  current: ScenarioOverrides,
  baseline: ScenarioOverrides,
  quarter: ScenarioQuarterKey,
  monthOffset: number,
  requestedValue: number,
): ScenarioOverrides {
  const ordered = orderedAeTargetRefs(current, baseline);
  const targetIndex = ordered.findIndex(
    (entry) => entry.quarter === quarter && entry.monthOffset === monthOffset,
  );
  if (targetIndex === -1) return cloneScenarioOverrides(current);

  const targetEntry = ordered[targetIndex];
  const previousValue = targetIndex > 0 ? ordered[targetIndex - 1]?.current ?? 0 : 0;
  const normalizedTarget = Math.max(
    Math.round(toNumber(requestedValue, targetEntry.current)),
    targetEntry.baseline,
    previousValue,
  );

  const delta = normalizedTarget - targetEntry.current;
  const next = cloneScenarioOverrides(current);

  if (Math.abs(delta) < 1e-9) {
    next[quarter].aeMonthTargets[monthOffset] = normalizedTarget;
    return next;
  }

  ordered.forEach((entry, index) => {
    if (index < targetIndex) return;
    const previousApplied =
      index > 0
        ? next[ordered[index - 1].quarter].aeMonthTargets[ordered[index - 1].monthOffset]
        : 0;
    const candidate = Math.round(entry.current + delta);
    const applied = Math.max(candidate, entry.baseline, previousApplied);
    next[entry.quarter].aeMonthTargets[entry.monthOffset] = applied;
  });

  return next;
}

export function computeScenario(snapshot: Snapshot, overrides: ScenarioOverrides): ScenarioResult {
  const bb = snapshot.scenario_building_blocks;
  const months = bb.months;
  const n = months.length;
  const firstProjected = firstProjectedMonthIndex(snapshot);

  const inventoryWins = bb.monthly_inventory_wins.map((value) => toNumber(value));
  const baselineFutureWins = bb.monthly_future_wins.map((value) => toNumber(value));
  const aeCreation = bb.monthly_ae_creation.map((value) => toNumber(value));
  const mqlCreation = bb.monthly_mql_creation.map((value) => toNumber(value));
  const monthlyCapacity = bb.monthly_ae_capacity.map((value) => toNumber(value));
  const monthlyAeCount = bb.monthly_ae_count.map((value) => toNumber(value));

  const baseAvgDealSize =
    toNumber(bb.observed_values.avg_deal_size, 0) || 300_000;
  const observedAeProductivity = toNumber(
    bb.observed_values.productivity_per_ae_per_month,
    0,
  );
  const baseMqlToS0 = toNumber(bb.funnel_rates.mql_to_s0, 0);
  const baseS0ToS1 = toNumber(bb.funnel_rates.s0_to_s1, 0);
  const baseS1ToS2 = toNumber(bb.funnel_rates.s1_to_s2, 0);
  const baseAeFactor = baseAvgDealSize * baseS0ToS1 * baseS1ToS2;
  const baseMqlFactor = baseMqlToS0 * baseAeFactor;

  const rampCurve = getObservedRampCurve(snapshot);
  const capacityPerAe = estimateCapacityPerAe(snapshot);
  const baselinePipelineCreated = aeCreation.map(
    (value, index) => value + (mqlCreation[index] ?? 0),
  );

  const overridable = getOverridableQuarters(snapshot);
  const aeCohorts: Array<{ startIndex: number; count: number }> = [];
  let carriedMonthlyExtraAes = 0;

  overridable.forEach((quarter) => {
    const override = overrides[quarter];
    if (!override) return;
    const monthIndexes = getQuarterMonthIndexes(snapshot, quarter);
    monthIndexes.forEach((monthIndex, monthOffset) => {
      if (monthIndex < firstProjected) return;
      const desiredTotal = Math.max(
        toNumber(override.aeMonthTargets[monthOffset], monthlyAeCount[monthIndex] ?? 0),
        monthlyAeCount[monthIndex] ?? 0,
      );
      const rawExtraAes = Math.max(0, desiredTotal - (bb.monthly_ae_count[monthIndex] ?? 0));
      const effectiveExtraAes = Math.max(rawExtraAes, carriedMonthlyExtraAes);
      const monthCohortCount = effectiveExtraAes - carriedMonthlyExtraAes;
      if (monthCohortCount > 0) {
        aeCohorts.push({ startIndex: monthIndex, count: monthCohortCount });
      }
      carriedMonthlyExtraAes = effectiveExtraAes;
    });
  });

  overridable.forEach((quarter) => {
    const override = overrides[quarter];
    if (!override) return;
    const startIndex = months.findIndex((month) => quarterForMonth(snapshot, month) === quarter);
    if (startIndex === -1) return;
    const count = Math.max(0, Math.round(toNumber(override.addAes, 0)));
    if (count <= 0) return;
    aeCohorts.push({ startIndex, count });
  });

  for (let index = firstProjected; index < n; index += 1) {
    let extraAeCreation = 0;
    let extraCapacity = 0;
    let extraHeadcount = 0;

    aeCohorts.forEach((cohort) => {
      if (index < cohort.startIndex) return;
      const ramp = getRampFactor(rampCurve, index - cohort.startIndex);
      extraHeadcount += cohort.count;
      extraAeCreation +=
        observedAeProductivity *
        cohort.count *
        ramp *
        baseS0ToS1 *
        baseS1ToS2 *
        baseAvgDealSize;
      extraCapacity += (capacityPerAe[index] ?? 0) * cohort.count * ramp;
    });

    aeCreation[index] += extraAeCreation;
    monthlyCapacity[index] += extraCapacity;
    monthlyAeCount[index] += extraHeadcount;
  }

  for (let index = firstProjected; index < n; index += 1) {
    const quarter = quarterForMonth(snapshot, months[index]);
    if (!quarter || !overridable.includes(quarter)) {
      continue;
    }

    const override = overrides[quarter];
    if (!override) continue;
    const effMqlToS0 = toNumber(override.mqlToS0, baseMqlToS0);
    const effS0ToS1 = toNumber(override.s0ToS1, baseS0ToS1);
    const effS1ToS2 = toNumber(override.s1ToS2, baseS1ToS2);
    const effDealSize = toNumber(override.avgDealSize, baseAvgDealSize);
    const effAeFactor = effDealSize * effS0ToS1 * effS1ToS2;
    const effMqlFactor = effMqlToS0 * effAeFactor;
    const aeScale = baseAeFactor > 0 ? effAeFactor / baseAeFactor : 1;
    const mqlScale = baseMqlFactor > 0 ? effMqlFactor / baseMqlFactor : 1;
    const mqlVolumeScale = Math.max(0, 1 + toNumber(override.mqlChangePct, 0));

    aeCreation[index] *= aeScale;
    mqlCreation[index] *= mqlScale * mqlVolumeScale;
  }

  const monthlyPipelineCreated = aeCreation.map(
    (value, index) => value + (mqlCreation[index] ?? 0),
  );
  const futureWinRates = getFutureGenerationWinRates(snapshot, n);
  const winAdjustedCreationDelta = monthlyPipelineCreated.map(
    (value, index) => (value - (baselinePipelineCreated[index] ?? 0)) * (futureWinRates[index] ?? 0),
  );
  const futureWinsDelta = stackCohorts(winAdjustedCreationDelta, bb.decay_curve).slice(0, n);
  const futureWins = baselineFutureWins.map(
    (value, index) => value + (futureWinsDelta[index] ?? 0),
  );

  for (let index = 0; index < firstProjected; index += 1) {
    aeCreation[index] = toNumber(bb.monthly_ae_creation[index], 0);
    mqlCreation[index] = toNumber(bb.monthly_mql_creation[index], 0);
    monthlyPipelineCreated[index] = aeCreation[index] + mqlCreation[index];
    futureWins[index] = baselineFutureWins[index];
    monthlyCapacity[index] = toNumber(bb.monthly_ae_capacity[index], 0);
    monthlyAeCount[index] = toNumber(bb.monthly_ae_count[index], 0);
  }

  const monthlyExpected = inventoryWins.map(
    (value, index) => value + (futureWins[index] ?? 0),
  );

  for (let index = 0; index < firstProjected; index += 1) {
    monthlyExpected[index] = toNumber(bb.monthly_total_expected[index], monthlyExpected[index]);
  }

  const monthlyCapped = applyCapacityCeiling(monthlyExpected, monthlyCapacity);
  const monthlyOverflow = computeOverflow(monthlyExpected, monthlyCapacity);

  for (let index = 0; index < firstProjected; index += 1) {
    monthlyCapped[index] = toNumber(bb.monthly_capped[index], monthlyExpected[index]);
    monthlyOverflow[index] = 0;
  }

  return {
    monthly_inventory_wins: inventoryWins,
    monthly_future_wins: futureWins,
    monthly_pipeline_created: monthlyPipelineCreated,
    monthly_ae_creation: aeCreation,
    monthly_mql_creation: mqlCreation,
    monthly_expected: monthlyExpected,
    monthly_capped: monthlyCapped,
    monthly_capacity: monthlyCapacity,
    monthly_ae_count: monthlyAeCount,
    monthly_overflow: monthlyOverflow,
    cumulative_expected: cumulative(monthlyExpected),
    cumulative_capped: cumulative(monthlyCapped),
    fy_expected: sum(monthlyExpected),
    fy_capped: sum(monthlyCapped),
  };
}
