import { describe, expect, it } from "vitest";

import mightyPlanJson from "../../../public/data/profiles/mighty-oak-holdings/plans/mighty-fy26-abm-gap.json";
import mightySnapshotJson from "../../../public/data/profiles/mighty-oak-holdings/snapshot.json";
import saplingPlanJson from "../../../public/data/profiles/sapling-industries/plans/sapling-fy26-segment-shift.json";
import saplingSnapshotJson from "../../../public/data/profiles/sapling-industries/snapshot.json";
import sproutPlanJson from "../../../public/data/profiles/sprout-labs/plans/sprout-fy26-pmf.json";
import sproutSnapshotJson from "../../../public/data/profiles/sprout-labs/snapshot.json";
import { buildFunnelHealthViewModel } from "../funnelHealthViewModel";
import { normalizePlanPreset } from "../plans";
import type { PlanPreset, RawPlanPreset } from "../plans";
import type { Snapshot } from "../../types/snapshot";

type PersonaId = "sprout-labs" | "sapling-industries" | "mighty-oak-holdings";

interface PersonaFixture {
  snapshot: Snapshot;
  plan: PlanPreset;
}

const PERSONAS: Record<PersonaId, PersonaFixture> = {
  "sprout-labs": {
    snapshot: sproutSnapshotJson as Snapshot,
    plan: normalizePlanPreset(sproutPlanJson as RawPlanPreset),
  },
  "sapling-industries": {
    snapshot: saplingSnapshotJson as Snapshot,
    plan: normalizePlanPreset(saplingPlanJson as RawPlanPreset),
  },
  "mighty-oak-holdings": {
    snapshot: mightySnapshotJson as Snapshot,
    plan: normalizePlanPreset(mightyPlanJson as RawPlanPreset),
  },
};

function viewModel(persona: PersonaId, selectedQuarter = "Q1FY26") {
  const fixture = PERSONAS[persona];
  return buildFunnelHealthViewModel({
    snapshot: fixture.snapshot,
    plan: fixture.plan,
    selectedQuarter,
  });
}

function metricValues(persona: PersonaId) {
  return Object.fromEntries(
    viewModel(persona).metrics.map((metric) => [
      metric.label,
      { value: metric.value, delta: metric.delta },
    ]),
  );
}

describe("buildFunnelHealthViewModel", () => {
  it("pins first-quarter KPI strip values for all committed persona fixtures", () => {
    expect(metricValues("sprout-labs")).toEqual({
      "Plan Bookings": { value: "$1.6M", delta: undefined },
      Reforecast: { value: "$1.4M", delta: "9% gap" },
      "Actual Bookings": { value: "$1.4M", delta: "100% through Q" },
      "AEs (Plan / Model)": { value: "6 / 11", delta: "11 ramped" },
      Confidence: { value: "committed", delta: undefined },
    });

    expect(metricValues("sapling-industries")).toEqual({
      "Plan Bookings": { value: "$10.0M", delta: undefined },
      Reforecast: { value: "$8.0M", delta: "20% gap" },
      "Actual Bookings": { value: "$8.0M", delta: "100% through Q" },
      "AEs (Plan / Model)": { value: "30 / 20", delta: "18 ramped" },
      Confidence: { value: "committed", delta: undefined },
    });

    expect(metricValues("mighty-oak-holdings")).toEqual({
      "Plan Bookings": { value: "$17.0M", delta: undefined },
      Reforecast: { value: "$16.0M", delta: "6% gap" },
      "Actual Bookings": { value: "$16.0M", delta: "100% through Q" },
      "AEs (Plan / Model)": { value: "96 / 136", delta: "133 ramped" },
      Confidence: { value: "committed", delta: undefined },
    });
  });

  it("pins Sapling weekly pace row formatting for current rendered values", () => {
    const rows = Object.fromEntries(
      viewModel("sapling-industries").paceRows.map((row) => [row.stage, row]),
    );

    expect(rows["MQLs / wk"]).toMatchObject({
      plan: "0.0",
      actual: "0.0",
      delta: "+0.0",
      deltaPct: "—",
    });
    expect(rows["MQL to S0 rate"]).toMatchObject({
      plan: "12.0%",
      actual: "12.0%",
      delta: "+0.0pp",
      deltaPct: "+0%",
    });
    expect(rows["AEs in Seat"]).toMatchObject({
      plan: "30",
      actual: "20",
      delta: "-10.0",
      deltaPct: "-33%",
    });
    expect(rows["Sales-Led ARR"]).toMatchObject({
      plan: "$10.0M",
      actual: "$8.0M",
      delta: "$-2.0M",
      deltaPct: "-20%",
    });
  });

  it("pins observed conversion-rate rows and rolling S2-to-won provenance", () => {
    const rows = Object.fromEntries(
      viewModel("sapling-industries").rateRows.map((row) => [row.transition, row]),
    );

    expect(rows["mql → s0"]).toMatchObject({
      transition: "mql → s0",
      rate: "12.0%",
      source: "Config assumption",
      sampleSize: "—",
      methodology: "registry_activity_rate",
    });
    expect(rows["plg pql → s1"]).toMatchObject({
      transition: "plg pql → s1",
      rate: "11.0%",
      source: "Static config",
      sampleSize: "—",
      methodology: "legacy_plg_pql_to_s0 * s0_to_s1",
    });
    expect(rows["s2 → won"]).toMatchObject({
      transition: "s2 → won",
      rate: "33.9%",
      source: "ProfileBackend",
      sampleSize: "n=112",
      methodology: "—",
    });
  });

  it("pins source-stream and expansion visibility without fabricated actual columns", () => {
    const sproutStreams = viewModel("sprout-labs").sourceStreams;
    const sapling = viewModel("sapling-industries");
    expect(sproutStreams).not.toBeNull();
    expect(sapling.sourceStreams).not.toBeNull();
    expect(sapling.expansion).not.toBeNull();

    expect(sproutStreams!.rows.map((row) => row.displayName)).toEqual([
      "Marketing / SDR",
      "AE Self-Gen",
    ]);
    expect(sproutStreams!.showActualColumns).toBe(false);

    expect(sapling.sourceStreams!.rows.map((row) => row.displayName)).toEqual([
      "Marketing / SDR",
      "AE Self-Gen",
    ]);
    const expansionMetrics = sapling.expansion!.metrics.map(
      (metric) => ({ label: metric.label, value: metric.value }),
    );
    expect(expansionMetrics).toEqual([
      { label: "Opening ARR", value: "$40.0M" },
      { label: "Total Expansion", value: "$1.7M" },
      { label: "Program Maturity", value: "100.0%" },
      { label: "Renewable Sales-Led", value: "$9.5M" },
    ]);
  });

  it("suppresses unreliable weekly plan and actual columns from Quarterly Funnel Summary", () => {
    const summary = viewModel("sapling-industries").quarterlySummary;

    expect(summary.headers).toEqual(["Quarter", "Bookings"]);
    expect(summary.rows).toEqual([
      { quarter: "Q1FY26", selected: true, bookings: "$8.0M" },
      { quarter: "Q2FY26", selected: false, bookings: "$11.5M" },
      { quarter: "Q3FY26", selected: false, bookings: "$14.8M" },
      { quarter: "Q4FY26", selected: false, bookings: "$16.1M" },
    ]);
  });
});
