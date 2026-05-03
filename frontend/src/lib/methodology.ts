import type { Snapshot } from "../types/snapshot";
import type { OrgProfile } from "./orgProfiles";
import { buildConnectorPolicyNotes } from "./orgProfiles";
import {
  buildPlanTimingSemantics,
  type PlanPreset,
  type PlanTimingSemantics,
} from "./plans";
import {
  asRecord,
  buildCriticalSignals,
  buildFallbackExceptions,
  getAuditHealthRows,
  getAuditOverallStatus,
  humanSourceLabel,
} from "./audit";

export interface MethodologyAssumptionRow {
  label: string;
  value: string;
  source: string;
}

export interface MethodologyPrinciple {
  title: string;
  summary: string;
}

export interface MethodologyProvenanceItem {
  label: string;
  value: string;
}

export interface MethodologyViewModel {
  narrativeNotes: string[];
  overallStatus: string;
  healthRows: ReturnType<typeof getAuditHealthRows>;
  criticalSignals: ReturnType<typeof buildCriticalSignals>;
  fallbackExceptions: ReturnType<typeof buildFallbackExceptions>;
  assumptions: MethodologyAssumptionRow[];
  principles: MethodologyPrinciple[];
  provenanceItems: MethodologyProvenanceItem[];
  planTimingSemantics: PlanTimingSemantics;
  decaySourceSummary: string | null;
  orgProfileName: string;
}

export const METHODOLOGY_PRINCIPLES: MethodologyPrinciple[] = [
  {
    title: "Two-Scenario Architecture",
    summary:
      "The model maintains two parallel views: Bottoms-Up (derived from current pipeline and headcount) and the selected Top-Down Target package. Neither is labeled 'the plan' — they serve different questions. Bottoms-Up answers 'what will we actually do?'; Top-Down answers 'what gap are we managing to?'",
  },
  {
    title: "Rate Registry",
    summary:
      "Conversion and funnel rates are resolved through runtime provenance rather than hardcoded in model functions. Depending on the signal, the active source may be CRM-observed activity, blended mature cohorts, or warehouse-observed cohorts. The critical signal ledger is the canonical source-of-truth for which method is active in the saved snapshot.",
  },
  {
    title: "AE Productivity Model",
    summary:
      "Productivity is modeled as a multiplier against observed baseline, not as an absolute quota. Ramping AEs contribute proportionally based on months elapsed vs ramp curve. Blended capacity = ramped AEs × 1.0 + ramping AEs × ramp fraction. This avoids double-counting new hire contributions.",
  },
  {
    title: "Actuals-Spliced Trajectory",
    summary:
      "Months with confirmed actual bookings are locked in the model — the scenario engine cannot modify them. Projections begin at the first future month. The solid/dashed line split on cumulative charts marks this boundary visually. This prevents retroactive 'what-if' distortions of closed history.",
  },
  {
    title: "Conservative Flat-Carry",
    summary:
      "For pipeline not covered by existing inventory or AE capacity, the model carries forward a flat rate (no growth assumption) rather than extrapolating trends. This is deliberately conservative — upside requires explicit scenario inputs, not passive extrapolation.",
  },
  {
    title: "Confirmed Hires Only",
    summary:
      "The roster model includes only confirmed hires (offer accepted). Open requisitions and anticipated headcount are excluded. Headcount upside is modeled through explicit scenario overrides to the monthly AE seat path, keeping the base trajectory conservative and scenario exploration explicit.",
  },
];

export function livePipelineSource(provenance: Record<string, unknown>): string {
  const source = typeof provenance.source === "string" ? provenance.source : "Unknown";
  const isLive = provenance.is_live;
  if (isLive === true) return `${source} (live)`;
  if (isLive === false) return `${source} (snapshot)`;
  return source;
}

export function buildMethodologyViewModel(
  snapshot: Snapshot,
  orgProfile: OrgProfile | null = null,
  scenarioEngineLabel: string | null = null,
  plan: PlanPreset | null = null,
): MethodologyViewModel {
  const rates = snapshot.rates;
  const observed = snapshot.scenario_building_blocks.observed_values;
  const funnelRateDescriptions =
    (snapshot.model_output.funnel_health.funnel_rate_descriptions as Record<
      string,
      Record<string, unknown>
    >) ?? {};
  const rollingS2ToWon =
    (snapshot.model_output.funnel_health.rolling_s2_to_won as Record<string, unknown>) ?? {};
  const s2RateSource = humanSourceLabel(String(rollingS2ToWon.source ?? "config"));
  const s2RateSample = Number(rollingS2ToWon.sample ?? 0);
  const provenance = asRecord(snapshot.provenance);
  const decayProvenance = asRecord(provenance.decay_curve);

  const assumptions: MethodologyAssumptionRow[] = [
    {
      label: "S2+ Win Rate (Observed)",
      value: `${(rates.overall_win_rate * 100).toFixed(1)}%`,
      source: s2RateSample > 0 ? `${s2RateSource} (n=${s2RateSample})` : s2RateSource,
    },
    {
      label: "Avg Deal Size (Observed)",
      value: `$${(observed.avg_deal_size / 1000).toFixed(0)}K`,
      source: "Closed Won deals, trailing 12mo",
    },
    {
      label: "Avg Cycle Days (Observed)",
      value: `${observed.avg_cycle_days.toFixed(0)}d`,
      source: "Runtime S2-S5 stage-duration sum",
    },
    {
      label: "Ramp Months (Observed)",
      value: `${observed.ramp_months.toFixed(0)} mo`,
      source: "Observed AE ramp curve",
    },
    {
      label: "AE Self-Gen S0 / Ramped AE / Month",
      value:
        observed.productivity_per_ae_per_month > 0
          ? observed.productivity_per_ae_per_month.toFixed(1)
          : "\u2014",
      source: "Trailing AE-sourced S0s / ramped AE-months",
    },
    ...Object.entries(rates.stage_conversion).map(([stage, rate]) => ({
      label: `${stage} Win Rate`,
      value: `${(rate * 100).toFixed(1)}%`,
      source: "Runtime stage probability",
    })),
    ...Object.entries(rates.stage_velocity_days).map(([stage, days]) => ({
      label: `${stage} Velocity`,
      value: `${days.toFixed(0)}d`,
      source: "Runtime observed stage duration",
    })),
    ...Object.entries(rates.funnel_rates).map(([key, rate]) => {
      const desc = funnelRateDescriptions[key] ?? {};
      const source = humanSourceLabel(String(desc.source ?? "config"));
      const sample = Number(desc.n ?? 0);
      return {
        label: key,
        value: `${(rate * 100).toFixed(2)}%`,
        source: sample > 0 ? `${source} (n=${sample})` : source,
      };
    }),
  ];

  const decaySourceSummary =
    Object.keys(decayProvenance).length > 0
      ? `Active close timing source: ${humanSourceLabel(
          String(decayProvenance.source ?? "unknown"),
        )}${
          typeof decayProvenance.sample === "number" ? ` (n=${decayProvenance.sample})` : ""
        }${
          typeof decayProvenance.minimum_sample === "number"
            ? `, minimum accepted sample ${decayProvenance.minimum_sample}`
            : ""
        }.`
      : null;
  const connectorPolicyNotes = orgProfile ? buildConnectorPolicyNotes(orgProfile) : [];
  const orgProfileName = orgProfile?.name ?? "Default org profile";
  const planTimingSemantics = buildPlanTimingSemantics(
    snapshot.scenario_building_blocks.months,
    plan,
  );

  return {
    narrativeNotes: [
      ...(connectorPolicyNotes.length
        ? [
            `${orgProfileName} connector policy is explicit and profile-scoped. ${connectorPolicyNotes.join(
              " ",
            )}`,
          ]
        : []),
      "The Audit tab is now the canonical finance-readiness surface for the current saved artifact. This page keeps the narrative model logic and design principles, while the readiness, critical-signal, and exception sections below remain snapshot-derived for traceability.",
      ...(scenarioEngineLabel
        ? [
            `Scenario recompute currently runs through ${scenarioEngineLabel} over the saved profile-scoped snapshot bundle. The request/response contract is aligned to the backend snapshot scenario service so the planner can move behind a canonical API boundary without another surface rewrite.`,
          ]
        : []),
      "Selected plan presets can carry explicit month-level targets, month-level AE seat paths, and note-only forward context metadata beyond the visible app horizon. Operator pages only compare against the selected plan's operator-comparable default view, and those plan-side targets remain reference metadata rather than inputs that rewrite the saved bottoms-up trajectory.",
      'The Forecast Tieout model separates forecast into two streams: existing pipeline (inventory) and future pipeline (created by capacity). Existing pipeline is the set of open S2+ deals in the snapshot as of the snapshot date. Each deal is assigned a win probability based on its stage using all-inclusive observed rates — won deals divided by total deals at that stage including still-open ones. This deliberately captures the "zombie pipeline" effect where deals perpetually push without closing.',
      "Future S2+ pipeline is modeled from two forward streams: AE self-gen creation and marketing-sourced pipeline creation. New AEs ramp along an observed curve calibrated to time-to-productivity, while marketing input flows through the live funnel-rate stack. The Scenario Planner keeps saved trajectory, plan target, and active overrides separate: AE seat timing is flexed at month grain, while demand, conversion, and pricing assumptions remain quarter-scoped.",
      "Actuals are spliced in as they become available. Once a month is confirmed closed, its bookings are locked and the model trajectory pivots forward from that point. The cumulative chart uses a solid line for actuals and a dashed line for projections, making the confirmed-vs-projected boundary explicit. Realized wins use contractual CloseDate, realized losses use actual Closed At timing, and finance-facing pipeline creation actuals use first entry into S2 rather than opp CreatedDate. Plan targets from the selected preset are overlaid for gap-to-plan visibility, but they do not seed the saved trajectory math.",
      "Export semantics follow the same split. The JSON snapshot and audit report remain tied to the saved baseline artifact, while the monthly CSV in Export Pack mirrors the live Scenario Planner state currently active in the app session. That lets finance compare saved baseline, active what-if scenario, and selected plan reference without conflating them.",
    ],
    overallStatus: getAuditOverallStatus(snapshot),
    healthRows: getAuditHealthRows(snapshot),
    criticalSignals: buildCriticalSignals(snapshot),
    fallbackExceptions: buildFallbackExceptions(snapshot),
    assumptions,
    principles: METHODOLOGY_PRINCIPLES,
    planTimingSemantics,
    provenanceItems: [
      { label: "Org profile", value: orgProfileName },
      { label: "CRM connector", value: orgProfile?.connectors.crm ?? "\u2014" },
      { label: "Warehouse connector", value: orgProfile?.connectors.warehouse ?? "\u2014" },
      { label: "Scenario engine", value: scenarioEngineLabel ?? "\u2014" },
      { label: "Snapshot generated", value: snapshot.generated_at },
      { label: "Pipeline as of", value: snapshot.as_of },
      { label: "Git SHA", value: snapshot.git_sha ? snapshot.git_sha.slice(0, 8) : "\u2014" },
      { label: "Deal count", value: String(snapshot.pipeline.deals.length) },
      {
        label: "Pipeline source",
        value: livePipelineSource(snapshot.pipeline.provenance),
      },
      {
        label: "Close timing source",
        value: humanSourceLabel(String(decayProvenance.source ?? "unknown")),
      },
      {
        label: "Rate source",
        value: "Mixed runtime sources; see critical signal ledger",
      },
    ],
    decaySourceSummary,
    orgProfileName,
  };
}
