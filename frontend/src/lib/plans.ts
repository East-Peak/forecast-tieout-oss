import { formatMonthLabel } from "./format";
import { monthBelongsToQuarter, numericScalar } from "./plans/normalize";

export * from "./plans/types";
export { derivePlanId, normalizePlanPreset } from "./plans/normalize";
import type {
  PlanMonthlyReference,
  PlanMonthlyReferenceBasis,
  PlanMonthlyReferenceRow,
  PlanPacingFieldId,
  PlanPacingProvenance,
  PlanPreset,
  PlanTimingSemantics,
  PlanTimingSemanticsItem,
  ResolvedPlanPacingField,
  ResolvedPlanPacingProvenance,
} from "./plans/types";

export function getPlanQuarterTarget(
  plan: PlanPreset | null,
  quarter: string,
): number | null {
  if (!plan?.availability.comparableOnOperatorPages || !plan.availability.quarterlyComparable) {
    return null;
  }
  return numericScalar(plan.targets.quarterlyBookings[quarter]);
}

export function getPlanFyTarget(plan: PlanPreset | null): number | null {
  if (!plan?.availability.comparableOnOperatorPages || !plan.availability.annualComparable) {
    return null;
  }
  return plan.fyTarget;
}

export function getPlanSeatQuarterTarget(
  plan: PlanPreset | null,
  quarter: string,
): number | null {
  if (!plan?.availability.comparableOnOperatorPages) return null;
  return numericScalar(plan.targets.quarterEndAeTargets[quarter]);
}

export function getPlanSeatMonthlyTarget(
  plan: PlanPreset | null,
  month: string,
): number | null {
  if (!plan?.availability.comparableOnOperatorPages) return null;
  return numericScalar(plan.targets.explicitMonthlyAeTargets[month]);
}

function buildFallbackProvenance(
  snapshotAsOf: string | null | undefined,
): PlanPacingProvenance {
  return {
    source: "snapshot_runtime_fallback",
    derivation: "normalized_domain_fallback",
    approvalStatus: "not_plan_approved",
    freshnessAsOf: snapshotAsOf ?? null,
    freshnessStatus: snapshotAsOf ? "present" : "missing_reference_date",
    label: "Snapshot-derived fallback",
    notes: snapshotAsOf
      ? []
      : ["Snapshot-derived fallback is missing a snapshot as-of date."],
  };
}

export function getCurrentDateInTimeZone(timeZone = "America/Los_Angeles"): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function classifyProvenanceState(
  provenance: PlanPacingProvenance,
): ResolvedPlanPacingProvenance["presentationState"] {
  if (
    provenance.source === "snapshot_runtime_fallback" ||
    provenance.derivation === "normalized_domain_fallback"
  ) {
    return "fallback";
  }
  if (provenance.approvalStatus === "approved") {
    return "approved";
  }
  if (provenance.approvalStatus === "not_approved" || provenance.approvalStatus === "working_draft") {
    return "provisional";
  }
  return "unknown";
}

function resolveStaleStatus(
  provenance: PlanPacingProvenance,
  evaluationAsOf: string,
): ResolvedPlanPacingProvenance {
  const freshnessAsOf = provenance.freshnessAsOf;
  if (!freshnessAsOf) {
    return {
      ...provenance,
      freshnessStatus: provenance.freshnessStatus ?? "missing_reference_date",
      stale: true,
      evaluationAsOf,
      presentationState: classifyProvenanceState(provenance),
    };
  }
  const evaluationDate = new Date(`${evaluationAsOf}T00:00:00Z`);
  const freshnessDate = new Date(`${freshnessAsOf}T00:00:00Z`);
  const days = Math.floor((evaluationDate.getTime() - freshnessDate.getTime()) / 86_400_000);
  return {
    ...provenance,
    stale: !Number.isFinite(days) || days > 30,
    evaluationAsOf,
    presentationState: classifyProvenanceState(provenance),
  };
}

export function resolvePlanPacingField(
  plan: PlanPreset | null,
  quarter: string,
  fieldId: PlanPacingFieldId,
  options?: {
    snapshotFallbackValue?: number | null;
    snapshotAsOf?: string | null;
    evaluationAsOf?: string;
    timeZone?: string;
  },
): ResolvedPlanPacingField {
  if (!plan?.availability.comparableOnOperatorPages || !plan.availability.quarterlyComparable) {
    return { value: null, provenance: null, source: "none" };
  }

  const evaluationAsOf =
    options?.evaluationAsOf ?? getCurrentDateInTimeZone(options?.timeZone);
  const planField = plan.pacing[quarter]?.fields[fieldId];
  if (planField) {
    return {
      value: planField.value,
      provenance: resolveStaleStatus(planField.provenance, evaluationAsOf),
      source: "plan",
    };
  }

  if (typeof options?.snapshotFallbackValue === "number") {
    const provenance = buildFallbackProvenance(options.snapshotAsOf);
    return {
      value: options.snapshotFallbackValue,
      provenance: resolveStaleStatus(provenance, evaluationAsOf),
      source: "fallback",
    };
  }

  return { value: null, provenance: null, source: "none" };
}

export function buildPlanMonthlyReference(
  months: string[],
  plan: PlanPreset | null,
): PlanMonthlyReference {
  if (!plan) {
    return {
      values: new Array(months.length).fill(0),
      rows: [],
      basis: "none",
      label: "Comparable Monthly Plan",
      note: null,
    };
  }

  if (!plan.availability.comparableOnOperatorPages) {
    return {
      values: new Array(months.length).fill(0),
      rows: [],
      basis: "suppressed_non_comparable",
      label: "Comparable Monthly Plan",
      note:
        "The selected plan has no operator-comparable default view, so monthly selected-plan rails are suppressed on operator pages.",
    };
  }

  if (plan.schemaVersion === 2 && !plan.availability.monthlyComparable) {
    return {
      values: new Array(months.length).fill(0),
      rows: [],
      basis: "unsupported_monthly",
      label: "Comparable Monthly Plan",
      note:
        "The selected comparable view does not support monthly grain in v2, so monthly selected-plan rails are intentionally suppressed rather than quarter-split or backfilled.",
    };
  }

  const rows = months.map((month): PlanMonthlyReferenceRow => {
    const explicitValue = plan.targets.explicitMonthlyBookings[month];
    if (typeof explicitValue === "number") {
      const quarter =
        Object.keys(plan.targets.quarterlyBookings).find((candidate) =>
          monthBelongsToQuarter(month, candidate),
        ) ?? null;
      return {
        month,
        quarter,
        value: explicitValue,
        basis: "explicit_monthly_plan",
      };
    }

    const quarter =
      Object.keys(plan.targets.quarterlyBookings).find((candidate) =>
        monthBelongsToQuarter(month, candidate),
      ) ?? null;
    const target = quarter ? getPlanQuarterTarget(plan, quarter) : null;
    const matchingMonths = quarter
      ? months.filter((candidate) => monthBelongsToQuarter(candidate, quarter))
      : [];
    return {
      month,
      quarter,
      value: quarter && target !== null && matchingMonths.length > 0 ? target / matchingMonths.length : 0,
      basis: "derived_even_quarter_split",
    };
  });

  const uniqueBases = new Set(rows.map((row) => row.basis));
  const basis: PlanMonthlyReferenceBasis =
    uniqueBases.size === 0
      ? "none"
      : uniqueBases.size === 1
        ? rows[0]?.basis ?? "none"
        : "mixed";

  let note: string | null = null;
  if (basis === "explicit_monthly_plan") {
    note = "The monthly comparison rail comes from explicit monthly values on the selected comparable view.";
  } else if (basis === "derived_even_quarter_split") {
    note =
      "This is a legacy plan asset. Its monthly rail is still shown as an even split of quarter targets until the asset is regenerated as schema_version 2.";
  } else if (basis === "mixed") {
    note =
      "This legacy plan mixes explicit monthly values with even-split quarter fallback for months that are still absent.";
  }

  return {
    values: rows.map((row) => row.value),
    rows,
    basis,
    label: "Comparable Monthly Plan",
    note,
  };
}

function sortUniqueIsoMonths(months: string[]): string[] {
  return Array.from(new Set(months)).sort((left, right) => left.localeCompare(right));
}

function describeMonthRange(months: string[]): string | null {
  const sorted = sortUniqueIsoMonths(months);
  if (sorted.length === 0) return null;
  if (sorted.length === 1) return formatMonthLabel(sorted[0]);
  return `${formatMonthLabel(sorted[0])} to ${formatMonthLabel(sorted[sorted.length - 1])}`;
}

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

export function buildPlanTimingSemantics(
  months: string[],
  plan: PlanPreset | null,
): PlanTimingSemantics {
  if (!plan) {
    return {
      selectedPlanName: "No selected plan",
      comparisonScopeLabel: null,
      comparisonScopeId: null,
      overview:
        "No selected plan is loaded, so operator pages only describe the saved snapshot baseline and the active scenario layer.",
      items: [
        {
          label: "Comparison Scope",
          detail:
            "No plan-specific comparison scope is active. Scenario and export math stay anchored to the saved snapshot only.",
          tone: "slate",
        },
        {
          label: "Monthly Plan Rail",
          detail:
            "No selected plan is loaded, so there is no monthly comparison rail to overlay against the saved trajectory.",
          tone: "slate",
        },
        {
          label: "Seat And Pacing Ownership",
          detail:
            "No plan-specific seat owner or pacing package is active. Any seat changes or pacing references come from the saved baseline and scenario overrides only.",
          tone: "slate",
        },
        {
          label: "Forecast Boundary",
          detail:
            "Selecting a plan changes comparison rails only. The saved baseline and live scenario still start from the profile-scoped snapshot bundle.",
          tone: "slate",
        },
      ],
    };
  }

  const monthlyReference = buildPlanMonthlyReference(months, plan);
  const activeMonths = sortUniqueIsoMonths(months);
  const activeHorizonEnd = activeMonths[activeMonths.length - 1] ?? null;
  const forwardMonths = sortUniqueIsoMonths(
    Object.values(plan.forwardContext?.referenceSeries ?? {}).flatMap((series) =>
      Object.keys(series),
    ),
  ).filter((month) => (activeHorizonEnd ? month > activeHorizonEnd : true));

  let comparisonScopeDetail = `Primary operator comparisons use ${plan.comparisonScopeLabel ?? "the selected comparable view"} (${plan.comparisonScopeId ?? "no-scope-id"}).`;
  let comparisonScopeTone: PlanTimingSemanticsItem["tone"] = "blue";
  if (!plan.availability.comparableOnOperatorPages) {
    comparisonScopeDetail =
      "The selected plan's default comparison view is not operator-comparable, so Scenario, Export, and other operator pages suppress primary gap math instead of inventing a sales-led comparator.";
    comparisonScopeTone = "amber";
  }

  if (plan.executiveContext.available) {
    comparisonScopeDetail += ` Derived executive context (${plan.executiveContext.label}) remains separate, includes held assumptions, and is not scenario-controlled.`;
  }

  let monthlyRailDetail = monthlyReference.note ?? "No monthly comparison rail is active.";
  let monthlyRailTone: PlanTimingSemanticsItem["tone"] = "slate";
  if (monthlyReference.basis === "explicit_monthly_plan") {
    monthlyRailDetail = `The selected comparable view is month-shaped across the active app horizon${
      describeMonthRange(activeMonths) ? ` (${describeMonthRange(activeMonths)})` : ""
    }. Operator pages use those explicit monthly values directly.`;
    monthlyRailTone = "blue";
  } else if (monthlyReference.basis === "derived_even_quarter_split") {
    monthlyRailTone = "amber";
  } else if (
    monthlyReference.basis === "unsupported_monthly" ||
    monthlyReference.basis === "suppressed_non_comparable"
  ) {
    monthlyRailTone = "amber";
  }

  let seatOwnershipDetail =
    "Seat targets, pacing targets, and conversion targets are suppressed because the selected plan is not operator-comparable.";
  let seatOwnershipTone: PlanTimingSemanticsItem["tone"] = "amber";
  if (plan.availability.comparableOnOperatorPages) {
    if (plan.availability.explicitMonthlyAeTargets) {
      seatOwnershipDetail = `Quarter-end seat targets are owned by ${plan.comparison.seatTargetOwnerComponentId ?? "the selected comparable component"}, and the plan also ships an explicit month-level seat path for operator pages.`;
      seatOwnershipTone = "emerald";
    } else if (plan.availability.quarterEndAeTargets) {
      seatOwnershipDetail = `Seat targets are owned by ${plan.comparison.seatTargetOwnerComponentId ?? "the selected comparable component"}, but only as quarter-end milestones. Month-level seat timing remains scenario-defined.`;
      seatOwnershipTone = "amber";
    } else {
      seatOwnershipDetail =
        "The selected comparable view does not ship renderable seat targets. Operator pages suppress seat references rather than infer an owner.";
    }

    if (plan.availability.quarterlyComparable) {
      if (plan.availability.quarterlyMqlPace || plan.availability.quarterlyConversionRates) {
        seatOwnershipDetail +=
          " Quarter-scoped pacing and conversion references follow the same comparable view and can fall back field-by-field to snapshot/runtime values only when explicit plan pacing is absent.";
      } else {
        seatOwnershipDetail +=
          " Quarter-scoped pacing and conversion references fall back field-by-field from the snapshot when explicit plan pacing is absent.";
      }
    } else {
      seatOwnershipDetail +=
        " The comparable view does not support quarterly grain, so quarter-scoped seat, pacing, and conversion references stay suppressed.";
    }
  }

  let forwardContextDetail =
    "No additional forward context is shipped beyond the active horizon in this selected plan.";
  let forwardContextTone: PlanTimingSemanticsItem["tone"] = "slate";
  if (forwardMonths.length > 0) {
    forwardContextDetail = `Forward context continues beyond the active horizon${
      describeMonthRange(forwardMonths) ? ` (${describeMonthRange(forwardMonths)})` : ""
    }, but it remains note-only in v2. Those ${pluralize(forwardMonths.length, "month", "months")} cannot be promoted into active math without generating a new plan version.`;
    forwardContextTone = "blue";
  } else if (plan.forwardContext) {
    forwardContextDetail =
      "This plan carries explicit note-only forward context metadata, but none of its reference series extend past the visible app horizon.";
    forwardContextTone = "blue";
  }

  return {
    selectedPlanName: plan.name,
    comparisonScopeLabel: plan.comparisonScopeLabel,
    comparisonScopeId: plan.comparisonScopeId,
    overview: `${plan.name} remains a comparison artifact. Operator pages bind to ${plan.comparisonScopeLabel ?? "the selected view"} and never let forward context or executive context rewrite the saved forecast math.`,
    items: [
      {
        label: "Comparison Scope",
        detail: comparisonScopeDetail,
        tone: comparisonScopeTone,
      },
      {
        label: "Monthly Plan Rail",
        detail: monthlyRailDetail,
        tone: monthlyRailTone,
      },
      {
        label: "Seat And Pacing Ownership",
        detail: seatOwnershipDetail,
        tone: seatOwnershipTone,
      },
      {
        label: "Forward Context",
        detail: forwardContextDetail,
        tone: forwardContextTone,
      },
    ],
  };
}
