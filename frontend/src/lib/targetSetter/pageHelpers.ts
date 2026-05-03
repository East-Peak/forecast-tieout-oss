/**
 * pageHelpers.ts — Build the data structures the TargetSetter page passes to
 * its child components.
 *
 * Functions exported:
 *   buildRateByEdge        — per-edge RateProvenance map for FunnelSankey/Grid
 *   buildScenarioOptions   — scenario pill strip options (data-driven from snapshot)
 *   buildRoleCards         — Marketing / Outbound / Sales summary cards
 *   buildTotalS0Footer     — combined S0 footer with Marketing + Outbound breakdown
 *
 * Design notes:
 *   - Scenario provenance comes from each scenario's description fields, not from hardcoded labels.
 *   - buildScenarioOptions is data-driven from snapshot.target_setter.scenarios.
 *   - funnel_rate_descriptions is heterogeneous across profiles; coerceRateProvenance
 *     normalizes the divergent shapes ({label,lookback_days} vs {value,source} vs
 *     {value,source,methodology}) into a uniform RateProvenance.
 */

import type { RateProvenance, Snapshot } from "../../types/snapshot";
import type {
  Scenario,
  ScenarioOption,
  RoleSummaryCard,
  TotalFooter,
} from "../../types/targetSetter";
import { loadScenariosFromSnapshot } from "./scenarios";
import { buildObservedScenario } from "./observedScenario";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Normalize an unknown raw funnel_rate_descriptions entry into a complete
 * RateProvenance.
 *
 * The OSS snapshot ships heterogeneous shapes depending on profile:
 *   - Acme:   { label: string; lookback_days: number }  (no `value` key)
 *   - Others: { value: number; source: string }
 *             { value: number; source: string; methodology: string }
 *
 * fallbackValue / fallbackSource / fallbackMethodology are used when the raw
 * entry is missing the corresponding field.
 */
function coerceRateProvenance(
  raw: unknown,
  fallbackValue: number,
  fallbackSource: string,
  fallbackMethodology: string,
): RateProvenance {
  const r =
    raw && typeof raw === "object"
      ? (raw as Record<string, unknown>)
      : {};
  return {
    value: typeof r.value === "number" ? r.value : fallbackValue,
    source:
      typeof r.source === "string"
        ? r.source
        : typeof r.label === "string"
          ? r.label
          : fallbackSource,
    n: typeof r.n === "number" ? r.n : null,
    methodology:
      typeof r.methodology === "string" ? r.methodology : fallbackMethodology,
    lookback_days:
      typeof r.lookback_days === "number" ? r.lookback_days : undefined,
    calibrated_at:
      typeof r.calibrated_at === "string" ? r.calibrated_at : undefined,
  };
}

// ---------------------------------------------------------------------------
// buildRateByEdge
// ---------------------------------------------------------------------------

/**
 * Build the `rateByEdge` object passed to FunnelSankey + FunnelGrid.
 *
 * For the Observed scenario, pulls real provenance from
 * `snapshot.model_output.funnel_health.funnel_rate_descriptions` where
 * available, trying both key naming conventions (mql_to_sql / mql_to_s0).
 *
 * For all other scenarios, synthesizes a RateProvenance shell sourced from
 * the scenario's own description (data-driven — no hardcoded label strings).
 */
export function buildRateByEdge(
  scenario: Scenario,
  snapshot: Snapshot,
): {
  mql_to_s0: RateProvenance;
  outbound_to_s0: RateProvenance;
  s0_to_s1: RateProvenance;
  s1_to_s2: RateProvenance;
} {
  const descriptions =
    snapshot.model_output?.funnel_health?.funnel_rate_descriptions ?? {};

  if (scenario.id === "observed") {
    // Try both key naming conventions:
    //   mql_to_sql / sql_to_opp / opp_to_s2  — Acme profile
    //   mql_to_s0  / s0_to_s1   / s1_to_s2   — sprout/sapling/mighty-oak
    const rawMql =
      (descriptions.mql_to_sql as unknown) ??
      (descriptions.mql_to_s0 as unknown);
    const rawS0 =
      (descriptions.sql_to_opp as unknown) ??
      (descriptions.s0_to_s1 as unknown);
    const rawS1 =
      (descriptions.opp_to_s2 as unknown) ??
      (descriptions.s1_to_s2 as unknown);

    const mqlEdge = coerceRateProvenance(
      rawMql,
      scenario.mql_to_s0,
      "snapshot",
      "observed",
    );

    return {
      mql_to_s0: mqlEdge,
      outbound_to_s0: {
        ...mqlEdge,
        source: `${mqlEdge.source} · same-rate proxy`,
        methodology: "MQL→S0 rate applied to outbound conversion",
      },
      s0_to_s1: coerceRateProvenance(
        rawS0,
        scenario.s0_to_s1,
        "snapshot",
        "observed",
      ),
      s1_to_s2: coerceRateProvenance(
        rawS1,
        scenario.s1_to_s2,
        "snapshot",
        "observed",
      ),
    };
  }

  // Non-observed: use the scenario's own description as provenance (no
  // hardcoded internal flavor strings).
  const source = scenario.description?.primary ?? scenario.label;
  const methodology = scenario.description?.secondary ?? "";

  const synth = (value: number, methodologySuffix = ""): RateProvenance => ({
    value,
    source,
    n: null,
    methodology: methodology + methodologySuffix,
  });

  return {
    mql_to_s0: synth(scenario.mql_to_s0),
    outbound_to_s0: synth(scenario.mql_to_s0, " · same-rate proxy"),
    s0_to_s1: synth(scenario.s0_to_s1),
    s1_to_s2: synth(scenario.s1_to_s2),
  };
}

// ---------------------------------------------------------------------------
// buildScenarioOptions
// ---------------------------------------------------------------------------

/**
 * Build the ordered scenario pill list for the ScenarioSelector component.
 *
 * Order: Observed (if present) → snapshot scenarios (in snapshot order) →
 * Custom pill (if includeCustom=true).
 *
 * Fully data-driven from snapshot — no hardcoded scenario ids or label strings.
 */
export function buildScenarioOptions(
  snapshot: Snapshot,
  /** When true, append a "Custom" pill reflecting the user's live adjustments. */
  includeCustom = false,
): ScenarioOption[] {
  const opts: ScenarioOption[] = [];

  const observed = buildObservedScenario(snapshot);
  if (observed) {
    opts.push({
      id: observed.id,
      label: observed.label,
      primaryLine: observed.description?.primary ?? "",
      secondaryLine: observed.description?.secondary ?? "",
    });
  }

  for (const s of loadScenariosFromSnapshot(snapshot)) {
    opts.push({
      id: s.id,
      label: s.label,
      primaryLine: s.description?.primary ?? "",
      secondaryLine: s.description?.secondary ?? "",
    });
  }

  if (includeCustom) {
    opts.push({
      id: "custom",
      label: "Custom",
      primaryLine: "Your adjustments",
      secondaryLine: "session-only",
    });
  }

  return opts;
}

// ---------------------------------------------------------------------------
// buildRoleCards
// ---------------------------------------------------------------------------

/**
 * Shape pre-computed quarter rows into RoleSummaryCard[] for RoleSummaryStrip.
 *
 * Produces three cards: Marketing (MQLs + marketing-sourced S0 secondary),
 * Outbound (outbound S0), and Sales (S2 SQOs).
 */
export function buildRoleCards(
  quarters: Array<{
    quarter: string;
    mqls: number;
    s0: number;
    outbound_s0: number;
    marketing_s2_total: number;
  }>,
  mqlQoq: number | null,
): RoleSummaryCard[] {
  const sum = (pick: (q: (typeof quarters)[number]) => number) =>
    quarters.reduce((acc, q) => acc + pick(q), 0);
  const perQ = (pick: (q: (typeof quarters)[number]) => number) =>
    quarters.map((q) => ({ quarter: q.quarter, value: pick(q) }));

  return [
    {
      role: "Marketing",
      metricLabel: "MQLs needed",
      totalValue: sum((q) => q.mqls),
      integer: true,
      perQuarter: perQ((q) => q.mqls),
      qoqDelta: mqlQoq,
      secondary: {
        label: "→ Marketing-sourced S0 needed",
        totalValue: sum((q) => q.s0),
        integer: true,
        perQuarter: perQ((q) => q.s0),
      },
    },
    {
      role: "Outbound",
      metricLabel: "Outbound S0 needed",
      totalValue: sum((q) => q.outbound_s0),
      integer: true,
      perQuarter: perQ((q) => q.outbound_s0),
      qoqDelta: null,
    },
    {
      role: "Sales",
      metricLabel: "S2 SQOs needed",
      totalValue: sum((q) => q.marketing_s2_total),
      integer: true,
      perQuarter: perQ((q) => q.marketing_s2_total),
      qoqDelta: null,
    },
  ];
}

// ---------------------------------------------------------------------------
// buildTotalS0Footer
// ---------------------------------------------------------------------------

/**
 * Build the combined S0 footer row shown below the role strip, decomposed
 * into Marketing and Outbound sub-components.
 */
export function buildTotalS0Footer(
  quarters: Array<{
    quarter: string;
    s0: number;
    outbound_s0: number;
    total_s0: number;
  }>,
): TotalFooter {
  const sum = (pick: (q: (typeof quarters)[number]) => number) =>
    quarters.reduce((acc, q) => acc + pick(q), 0);
  const perQ = (pick: (q: (typeof quarters)[number]) => number) =>
    quarters.map((q) => ({ quarter: q.quarter, value: pick(q) }));

  return {
    label: "Total S0 needed (Marketing + Outbound)",
    totalValue: sum((q) => q.total_s0),
    integer: true,
    perQuarter: perQ((q) => q.total_s0),
    components: [
      { label: "Marketing", value: sum((q) => q.s0) },
      { label: "Outbound", value: sum((q) => q.outbound_s0) },
    ],
  };
}
