import { describe, expect, it } from "vitest";

import mightyPlanJson from "../../../public/data/profiles/mighty-oak-holdings/plans/mighty-fy26-abm-gap.json";
import mightySnapshotJson from "../../../public/data/profiles/mighty-oak-holdings/snapshot.json";
import saplingPlanJson from "../../../public/data/profiles/sapling-industries/plans/sapling-fy26-segment-shift.json";
import saplingSnapshotJson from "../../../public/data/profiles/sapling-industries/snapshot.json";
import sproutPlanJson from "../../../public/data/profiles/sprout-labs/plans/sprout-fy26-pmf.json";
import sproutSnapshotJson from "../../../public/data/profiles/sprout-labs/snapshot.json";
import type { Snapshot } from "../../types/snapshot";
import {
  buildPlanMonthlyReference,
  normalizePlanPreset,
  type PlanPreset,
  type RawPlanPreset,
} from "../plans";

type PersonaId = "sprout-labs" | "sapling-industries" | "mighty-oak-holdings";

interface PersonaFixture {
  id: PersonaId;
  snapshot: Snapshot;
  plan: PlanPreset;
}

const EPSILON = 1e-6;
const QUARTERS = ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"] as const;
type Quarter = (typeof QUARTERS)[number];

const PERSONAS: Record<PersonaId, PersonaFixture> = {
  "sprout-labs": {
    id: "sprout-labs",
    snapshot: sproutSnapshotJson as Snapshot,
    plan: normalizePlanPreset(sproutPlanJson as RawPlanPreset),
  },
  "sapling-industries": {
    id: "sapling-industries",
    snapshot: saplingSnapshotJson as Snapshot,
    plan: normalizePlanPreset(saplingPlanJson as RawPlanPreset),
  },
  "mighty-oak-holdings": {
    id: "mighty-oak-holdings",
    snapshot: mightySnapshotJson as Snapshot,
    plan: normalizePlanPreset(mightyPlanJson as RawPlanPreset),
  },
};

interface RenderedQuarter {
  quarter: Quarter;
  expected: number;
  existing: number;
  plan: number;
  capacity: number;
}

interface RenderedMetrics {
  expected: number;
  plan: number;
  capacity: number;
  monthlyExpectedToPlan: number[];
  monthlyExpectedToCapacity: number[];
  monthlyCapacityToPlan: number[];
  quarters: Record<Quarter, RenderedQuarter>;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function mean(values: number[]): number {
  return sum(values) / values.length;
}

function renderedMetrics({ snapshot, plan }: PersonaFixture): RenderedMetrics {
  const bridge = snapshot.model_output.bookings_bridge;
  const planReference = buildPlanMonthlyReference(bridge.months, plan);
  const capacityByMonth = new Map(
    snapshot.roster.effective_capacity.map((row) => [row.month.slice(0, 10), row.ae_capacity]),
  );

  const quarters = Object.fromEntries(
    QUARTERS.map((quarter) => [
      quarter,
      { quarter, expected: 0, existing: 0, plan: 0, capacity: 0 },
    ]),
  ) as Record<Quarter, RenderedQuarter>;

  bridge.months.forEach((month, index) => {
    const planRow = planReference.rows[index];
    const quarter = planRow?.quarter as Quarter | null;
    if (!quarter || !QUARTERS.includes(quarter)) return;
    const monthKey = month.slice(0, 10);
    quarters[quarter].expected += bridge.total_expected[index] ?? 0;
    quarters[quarter].existing += bridge.existing_wins[index] ?? 0;
    quarters[quarter].plan += planReference.values[index] ?? 0;
    quarters[quarter].capacity += capacityByMonth.get(monthKey) ?? 0;
  });

  const expected = sum(Object.values(quarters).map((quarter) => quarter.expected));
  const planTotal = sum(Object.values(quarters).map((quarter) => quarter.plan));
  const capacity = sum(Object.values(quarters).map((quarter) => quarter.capacity));
  const monthlyExpectedToPlan = bridge.months.map((_, index) => {
    const planValue = planReference.values[index] ?? 0;
    return planValue > 0 ? (bridge.total_expected[index] ?? 0) / planValue : 0;
  });
  const monthlyExpectedToCapacity = bridge.months.map((month, index) => {
    const capacityValue = capacityByMonth.get(month.slice(0, 10)) ?? 0;
    return capacityValue > 0 ? (bridge.total_expected[index] ?? 0) / capacityValue : 0;
  });
  const monthlyCapacityToPlan = bridge.months.map((month, index) => {
    const planValue = planReference.values[index] ?? 0;
    return planValue > 0 ? (capacityByMonth.get(month.slice(0, 10)) ?? 0) / planValue : 0;
  });

  return {
    expected,
    plan: planTotal,
    capacity,
    monthlyExpectedToPlan,
    monthlyExpectedToCapacity,
    monthlyCapacityToPlan,
    quarters,
  };
}

function quarterGap(metrics: RenderedMetrics, quarter: Quarter): number {
  return metrics.quarters[quarter].plan - metrics.quarters[quarter].expected;
}

describe("public persona rendered narrative fixtures", () => {
  it("keeps Sprout's rendered bridge as a visible coverage cliff, not broken near-zero data", () => {
    const metrics = renderedMetrics(PERSONAS["sprout-labs"]);

    expect(metrics.capacity / metrics.plan).toBeGreaterThanOrEqual(0.85);
    expect(metrics.capacity / metrics.plan).toBeLessThanOrEqual(1.15);
    expect(metrics.expected / metrics.plan).toBeGreaterThanOrEqual(0.55);
    expect(metrics.expected / metrics.plan).toBeLessThanOrEqual(0.70);
    expect(mean(metrics.monthlyExpectedToPlan.slice(0, 6))).toBeGreaterThanOrEqual(0.80);
    expect(mean(metrics.monthlyExpectedToPlan.slice(9, 12))).toBeLessThanOrEqual(0.65);
  });

  it("keeps Sapling's rendered bridge as plan-level headcount with a widening capacity gap", () => {
    const metrics = renderedMetrics(PERSONAS["sapling-industries"]);

    for (const monthRatio of metrics.monthlyExpectedToCapacity) {
      expect(monthRatio).toBeLessThanOrEqual(1 + EPSILON);
    }
    for (const monthRatio of metrics.monthlyCapacityToPlan) {
      expect(monthRatio).toBeGreaterThanOrEqual(1);
    }
    expect(metrics.expected / metrics.plan).toBeGreaterThanOrEqual(0.82);
    expect(metrics.expected / metrics.plan).toBeLessThanOrEqual(0.92);
    expect(quarterGap(metrics, "Q2FY26")).toBeGreaterThan(0);
    expect(quarterGap(metrics, "Q3FY26")).toBeGreaterThan(quarterGap(metrics, "Q2FY26"));
    expect(quarterGap(metrics, "Q4FY26")).toBeGreaterThan(quarterGap(metrics, "Q3FY26"));
  });

  it("keeps Mighty Oak's rendered bridge below plan and capacity despite early existing-pipeline weight", () => {
    const metrics = renderedMetrics(PERSONAS["mighty-oak-holdings"]);
    const fyShortfall = metrics.plan - metrics.expected;
    const h2Shortfall = quarterGap(metrics, "Q3FY26") + quarterGap(metrics, "Q4FY26");
    const h1Existing = metrics.quarters.Q1FY26.existing + metrics.quarters.Q2FY26.existing;
    const h1Expected = metrics.quarters.Q1FY26.expected + metrics.quarters.Q2FY26.expected;

    for (const monthRatio of metrics.monthlyExpectedToCapacity) {
      expect(monthRatio).toBeLessThanOrEqual(1 + EPSILON);
    }
    for (const monthRatio of metrics.monthlyExpectedToPlan) {
      expect(monthRatio).toBeLessThanOrEqual(1 + EPSILON);
    }
    expect(metrics.expected / metrics.plan).toBeGreaterThanOrEqual(0.80);
    expect(metrics.expected / metrics.plan).toBeLessThanOrEqual(0.90);
    expect(fyShortfall).toBeGreaterThan(0);
    expect(h2Shortfall / fyShortfall).toBeGreaterThanOrEqual(0.60);
    expect(h1Existing / h1Expected).toBeGreaterThanOrEqual(0.60);
  });

  it("keeps quarter tieout blocks reconciled to the rendered chart series", () => {
    for (const persona of Object.values(PERSONAS)) {
      const metrics = renderedMetrics(persona);
      const quarterBlocks = persona.snapshot.model_output.bookings_bridge.trajectory_quarters;

      for (const quarterBlock of quarterBlocks) {
        const quarter = quarterBlock.quarter as Quarter;
        if (!QUARTERS.includes(quarter)) continue;
        const renderedQuarter = metrics.quarters[quarter];
        const topDown = (quarterBlock.top_down as { bookings?: number }).bookings ?? 0;
        const bottomsUp =
          (quarterBlock.bottoms_up as { sales_led_arr?: number }).sales_led_arr ?? 0;

        expect(Math.abs(topDown - renderedQuarter.plan) / renderedQuarter.plan).toBeLessThanOrEqual(0.15);
        expect(Math.abs(bottomsUp - renderedQuarter.expected) / renderedQuarter.expected).toBeLessThanOrEqual(0.15);
      }
    }
  });
});
