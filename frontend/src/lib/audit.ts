import type { Snapshot } from "../types/snapshot";

const SOURCE_LABELS: Record<string, string> = {
  registry: "Config assumption",
  blended_cohort: "Blended cohort",
  Salesforce: "Salesforce observed",
  warehouse: "warehouse observed",
  static: "Static config",
  plan: "Plan config",
  config: "Config fallback",
};

export interface AuditHealthRow {
  label: string;
  status: string;
  message: string;
}

export interface AuditSignal {
  label: string;
  source: string;
  sample: string;
  method: string;
  note: string;
}

export interface AuditException {
  label: string;
  source: string;
  detail: string;
}

export interface AuditQuarterTieoutRow {
  quarter: string;
  bookings: number;
  funnel: number;
  capacity: number;
  actuals: number;
  maxDelta: number;
  status: string;
}

export interface AuditMonthLockRow {
  month: string;
  inventoryWins: number;
  totalExpected: number;
  futureWins: number;
  status: string;
  message: string;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function humanSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function statusLabel(status: string): string {
  const value = status.trim().toLowerCase();
  if (value === "ok") return "Healthy";
  if (value === "aligned") return "Aligned";
  if (value === "diverged") return "Diverged";
  if (value === "green") return "Healthy";
  if (value === "yellow") return "Warning";
  if (value === "red") return "Critical";
  return status || "Unknown";
}

export function statusColor(status: string): "emerald" | "amber" | "red" | "slate" {
  const value = status.trim().toLowerCase();
  if (value === "green" || value === "ok" || value === "aligned") return "emerald";
  if (value === "yellow" || value === "warning") return "amber";
  if (value === "red" || value === "diverged" || value === "critical") return "red";
  return "slate";
}

export function getAuditOverallStatus(snapshot: Snapshot): string {
  const health = asRecord(snapshot.health_status);
  return asString(health.overall_status) || "unknown";
}

export function getAuditHealthRows(snapshot: Snapshot): AuditHealthRow[] {
  const health = asRecord(snapshot.health_status);
  return [
    ["freshness", "Freshness"],
    ["bookings_reconciliation", "Bookings Reconciliation"],
    ["decay_curve", "Close Timing"],
    ["targets", "Targets"],
  ].map(([key, label]) => {
    const row = asRecord(health[key]);
    return {
      label,
      status: asString(row.status) || "unknown",
      message: asString(row.message) || "\u2014",
    };
  });
}

function getProvenance(snapshot: Snapshot): Record<string, unknown> {
  return asRecord(snapshot.provenance);
}

function asQuarterRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") as Record<string, unknown>[] : [];
}

function getQuarterNumber(row: Record<string, unknown> | undefined, key: "bu_sales_led_arr" | "actual_bookings"): number {
  if (!row) return 0;

  const directValue = asNumber(row[key]);
  if (directValue !== null) return directValue;

  if (key === "bu_sales_led_arr") {
    const nestedValue = asNumber(asRecord(row.bottoms_up).sales_led_arr);
    if (nestedValue !== null) return nestedValue;
  }

  if (key === "actual_bookings") {
    const nestedValue = asNumber(asRecord(row.actuals).bookings);
    if (nestedValue !== null) return nestedValue;
  }

  return 0;
}

function formatAuditMoney(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSample(record: Record<string, unknown>): string {
  const n = asNumber(record.n);
  if (n !== null) return `n=${n.toFixed(0)}`;

  const sample = asNumber(record.sample);
  if (sample !== null) return `n=${sample.toFixed(0)}`;

  const oppCount = asNumber(record.opp_count);
  if (oppCount !== null) return `${oppCount.toFixed(0)} opps`;

  const s0Count = asNumber(record.s0_count);
  const rampedAeMonths = asNumber(record.ramped_ae_months);
  if (s0Count !== null && rampedAeMonths !== null) {
    return `${s0Count.toFixed(0)} S0 / ${rampedAeMonths.toFixed(1)} AE-months`;
  }

  const period = asRecord(record.period);
  const startDate = asString(period.start_date);
  const endDate = asString(period.end_date);
  if (startDate && endDate) return `${startDate} to ${endDate}`;

  const sampleSizes = asRecord(record.sample_sizes);
  const enterprise = asRecord(sampleSizes.enterprise);
  const qualifiedReps = asNumber(enterprise.qualified_reps);
  if (qualifiedReps !== null) return `${qualifiedReps.toFixed(0)} reps`;

  return "\u2014";
}

function formatMethod(record: Record<string, unknown>, fallback = "\u2014"): string {
  const directKeys = ["methodology", "method", "arr_basis", "metric_used", "provenance"];
  for (const key of directKeys) {
    const value = asString(record[key]);
    if (value) return value;
  }

  const source = asString(record.source);
  if (source === "warehouse" && asString(record.warehouse_table)) {
    return asString(record.warehouse_table);
  }

  return fallback;
}

function formatNote(record: Record<string, unknown>): string {
  const directKeys = ["warning", "reason", "note"];
  for (const key of directKeys) {
    const value = asString(record[key]);
    if (value) return value;
  }

  const minimumSample = asNumber(record.minimum_sample);
  const sampleQuality = asString(record.sample_quality);
  if (minimumSample !== null || sampleQuality) {
    const parts = [];
    if (minimumSample !== null) parts.push(`min=${minimumSample.toFixed(0)}`);
    if (sampleQuality) parts.push(sampleQuality);
    return parts.join(", ");
  }

  const qualifyingMonths = asNumber(record.qualifying_months);
  if (qualifyingMonths !== null) return `${qualifyingMonths.toFixed(0)} qualifying months`;

  return "\u2014";
}

export function buildCriticalSignals(snapshot: Snapshot): AuditSignal[] {
  const provenance = getProvenance(snapshot);
  const funnelRates = asRecord(provenance.funnel_rates);
  const signalRows: Array<[string, Record<string, unknown>]> = [
    ["Beginning ARR", asRecord(provenance.beginning_arr)],
    ["Bookings Summary", asRecord(provenance.bookings_summary)],
    ["ARR Movements", asRecord(provenance.arr_movements)],
    ["Pipeline Inventory", asRecord(provenance.pipeline)],
    ["Roster", asRecord(provenance.roster)],
    ["AE Productivity", asRecord(provenance.observed_productivity)],
    ["AE Ramp Curve", asRecord(provenance.observed_ramp_curve)],
    ["Trailing MQL Signal", asRecord(provenance.trailing_mql_signal)],
    ["Close Timing Curve", asRecord(provenance.decay_curve)],
    ["S2 to Won", asRecord(provenance.s2_to_won)],
    ["MQL to S0", asRecord(funnelRates.mql_to_s0)],
    ["S0 to S1", asRecord(funnelRates.s0_to_s1)],
    ["S1 to S2", asRecord(funnelRates.s1_to_s2)],
  ];

  return signalRows.map(([label, record]) => {
    const source = asString(record.source) || "unknown";
    return {
      label,
      source: humanSourceLabel(source),
      sample: formatSample(record),
      method: formatMethod(record),
      note: formatNote(record),
    };
  });
}

export function buildQuarterTieoutRows(snapshot: Snapshot): AuditQuarterTieoutRow[] {
  const bookingsRows = asQuarterRows(snapshot.model_output.bookings_bridge.trajectory_quarters);
  const funnelRows = asQuarterRows(snapshot.model_output.funnel_health.trajectory_quarters);
  const capacityRows = asQuarterRows(snapshot.model_output.capacity_headcount.trajectory_quarters);

  return bookingsRows.map((bookingsRow) => {
    const quarter = asString(bookingsRow.quarter) || "Unknown";
    const funnelRow = funnelRows.find((row) => asString(row.quarter) === quarter);
    const capacityRow = capacityRows.find((row) => asString(row.quarter) === quarter);
    const bookings = getQuarterNumber(bookingsRow, "bu_sales_led_arr");
    const funnel = getQuarterNumber(funnelRow, "bu_sales_led_arr");
    const capacity = getQuarterNumber(capacityRow, "bu_sales_led_arr");
    const actuals = getQuarterNumber(bookingsRow, "actual_bookings");
    const maxDelta = Math.max(
      Math.abs(bookings - funnel),
      Math.abs(bookings - capacity),
      Math.abs(funnel - capacity)
    );

    return {
      quarter,
      bookings,
      funnel,
      capacity,
      actuals,
      maxDelta,
      status: maxDelta <= 1 ? "green" : "red",
    };
  });
}

export function buildActualMonthLockRows(snapshot: Snapshot): AuditMonthLockRow[] {
  const bb = snapshot.scenario_building_blocks;

  return bb.months
    .map((month, index) => {
      const inventoryWins = bb.monthly_inventory_wins[index] ?? 0;
      const totalExpected = bb.monthly_total_expected[index] ?? 0;
      const futureWins = bb.monthly_future_wins[index] ?? 0;
      const matchesActual = Math.abs(totalExpected - inventoryWins) <= 1;
      const futureSuppressed = Math.abs(futureWins) <= 1;
      let message = "Actual month locked to closed bookings with future wins suppressed.";
      if (!matchesActual && !futureSuppressed) {
        message = "Actual month is not locked and still includes projected future wins.";
      } else if (!matchesActual) {
        message = "Actual month total expected does not match closed bookings.";
      } else if (!futureSuppressed) {
        message = "Actual month still includes projected future wins.";
      }

      return {
        month,
        inventoryWins,
        totalExpected,
        futureWins,
        status: matchesActual && futureSuppressed ? "green" : "red",
        message,
      };
    })
    .filter((_, index) => bb.monthly_is_actual[index]);
}

function isConfigLike(source: string): boolean {
  const value = source.trim().toLowerCase();
  return value === "config" || value === "registry" || value === "static" || value === "plan";
}

export function buildFallbackExceptions(snapshot: Snapshot): AuditException[] {
  const provenance = getProvenance(snapshot);
  const exceptions: AuditException[] = [];

  const criticalKeys: Array<[string, Record<string, unknown>]> = [
    ["Beginning ARR", asRecord(provenance.beginning_arr)],
    ["Bookings Summary", asRecord(provenance.bookings_summary)],
    ["ARR Movements", asRecord(provenance.arr_movements)],
    ["Pipeline Inventory", asRecord(provenance.pipeline)],
    ["Roster", asRecord(provenance.roster)],
    ["AE Productivity", asRecord(provenance.observed_productivity)],
    ["AE Ramp Curve", asRecord(provenance.observed_ramp_curve)],
    ["Trailing MQL Signal", asRecord(provenance.trailing_mql_signal)],
    ["Close Timing Curve", asRecord(provenance.decay_curve)],
    ["S2 to Won", asRecord(provenance.s2_to_won)],
  ];

  for (const [label, record] of criticalKeys) {
    const source = asString(record.source);
    if (isConfigLike(source)) {
      exceptions.push({
        label,
        source: humanSourceLabel(source),
        detail: formatNote(record),
      });
    }
  }

  const funnelRates = asRecord(provenance.funnel_rates);
  for (const key of ["mql_to_s0", "s0_to_s1", "s1_to_s2"]) {
    const record = asRecord(funnelRates[key]);
    const source = asString(record.source);
    if (isConfigLike(source)) {
      exceptions.push({
        label: key,
        source: humanSourceLabel(source),
        detail: formatMethod(record, formatNote(record)),
      });
    }
  }

  return exceptions;
}

export function buildAcceptedScopeExclusions(snapshot: Snapshot): AuditException[] {
  const provenance = getProvenance(snapshot);
  const funnelRates = asRecord(provenance.funnel_rates);
  const exclusions: AuditException[] = [];

  for (const [label, candidateKeys] of [
    ["plg_signup_to_pql", ["plg_signup_to_pql"]],
    ["plg_pql_to_s1", ["plg_pql_to_s1", "plg_pql_to_s0"]],
  ] as const) {
    const record = candidateKeys
      .map((key) => asRecord(funnelRates[key]))
      .find((entry) => Object.keys(entry).length > 0) ?? {};
    const source = asString(record.source);
    if (!isConfigLike(source)) continue;

    exclusions.push({
      label,
      source: humanSourceLabel(source),
      detail: formatMethod(record, formatNote(record)),
    });
  }

  return exclusions;
}

export function buildInactiveFallbackDebt(snapshot: Snapshot): AuditException[] {
  const decayHealth = asRecord(asRecord(snapshot.health_status).decay_curve);
  const activeSource = asString(decayHealth.source);
  const fallbackValidation = asRecord(decayHealth.fallback_validation);

  if (
    !Object.keys(fallbackValidation).length ||
    (activeSource !== "Salesforce" && activeSource !== "warehouse")
  ) {
    return [];
  }

  return [
    {
      label: "Config close timing fallback",
      source: "Inactive fallback debt",
      detail:
        asString(fallbackValidation.message) ||
        "Observed runtime path is active; config fallback validation is tracked separately.",
    },
  ];
}

export function buildAuditReportText(snapshot: Snapshot): string {
  const lines: string[] = [];
  const overall = statusLabel(getAuditOverallStatus(snapshot));
  const healthRows = getAuditHealthRows(snapshot);
  const criticalSignals = buildCriticalSignals(snapshot);
  const exceptions = buildFallbackExceptions(snapshot);
  const acceptedScopeExclusions = buildAcceptedScopeExclusions(snapshot);
  const inactiveFallbackDebt = buildInactiveFallbackDebt(snapshot);
  const quarterTieoutRows = buildQuarterTieoutRows(snapshot);
  const monthLockRows = buildActualMonthLockRows(snapshot);

  lines.push("Forecast Tieout Finance Audit Report");
  lines.push("=".repeat(40));
  lines.push(`Snapshot as_of: ${snapshot.as_of}`);
  lines.push(`Generated at: ${snapshot.generated_at}`);
  lines.push(`Git SHA: ${snapshot.git_sha}`);
  lines.push(`Overall status: ${overall}`);
  lines.push("");
  lines.push("Health Checks");
  lines.push("-".repeat(40));
  for (const row of healthRows) {
    lines.push(`${row.label}: ${statusLabel(row.status)} — ${row.message}`);
  }
  lines.push("");
  lines.push("Critical Signal Ledger");
  lines.push("-".repeat(40));
  for (const row of criticalSignals) {
    lines.push(`${row.label}: ${row.source} | sample=${row.sample} | method=${row.method} | note=${row.note}`);
  }
  lines.push("");
  lines.push("Fallback Exceptions");
  lines.push("-".repeat(40));
  if (exceptions.length === 0) {
    lines.push("None");
  } else {
    for (const row of exceptions) {
      lines.push(`${row.label}: ${row.source} | ${row.detail}`);
    }
  }
  lines.push("");
  lines.push("Accepted Scope Exclusions");
  lines.push("-".repeat(40));
  if (acceptedScopeExclusions.length === 0) {
    lines.push("None");
  } else {
    for (const row of acceptedScopeExclusions) {
      lines.push(`${row.label}: ${row.source} | ${row.detail}`);
    }
  }
  lines.push("");
  lines.push("Inactive Fallback Debt");
  lines.push("-".repeat(40));
  if (inactiveFallbackDebt.length === 0) {
    lines.push("None");
  } else {
    for (const row of inactiveFallbackDebt) {
      lines.push(`${row.label}: ${row.source} | ${row.detail}`);
    }
  }
  lines.push("");
  lines.push("Quarter Tie-Out");
  lines.push("-".repeat(40));
  for (const row of quarterTieoutRows) {
    lines.push(
      `${row.quarter}: bookings=${formatAuditMoney(row.bookings)} | funnel=${formatAuditMoney(row.funnel)} | capacity=${formatAuditMoney(row.capacity)} | actuals=${formatAuditMoney(row.actuals)} | max_delta=${formatAuditMoney(row.maxDelta)} | status=${statusLabel(row.status)}`
    );
  }
  lines.push("");
  lines.push("Actual Month Locks");
  lines.push("-".repeat(40));
  for (const row of monthLockRows) {
    lines.push(
      `${row.month}: inventory=${formatAuditMoney(row.inventoryWins)} | total_expected=${formatAuditMoney(row.totalExpected)} | future_wins=${formatAuditMoney(row.futureWins)} | status=${statusLabel(row.status)} | ${row.message}`
    );
  }
  return lines.join("\n");
}
