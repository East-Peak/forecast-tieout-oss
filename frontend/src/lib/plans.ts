import { formatMonthLabel } from "./format";

/**
 * Plan-validation heuristic: does the given month string belong to the given
 * fiscal-quarter label?
 *
 * Plans are loaded BEFORE the snapshot is available (both fetch in parallel),
 * so the validator can't read `snapshot.scenario_building_blocks.quarter_by_month`
 * to know the calendar. Instead it parses the quarter label as `Q<n>FY<yy>`
 * and assumes a Feb-start year-of-start fiscal calendar — the convention Acme
 * uses, and the convention nearly all B2B SaaS plans we've seen use.
 *
 * If a plan declares quarters in a different format (e.g. calendar quarters
 * like "Q1 2026"), this validator will produce false negatives. The fix in
 * that case is to either (a) declare the plan's calendar explicitly in the
 * plan JSON and read it here, or (b) defer rollup validation until the
 * snapshot is loaded and pass `quarter_by_month` in.
 */
function monthBelongsToQuarter(month: string, quarter: string): boolean {
  const m = quarter.match(/^Q(\d)FY(\d{2})$/);
  if (!m) return false;
  const qNum = Number.parseInt(m[1], 10);
  const fyYear = 2000 + Number.parseInt(m[2], 10);
  // Feb-start, year-of-start convention. Q1 starts in Feb of fyYear.
  const monthPrefix = month.slice(0, 7);
  const expected: string[] = [];
  for (let i = 0; i < 3; i += 1) {
    const calMonth = 2 + (qNum - 1) * 3 + i; // 2..13 → wrap to 1
    if (calMonth <= 12) {
      expected.push(`${fyYear}-${String(calMonth).padStart(2, "0")}`);
    } else {
      expected.push(`${fyYear + 1}-${String(calMonth - 12).padStart(2, "0")}`);
    }
  }
  return expected.includes(monthPrefix);
}

export * from "./plans/types";
import type {
  NormalizedSeatValueFamily,
  NormalizedValueFamily,
  PlanArrGrain,
  PlanComponent,
  PlanForwardContext,
  PlanMonthlyReference,
  PlanMonthlyReferenceBasis,
  PlanMonthlyReferenceRow,
  PlanPacingField,
  PlanPacingFieldId,
  PlanPacingProvenance,
  PlanPacingQuarterPackage,
  PlanPreset,
  PlanView,
  PlanTimingSemantics,
  PlanTimingSemanticsItem,
  RawPlanPreset,
  ResolvedPlanPacingField,
  ResolvedPlanPacingProvenance,
  SliderDefaults,
} from "./plans/types";
import { PlanValidationError } from "./plans/types";

const PLAN_TOP_LEVEL_KEYS_V2 = new Set([
  "schema_version",
  "id",
  "name",
  "version",
  "created_date",
  "default_comparison_view_id",
  "default_executive_context_view_id",
  "components",
  "views",
  "pacing",
  "forward_context",
]);
const PLAN_COMPONENT_KEYS_V2 = new Set([
  "label",
  "category",
  "modeled_status",
  "approval_status",
  "basis",
  "as_of",
  "arr_targets",
  "seat_targets",
]);
const PLAN_ARR_TARGET_KEYS_V2 = new Set([
  "canonical_grain",
  "monthly",
  "quarterly",
  "annual",
  "quarterly_rollup",
  "annual_rollup",
]);
const PLAN_SEAT_TARGET_KEYS_V2 = new Set([
  "canonical_grain",
  "monthly",
  "quarterly_rollup",
  "annual_rollup",
]);
const PLAN_VIEW_KEYS_V2 = new Set([
  "label",
  "treatment_class",
  "supported_grains",
  "component_ids",
  "derived",
  "seat_target_owner_component_id",
  "context_kind",
]);
const PLAN_PACING_PACKAGE_KEYS_V2 = new Set(["package_provenance", "fields"]);
const PLAN_PACING_FIELD_KEYS_V2 = new Set(["value", "provenance"]);
const PLAN_PROVENANCE_KEYS_V2 = new Set([
  "source",
  "derivation",
  "approval_status",
  "freshness_as_of",
  "freshness_status",
  "label",
  "notes",
]);
const PLAN_FORWARD_CONTEXT_KEYS_V2 = new Set([
  "mode",
  "promotion_strategy",
  "effective_after",
  "reference_series",
  "notes",
]);
const PLAN_FORWARD_CONTEXT_REFERENCE_IDS = new Set([
  "sales_led_monthly",
  "sales_led_ae_targets",
]);
const PLAN_PACING_FIELD_IDS = new Set<PlanPacingFieldId>([
  "mqls_weekly",
  "s0_weekly",
  "s1_weekly",
  "s2_weekly",
  "mql_to_s0",
  "s0_to_s1",
  "s1_to_s2",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function assertAllowedKeys(
  value: Record<string, unknown>,
  allowed: Set<string>,
  path: string,
) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      throw new PlanValidationError(`Unknown key at ${path}: ${key}`);
    }
  }
}

function numericRecord(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).flatMap(([key, raw]) =>
      typeof raw === "number" && Number.isFinite(raw) ? [[key, raw]] : [],
    ),
  );
}

function numericScalar(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string" && entry.length > 0)
    : [];
}

function sortGrains(grains: Iterable<PlanArrGrain>): PlanArrGrain[] {
  const order: Record<PlanArrGrain, number> = { monthly: 1, quarterly: 2, annual: 3 };
  return Array.from(new Set(grains)).sort((left, right) => order[left] - order[right]);
}

export function derivePlanId(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizeSliderDefaults(value: unknown): SliderDefaults {
  const raw = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    winRate: typeof raw.win_rate === "number" ? raw.win_rate : null,
    avgDealSize: typeof raw.avg_deal_size === "number" ? raw.avg_deal_size : null,
    rampMonths: typeof raw.ramp_months === "number" ? raw.ramp_months : null,
    avgProductivity:
      typeof raw.avg_productivity === "number" ? raw.avg_productivity : null,
    avgCycleDays: typeof raw.avg_cycle_days === "number" ? raw.avg_cycle_days : null,
  };
}

function normalizeProvenance(
  value: unknown,
  path: string,
): PlanPacingProvenance {
  const raw = asRecord(value);
  if (!raw) {
    return {
      source: "unknown",
      derivation: "unknown",
      approvalStatus: "unknown",
      freshnessAsOf: null,
      freshnessStatus: null,
      label: null,
      notes: [],
    };
  }
  assertAllowedKeys(raw, PLAN_PROVENANCE_KEYS_V2, path);
  return {
    source: stringValue(raw.source) ?? "unknown",
    derivation: stringValue(raw.derivation) ?? "unknown",
    approvalStatus: stringValue(raw.approval_status) ?? "unknown",
    freshnessAsOf: stringValue(raw.freshness_as_of),
    freshnessStatus: stringValue(raw.freshness_status),
    label: stringValue(raw.label),
    notes:
      typeof raw.notes === "string"
        ? [raw.notes]
        : stringArray(raw.notes),
  };
}

function mergeProvenance(
  fieldLevel: PlanPacingProvenance | null,
  packageLevel: PlanPacingProvenance,
): PlanPacingProvenance {
  if (!fieldLevel) return packageLevel;
  return {
    source: fieldLevel.source !== "unknown" ? fieldLevel.source : packageLevel.source,
    derivation:
      fieldLevel.derivation !== "unknown" ? fieldLevel.derivation : packageLevel.derivation,
    approvalStatus:
      fieldLevel.approvalStatus !== "unknown"
        ? fieldLevel.approvalStatus
        : packageLevel.approvalStatus,
    freshnessAsOf: fieldLevel.freshnessAsOf ?? packageLevel.freshnessAsOf,
    freshnessStatus: fieldLevel.freshnessStatus ?? packageLevel.freshnessStatus,
    label: fieldLevel.label ?? packageLevel.label,
    notes: [...packageLevel.notes, ...fieldLevel.notes],
  };
}

function normalizePacingField(
  value: unknown,
  packageProvenance: PlanPacingProvenance,
  path: string,
): PlanPacingField | null {
  const raw = asRecord(value);
  if (!raw) return null;
  assertAllowedKeys(raw, PLAN_PACING_FIELD_KEYS_V2, path);
  const fieldValue = numericScalar(raw.value);
  if (fieldValue === null) {
    throw new PlanValidationError(`Missing numeric value at ${path}.value`);
  }
  const fieldProvenance = raw.provenance
    ? normalizeProvenance(raw.provenance, `${path}.provenance`)
    : null;
  return {
    value: fieldValue,
    provenance: mergeProvenance(fieldProvenance, packageProvenance),
  };
}

function normalizePacing(
  value: unknown,
  path: string,
): Record<string, PlanPacingQuarterPackage> {
  const raw = asRecord(value);
  if (!raw) return {};
  const result: Record<string, PlanPacingQuarterPackage> = {};
  for (const [quarter, packageValue] of Object.entries(raw)) {
    const packageRecord = asRecord(packageValue);
    if (!packageRecord) {
      throw new PlanValidationError(`Invalid pacing package at ${path}.${quarter}`);
    }
    assertAllowedKeys(packageRecord, PLAN_PACING_PACKAGE_KEYS_V2, `${path}.${quarter}`);
    const packageProvenance = normalizeProvenance(
      packageRecord.package_provenance,
      `${path}.${quarter}.package_provenance`,
    );
    const fieldsRecord = asRecord(packageRecord.fields);
    if (!fieldsRecord) {
      throw new PlanValidationError(`Missing pacing fields at ${path}.${quarter}.fields`);
    }
    const fields: Partial<Record<PlanPacingFieldId, PlanPacingField>> = {};
    for (const [fieldId, fieldValue] of Object.entries(fieldsRecord)) {
      if (!PLAN_PACING_FIELD_IDS.has(fieldId as PlanPacingFieldId)) {
        throw new PlanValidationError(`Unknown pacing field ${fieldId} at ${path}.${quarter}.fields`);
      }
      const normalizedField = normalizePacingField(
        fieldValue,
        packageProvenance,
        `${path}.${quarter}.fields.${fieldId}`,
      );
      if (normalizedField) {
        fields[fieldId as PlanPacingFieldId] = normalizedField;
      }
    }
    result[quarter] = {
      packageProvenance,
      fields,
    };
  }
  return result;
}

function validateTargetBlockKeys(
  raw: Record<string, unknown>,
  allowed: Set<string>,
  path: string,
) {
  assertAllowedKeys(raw, allowed, path);
}

function normalizeArrTargets(
  value: unknown,
  path: string,
): NormalizedValueFamily {
  const raw = asRecord(value);
  if (!raw) throw new PlanValidationError(`Missing arr_targets at ${path}`);
  validateTargetBlockKeys(raw, PLAN_ARR_TARGET_KEYS_V2, path);
  const canonicalGrain = stringValue(raw.canonical_grain);
  if (canonicalGrain !== "monthly" && canonicalGrain !== "quarterly" && canonicalGrain !== "annual") {
    throw new PlanValidationError(`Unsupported canonical_grain at ${path}`);
  }

  const monthly = numericRecord(raw.monthly);
  const quarterly =
    canonicalGrain === "quarterly"
      ? numericRecord(raw.quarterly)
      : numericRecord(raw.quarterly_rollup);
  const annual =
    canonicalGrain === "annual"
      ? numericScalar(raw.annual)
      : numericScalar(raw.annual_rollup);
  const rawBlocks = [
    Object.keys(monthly).length > 0 ? "monthly" : null,
    canonicalGrain === "quarterly" && Object.keys(quarterly).length > 0 ? "quarterly" : null,
    canonicalGrain === "annual" && annual !== null ? "annual" : null,
  ].filter(Boolean);

  if (canonicalGrain === "monthly") {
    if (Object.keys(monthly).length === 0) {
      throw new PlanValidationError(`${path} must include monthly raw targets.`);
    }
    if (Object.keys(quarterly).length === 0) {
      throw new PlanValidationError(`${path} must include quarterly_rollup for monthly canonical grain.`);
    }
  } else if (canonicalGrain === "quarterly") {
    if (Object.keys(quarterly).length === 0) {
      throw new PlanValidationError(`${path} must include quarterly raw targets.`);
    }
  } else if (annual === null) {
    throw new PlanValidationError(`${path} must include annual raw targets.`);
  }

  if (rawBlocks.length !== 1) {
    throw new PlanValidationError(`${path} may contain exactly one raw target block matching canonical_grain.`);
  }

  if (canonicalGrain === "monthly") {
    for (const [quarter, declared] of Object.entries(quarterly)) {
      const calculated = Object.entries(monthly).reduce((sum, [month, monthValue]) => {
        return monthBelongsToQuarter(month, quarter) ? sum + monthValue : sum;
      }, 0);
      if (calculated !== declared) {
        throw new PlanValidationError(`${path} quarterly_rollup mismatch for ${quarter}.`);
      }
    }
    const calculatedAnnual = Object.values(monthly).reduce((sum, monthValue) => sum + monthValue, 0);
    if (annual !== null && calculatedAnnual !== annual) {
      throw new PlanValidationError(`${path} annual_rollup mismatch.`);
    }
  } else if (canonicalGrain === "quarterly") {
    const calculatedAnnual = Object.values(quarterly).reduce((sum, quarterValue) => sum + quarterValue, 0);
    if (annual !== null && calculatedAnnual !== annual) {
      throw new PlanValidationError(`${path} annual_rollup mismatch.`);
    }
  }

  return {
    canonicalGrain,
    monthly,
    quarterly,
    annual,
  };
}

function normalizeSeatTargets(
  value: unknown,
  path: string,
): NormalizedSeatValueFamily | null {
  if (value == null) return null;
  const raw = asRecord(value);
  if (!raw) throw new PlanValidationError(`Invalid seat_targets at ${path}`);
  validateTargetBlockKeys(raw, PLAN_SEAT_TARGET_KEYS_V2, path);
  const canonicalGrain = stringValue(raw.canonical_grain);
  if (canonicalGrain !== "monthly" && canonicalGrain !== "quarterly" && canonicalGrain !== "annual") {
    throw new PlanValidationError(`Unsupported seat canonical_grain at ${path}`);
  }

  const monthly = numericRecord(raw.monthly);
  const quarterly = numericRecord(raw.quarterly_rollup);
  const annual = numericScalar(raw.annual_rollup);

  if (canonicalGrain === "monthly") {
    if (Object.keys(monthly).length === 0) {
      throw new PlanValidationError(`${path} must include monthly seat targets.`);
    }
    for (const value of Object.values(monthly)) {
      if (!Number.isInteger(value)) {
        throw new PlanValidationError(`${path} monthly seat targets must be integers.`);
      }
    }
    for (const [quarter, declared] of Object.entries(quarterly)) {
      const quarterMonths = Object.keys(monthly)
        .filter((month) => monthBelongsToQuarter(month, quarter))
        .sort((left, right) => left.localeCompare(right));
      const finalMonth = quarterMonths[quarterMonths.length - 1];
      if (!finalMonth || monthly[finalMonth] !== declared) {
        throw new PlanValidationError(`${path} quarter-end seat rollup mismatch for ${quarter}.`);
      }
    }
    const sortedMonths = Object.keys(monthly).sort((left, right) => left.localeCompare(right));
    const finalMonth = sortedMonths[sortedMonths.length - 1];
    if (annual !== null && finalMonth && monthly[finalMonth] !== annual) {
      throw new PlanValidationError(`${path} annual seat rollup mismatch.`);
    }
  } else if (canonicalGrain === "quarterly") {
    if (Object.keys(quarterly).length === 0) {
      throw new PlanValidationError(`${path} must include quarterly seat targets.`);
    }
    for (const value of Object.values(quarterly)) {
      if (!Number.isInteger(value)) {
        throw new PlanValidationError(`${path} quarterly seat targets must be integers.`);
      }
    }
    const sortedQuarters = Object.keys(quarterly).sort((left, right) => left.localeCompare(right));
    const finalQuarter = sortedQuarters[sortedQuarters.length - 1];
    if (annual !== null && finalQuarter && quarterly[finalQuarter] !== annual) {
      throw new PlanValidationError(`${path} annual seat rollup mismatch.`);
    }
  } else if (annual === null || !Number.isInteger(annual)) {
    throw new PlanValidationError(`${path} must include integer annual seat targets.`);
  }

  return {
    canonicalGrain,
    monthly,
    quarterly,
    annual,
  };
}

function derivableGrains(component: PlanComponent): PlanArrGrain[] {
  if (component.arrTargets.canonicalGrain === "monthly") return ["monthly", "quarterly", "annual"];
  if (component.arrTargets.canonicalGrain === "quarterly") return ["quarterly", "annual"];
  return ["annual"];
}

function intersectGrains(grainSets: PlanArrGrain[][]): PlanArrGrain[] {
  if (grainSets.length === 0) return [];
  return sortGrains(
    grainSets[0].filter((grain) => grainSets.every((set) => set.includes(grain))),
  );
}

function deriveViewTotals(
  componentIds: string[],
  components: Record<string, PlanComponent>,
  supportedGrains: PlanArrGrain[],
): PlanView["totals"] {
  const componentList = componentIds.map((componentId) => components[componentId]);
  const totals = {
    monthly: {} as Record<string, number>,
    quarterly: {} as Record<string, number>,
    annual: null as number | null,
  };

  if (supportedGrains.includes("monthly")) {
    const monthKeys = Array.from(
      new Set(componentList.flatMap((component) => Object.keys(component.arrTargets.monthly))),
    );
    for (const month of monthKeys) {
      totals.monthly[month] = componentList.reduce(
        (sum, component) => sum + (component.arrTargets.monthly[month] ?? 0),
        0,
      );
    }
  }

  if (supportedGrains.includes("quarterly")) {
    const quarterKeys = Array.from(
      new Set(componentList.flatMap((component) => Object.keys(component.arrTargets.quarterly))),
    );
    for (const quarter of quarterKeys) {
      totals.quarterly[quarter] = componentList.reduce(
        (sum, component) => sum + (component.arrTargets.quarterly[quarter] ?? 0),
        0,
      );
    }
  }

  if (supportedGrains.includes("annual")) {
    totals.annual = componentList.reduce(
      (sum, component) => sum + (component.arrTargets.annual ?? 0),
      0,
    );
  }

  return totals;
}

function normalizeComponent(
  componentId: string,
  value: unknown,
  path: string,
): PlanComponent {
  const raw = asRecord(value);
  if (!raw) throw new PlanValidationError(`Invalid component at ${path}`);
  assertAllowedKeys(raw, PLAN_COMPONENT_KEYS_V2, path);

  const modeledStatus = stringValue(raw.modeled_status);
  if (modeledStatus !== "scenario_modeled" && modeledStatus !== "held_assumption") {
    throw new PlanValidationError(`Unsupported modeled_status at ${path}`);
  }

  return {
    id: componentId,
    label: stringValue(raw.label) ?? componentId,
    category: stringValue(raw.category) ?? "unknown",
    modeledStatus,
    approvalStatus: stringValue(raw.approval_status) ?? "unknown",
    basis: stringValue(raw.basis) ?? "unknown",
    asOf: stringValue(raw.as_of) ?? "",
    arrTargets: normalizeArrTargets(raw.arr_targets, `${path}.arr_targets`),
    seatTargets: normalizeSeatTargets(raw.seat_targets, `${path}.seat_targets`),
  };
}

function normalizeForwardContext(
  value: unknown,
  path: string,
): PlanForwardContext | null {
  if (value == null) return null;
  const raw = asRecord(value);
  if (!raw) throw new PlanValidationError(`Invalid forward_context at ${path}`);
  assertAllowedKeys(raw, PLAN_FORWARD_CONTEXT_KEYS_V2, path);
  const mode = stringValue(raw.mode);
  const promotionStrategy = stringValue(raw.promotion_strategy);
  if (mode !== "note_only" || promotionStrategy !== "requires_new_plan_version") {
    throw new PlanValidationError(`forward_context at ${path} must remain note_only in v2.`);
  }

  const referenceSeriesRaw = asRecord(raw.reference_series) ?? {};
  const referenceSeries: Record<string, Record<string, number>> = {};
  for (const [seriesId, seriesValue] of Object.entries(referenceSeriesRaw)) {
    if (!PLAN_FORWARD_CONTEXT_REFERENCE_IDS.has(seriesId)) {
      throw new PlanValidationError(`Unknown forward_context.reference_series id at ${path}: ${seriesId}`);
    }
    referenceSeries[seriesId] = numericRecord(seriesValue);
  }

  return {
    mode: "note_only",
    promotionStrategy: "requires_new_plan_version",
    effectiveAfter: stringValue(raw.effective_after),
    referenceSeries,
    notes:
      typeof raw.notes === "string"
        ? [raw.notes]
        : stringArray(raw.notes),
  };
}

function normalizeV2PlanPreset(
  raw: RawPlanPreset,
  source: { manifestId?: string | null; path?: string | null },
): PlanPreset {
  const rawRecord = raw as unknown as Record<string, unknown>;
  assertAllowedKeys(rawRecord, PLAN_TOP_LEVEL_KEYS_V2, "plan");
  if (!raw.id) throw new PlanValidationError("V2 plans must carry an explicit id.");
  if (source.manifestId && source.manifestId !== raw.id) {
    throw new PlanValidationError(
      `Manifest id ${source.manifestId} does not match payload id ${raw.id}.`,
    );
  }
  if (!raw.default_comparison_view_id) {
    throw new PlanValidationError("V2 plans must declare default_comparison_view_id.");
  }

  const componentsRaw = asRecord(raw.components);
  if (!componentsRaw || Object.keys(componentsRaw).length === 0) {
    throw new PlanValidationError("V2 plans must declare canonical components.");
  }
  const components = Object.fromEntries(
    Object.entries(componentsRaw).map(([componentId, componentValue]) => [
      componentId,
      normalizeComponent(componentId, componentValue, `plan.components.${componentId}`),
    ]),
  );

  const viewsRaw = asRecord(raw.views);
  if (!viewsRaw || Object.keys(viewsRaw).length === 0) {
    throw new PlanValidationError("V2 plans must declare canonical views.");
  }
  const views: Record<string, PlanView> = {};
  for (const [viewId, viewValue] of Object.entries(viewsRaw)) {
    const viewRecord = asRecord(viewValue);
    if (!viewRecord) throw new PlanValidationError(`Invalid view at plan.views.${viewId}`);
    assertAllowedKeys(viewRecord, PLAN_VIEW_KEYS_V2, `plan.views.${viewId}`);
    const treatmentClass = stringValue(viewRecord.treatment_class);
    if (treatmentClass !== "operator_comparable" && treatmentClass !== "executive_reference") {
      throw new PlanValidationError(`Unsupported treatment_class for ${viewId}.`);
    }
    const componentIds = stringArray(viewRecord.component_ids);
    if (componentIds.length === 0) {
      throw new PlanValidationError(`View ${viewId} must include at least one component id.`);
    }
    for (const componentId of componentIds) {
      if (!components[componentId]) {
        throw new PlanValidationError(`View ${viewId} references unknown component ${componentId}.`);
      }
    }
    if (treatmentClass === "operator_comparable") {
      for (const componentId of componentIds) {
        if (components[componentId].modeledStatus !== "scenario_modeled") {
          throw new PlanValidationError(
            `Operator-comparable view ${viewId} may include only scenario_modeled components.`,
          );
        }
      }
    }
    const supportedGrains = sortGrains(
      stringArray(viewRecord.supported_grains).filter(
        (grain): grain is PlanArrGrain =>
          grain === "monthly" || grain === "quarterly" || grain === "annual",
      ),
    );
    const derivedGrains = intersectGrains(
      componentIds.map((componentId) => derivableGrains(components[componentId])),
    );
    if (
      supportedGrains.length === 0 ||
      supportedGrains.some((grain) => !derivedGrains.includes(grain))
    ) {
      throw new PlanValidationError(`View ${viewId} declares unsupported grains.`);
    }
    const seatTargetOwnerComponentId = stringValue(viewRecord.seat_target_owner_component_id);
    if (seatTargetOwnerComponentId) {
      if (!componentIds.includes(seatTargetOwnerComponentId)) {
        throw new PlanValidationError(
          `View ${viewId} seat_target_owner_component_id must be a member component.`,
        );
      }
      if (!components[seatTargetOwnerComponentId]?.seatTargets) {
        throw new PlanValidationError(
          `View ${viewId} seat_target_owner_component_id must expose seat_targets.`,
        );
      }
    }
    views[viewId] = {
      id: viewId,
      label: stringValue(viewRecord.label) ?? viewId,
      treatmentClass,
      supportedGrains,
      componentIds,
      seatTargetOwnerComponentId,
      derived: Boolean(viewRecord.derived),
      contextKind: stringValue(viewRecord.context_kind),
      totals: deriveViewTotals(componentIds, components, supportedGrains),
    };
  }

  const comparisonView = views[raw.default_comparison_view_id];
  if (!comparisonView) {
    throw new PlanValidationError("default_comparison_view_id references an unknown view.");
  }

  const operatorComparableViews = Object.values(views).filter(
    (view) => view.treatmentClass === "operator_comparable",
  );
  if (operatorComparableViews.length > 0 && comparisonView.treatmentClass !== "operator_comparable") {
    throw new PlanValidationError(
      "default_comparison_view_id must resolve to an operator_comparable view when one exists.",
    );
  }

  const executiveViewId = raw.default_executive_context_view_id ?? null;
  const executiveView = executiveViewId ? views[executiveViewId] : null;
  if (executiveViewId) {
    if (!executiveView) {
      throw new PlanValidationError("default_executive_context_view_id references an unknown view.");
    }
    if (executiveView.treatmentClass !== "executive_reference") {
      throw new PlanValidationError("default_executive_context_view_id must reference an executive view.");
    }
    if (executiveView.contextKind !== "total_net_new") {
      throw new PlanValidationError("default_executive_context_view_id must use context_kind total_net_new.");
    }
    if (executiveView.id === comparisonView.id) {
      throw new PlanValidationError("default_executive_context_view_id must differ from default_comparison_view_id.");
    }
  }

  const pacing = normalizePacing(raw.pacing, "plan.pacing");
  if (Object.keys(pacing).length > 0) {
    if (operatorComparableViews.length !== 1) {
      throw new PlanValidationError(
        "V2 pacing requires exactly one operator_comparable view.",
      );
    }
    if (comparisonView.id !== operatorComparableViews[0]?.id) {
      throw new PlanValidationError(
        "V2 pacing requires default_comparison_view_id to resolve to the sole operator_comparable view.",
      );
    }
  }

  const forwardContext = normalizeForwardContext(raw.forward_context, "plan.forward_context");
  const explicitMonthlyBookings =
    comparisonView.treatmentClass === "operator_comparable" &&
    comparisonView.supportedGrains.includes("monthly")
      ? { ...comparisonView.totals.monthly }
      : {};
  const quarterEndSeatTargets =
    comparisonView.seatTargetOwnerComponentId &&
    comparisonView.treatmentClass === "operator_comparable"
      ? { ...(components[comparisonView.seatTargetOwnerComponentId]?.seatTargets?.quarterly ?? {}) }
      : {};
  const explicitMonthlyAeTargets =
    comparisonView.seatTargetOwnerComponentId &&
    comparisonView.treatmentClass === "operator_comparable"
      ? { ...(components[comparisonView.seatTargetOwnerComponentId]?.seatTargets?.monthly ?? {}) }
      : {};

  const quarterlyMqlPace = Object.fromEntries(
    Object.entries(pacing).flatMap(([quarter, packageValue]) => {
      const field = packageValue.fields.mqls_weekly;
      return typeof field?.value === "number" ? [[quarter, field.value]] : [];
    }),
  );
  const quarterlyConversionRates = {
    mqlToS0: Object.fromEntries(
      Object.entries(pacing).flatMap(([quarter, packageValue]) => {
        const field = packageValue.fields.mql_to_s0;
        return typeof field?.value === "number" ? [[quarter, field.value]] : [];
      }),
    ),
    s0ToS1: Object.fromEntries(
      Object.entries(pacing).flatMap(([quarter, packageValue]) => {
        const field = packageValue.fields.s0_to_s1;
        return typeof field?.value === "number" ? [[quarter, field.value]] : [];
      }),
    ),
    s1ToS2: Object.fromEntries(
      Object.entries(pacing).flatMap(([quarter, packageValue]) => {
        const field = packageValue.fields.s1_to_s2;
        return typeof field?.value === "number" ? [[quarter, field.value]] : [];
      }),
    ),
  };

  const comparisonQuarterly =
    comparisonView.treatmentClass === "operator_comparable" &&
    comparisonView.supportedGrains.includes("quarterly")
      ? { ...comparisonView.totals.quarterly }
      : {};
  const fyTarget =
    comparisonView.treatmentClass === "operator_comparable" &&
    comparisonView.supportedGrains.includes("annual")
      ? comparisonView.totals.annual
      : null;

  return {
    id: raw.id,
    slug: raw.id,
    schemaVersion: 2,
    name: raw.name,
    version: raw.version,
    createdDate: raw.created_date,
    source: {
      manifestId: source.manifestId ?? null,
      path: source.path ?? null,
      provenance: "plan_file",
    },
    components,
    views,
    comparisonScopeId: comparisonView.id,
    comparisonScopeLabel: comparisonView.label,
    comparison: {
      viewId: comparisonView.id,
      label: comparisonView.label,
      operatorComparable: comparisonView.treatmentClass === "operator_comparable",
      supportedGrains: comparisonView.supportedGrains,
      seatTargetOwnerComponentId: comparisonView.seatTargetOwnerComponentId,
    },
    executiveContext: {
      viewId: executiveView?.id ?? null,
      label: executiveView?.label ?? null,
      supportedGrains: executiveView?.supportedGrains ?? [],
      annualTarget: executiveView?.totals.annual ?? null,
      quarterlyTargets: executiveView ? { ...executiveView.totals.quarterly } : {},
      available: Boolean(executiveView),
    },
    targets: {
      quarterlyBookings: comparisonQuarterly,
      explicitMonthlyBookings,
      explicitMonthlyAeTargets,
      quarterEndAeTargets: quarterEndSeatTargets,
      quarterlyMqlPace,
      quarterlyConversionRates,
    },
    pacing,
    hiring: {
      entries: Array.isArray(raw.hiring_schedule) ? raw.hiring_schedule : [],
      hasExplicitMonthlySeatPath: Object.keys(explicitMonthlyAeTargets).length > 0,
    },
    assumptions: normalizeSliderDefaults(raw.slider_defaults),
    availability: {
      comparableOnOperatorPages: comparisonView.treatmentClass === "operator_comparable",
      explicitMonthlyBookings: Object.keys(explicitMonthlyBookings).length > 0,
      explicitMonthlyAeTargets: Object.keys(explicitMonthlyAeTargets).length > 0,
      quarterEndAeTargets: Object.keys(quarterEndSeatTargets).length > 0,
      quarterlyMqlPace: Object.keys(quarterlyMqlPace).length > 0,
      quarterlyConversionRates:
        Object.keys(quarterlyConversionRates.mqlToS0).length > 0 ||
        Object.keys(quarterlyConversionRates.s0ToS1).length > 0 ||
        Object.keys(quarterlyConversionRates.s1ToS2).length > 0,
      hiringSchedule: Array.isArray(raw.hiring_schedule) && raw.hiring_schedule.length > 0,
      monthlyComparable:
        comparisonView.treatmentClass === "operator_comparable" &&
        comparisonView.supportedGrains.includes("monthly"),
      quarterlyComparable:
        comparisonView.treatmentClass === "operator_comparable" &&
        comparisonView.supportedGrains.includes("quarterly"),
      annualComparable:
        comparisonView.treatmentClass === "operator_comparable" &&
        comparisonView.supportedGrains.includes("annual"),
      executiveContext: Boolean(executiveView),
    },
    forwardContext,
    fyTarget,
  };
}

function normalizeLegacyPlanPreset(
  raw: RawPlanPreset,
  source: { manifestId?: string | null; path?: string | null },
): PlanPreset {
  const slug = raw.id || source.manifestId || derivePlanId(raw.name);
  const quarterlyBookings = numericRecord(raw.quarterly_targets);
  const explicitMonthlyBookings = numericRecord(raw.monthly_targets);
  const explicitMonthlyAeTargets = numericRecord(raw.monthly_ae_targets);
  const quarterEndAeTargets = numericRecord(raw.quarter_end_ae_targets);
  const quarterlyMqlPace = numericRecord(raw.quarterly_mql_pace);
  const quarterlyConversionTargets =
    raw.quarterly_conversion_targets && typeof raw.quarterly_conversion_targets === "object"
      ? raw.quarterly_conversion_targets
      : {};

  const arrTargets: NormalizedValueFamily =
    Object.keys(explicitMonthlyBookings).length > 0
      ? {
          canonicalGrain: "monthly",
          monthly: explicitMonthlyBookings,
          quarterly: quarterlyBookings,
          annual: Object.values(quarterlyBookings).reduce((sum, value) => sum + value, 0),
        }
      : {
          canonicalGrain: "quarterly",
          monthly: {},
          quarterly: quarterlyBookings,
          annual: Object.values(quarterlyBookings).reduce((sum, value) => sum + value, 0),
        };
  const seatTargets: NormalizedSeatValueFamily | null =
    Object.keys(explicitMonthlyAeTargets).length > 0 || Object.keys(quarterEndAeTargets).length > 0
      ? {
          canonicalGrain:
            Object.keys(explicitMonthlyAeTargets).length > 0 ? "monthly" : "quarterly",
          monthly: explicitMonthlyAeTargets,
          quarterly: quarterEndAeTargets,
          annual:
            Object.keys(explicitMonthlyAeTargets).length > 0
              ? explicitMonthlyAeTargets[
                  Object.keys(explicitMonthlyAeTargets).sort((left, right) =>
                    left.localeCompare(right),
                  )[Object.keys(explicitMonthlyAeTargets).length - 1] ?? ""
                ] ?? null
              : quarterEndAeTargets[
                  Object.keys(quarterEndAeTargets).sort((left, right) =>
                    left.localeCompare(right),
                  )[Object.keys(quarterEndAeTargets).length - 1] ?? ""
                ] ?? null,
        }
      : null;
  const comparisonView: PlanView = {
    id: "legacy_default_comparison",
    label: raw.name,
    treatmentClass: "operator_comparable",
    supportedGrains: ["monthly", "quarterly", "annual"],
    componentIds: ["sales_led"],
    seatTargetOwnerComponentId: seatTargets ? "sales_led" : null,
    derived: true,
    contextKind: null,
    totals: {
      monthly: explicitMonthlyBookings,
      quarterly: quarterlyBookings,
      annual: Object.values(quarterlyBookings).reduce((sum, value) => sum + value, 0),
    },
  };

  return {
    id: slug,
    slug,
    schemaVersion: 1,
    name: raw.name,
    version: raw.version,
    createdDate: raw.created_date,
    source: {
      manifestId: source.manifestId ?? null,
      path: source.path ?? null,
      provenance: "plan_file",
    },
    components: {
      sales_led: {
        id: "sales_led",
        label: "Plan Reference",
        category: "legacy",
        modeledStatus: "scenario_modeled",
        approvalStatus: "legacy",
        basis: "legacy_flat_fields",
        asOf: raw.created_date,
        arrTargets,
        seatTargets,
      },
    },
    views: {
      legacy_default_comparison: comparisonView,
    },
    comparisonScopeId: comparisonView.id,
    comparisonScopeLabel: comparisonView.label,
    comparison: {
      viewId: comparisonView.id,
      label: comparisonView.label,
      operatorComparable: true,
      supportedGrains: comparisonView.supportedGrains,
      seatTargetOwnerComponentId: comparisonView.seatTargetOwnerComponentId,
    },
    executiveContext: {
      viewId: null,
      label: null,
      supportedGrains: [],
      annualTarget: null,
      quarterlyTargets: {},
      available: false,
    },
    targets: {
      quarterlyBookings,
      explicitMonthlyBookings,
      explicitMonthlyAeTargets,
      quarterEndAeTargets,
      quarterlyMqlPace,
      quarterlyConversionRates: {
        mqlToS0: numericRecord(quarterlyConversionTargets.mql_to_s0),
        s0ToS1: numericRecord(quarterlyConversionTargets.s0_to_s1),
        s1ToS2: numericRecord(quarterlyConversionTargets.s1_to_s2),
      },
    },
    pacing: {},
    hiring: {
      entries: Array.isArray(raw.hiring_schedule) ? raw.hiring_schedule : [],
      hasExplicitMonthlySeatPath: Object.keys(explicitMonthlyAeTargets).length > 0,
    },
    assumptions: normalizeSliderDefaults(raw.slider_defaults),
    availability: {
      comparableOnOperatorPages: true,
      explicitMonthlyBookings: Object.keys(explicitMonthlyBookings).length > 0,
      explicitMonthlyAeTargets: Object.keys(explicitMonthlyAeTargets).length > 0,
      quarterEndAeTargets: Object.keys(quarterEndAeTargets).length > 0,
      quarterlyMqlPace: Object.keys(quarterlyMqlPace).length > 0,
      quarterlyConversionRates:
        Object.keys(quarterlyConversionTargets.mql_to_s0 ?? {}).length > 0 ||
        Object.keys(quarterlyConversionTargets.s0_to_s1 ?? {}).length > 0 ||
        Object.keys(quarterlyConversionTargets.s1_to_s2 ?? {}).length > 0,
      hiringSchedule: Array.isArray(raw.hiring_schedule) && raw.hiring_schedule.length > 0,
      monthlyComparable: true,
      quarterlyComparable: Object.keys(quarterlyBookings).length > 0,
      annualComparable: Object.keys(quarterlyBookings).length > 0,
      executiveContext: false,
    },
    forwardContext: null,
    fyTarget: Object.values(quarterlyBookings).reduce((sum, value) => sum + value, 0),
  };
}

export function normalizePlanPreset(
  raw: RawPlanPreset,
  source?: { manifestId?: string | null; path?: string | null },
): PlanPreset {
  return raw.schema_version === 2
    ? normalizeV2PlanPreset(raw, source ?? {})
    : normalizeLegacyPlanPreset(raw, source ?? {});
}

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
