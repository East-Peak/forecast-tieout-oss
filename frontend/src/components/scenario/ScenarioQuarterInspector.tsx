import { useEffect, useState } from "react";
import { Badge, Card, Text } from "../ui";
import type {
  ScenarioQuarterKey,
  ScenarioQuarterOverride,
} from "../../engine/scenario";
import type {
  QuarterPlanReference,
  ScalarOverrideFieldKey,
} from "../../lib/scenarioPlanner";
import {
  OVERRIDE_FIELDS,
  clampValue,
  formatCountInput,
  formatCurrencyInput,
  formatMoney,
  formatPercentInput,
  formatSignedMoney,
  formatWeeklyInput,
  formatWeeklyVolume,
} from "../../lib/scenarioPlanner";
import type { ResolvedPlanPacingProvenance } from "../../lib/plans";

interface Props {
  quarter: ScenarioQuarterKey;
  monthRange: string;
  override: ScenarioQuarterOverride;
  baseline: ScenarioQuarterOverride;
  mode: "baseline" | "override";
  monthLabels: string[];
  savedAeTargets: number[];
  seatTargets: number[];
  planAeMonthTargets: Array<number | null>;
  savedQuarterBookings: number;
  planQuarterBookings: number | null;
  planAeTarget: number | null;
  savedMqlWeekly: number | null;
  planMqlWeekly: number | null;
  scenarioMqlWeekly: number | null;
  scenarioQuarterBookings: number;
  scenarioGapToPlan: number | null;
  planReference: QuarterPlanReference;
  onChange: (field: ScalarOverrideFieldKey, value: number) => void;
  onAeTargetChange: (monthOffset: number, value: number) => void;
  onMqlWeeklyChange: (value: number) => void;
  onResetQuarter: () => void;
  onCopyAssumptionsForward: (() => void) | null;
}

function formatOverrideInputValue(field: (typeof OVERRIDE_FIELDS)[number], value: number): string {
  switch (field.inputKind) {
    case "percent":
      return formatPercentInput(value);
    case "currency":
      return formatCurrencyInput(value);
    case "count":
    default:
      return formatCountInput(value);
  }
}

function parseOverrideInputValue(
  field: (typeof OVERRIDE_FIELDS)[number],
  value: string,
): number | null {
  const normalized = value.replace(/[$,%\s]/g, "").replace(/,/g, "");
  if (
    normalized.length === 0 ||
    normalized === "-" ||
    normalized === "+" ||
    normalized === "." ||
    normalized === "-." ||
    normalized === "+."
  ) {
    return null;
  }

  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return null;

  const scaled = field.inputKind === "percent" ? parsed / 100 : parsed;
  const clamped = clampValue(scaled, field.min, field.max);

  if (field.inputKind === "count" || field.inputKind === "currency") {
    return Math.round(clamped);
  }

  return clamped;
}

function parseWholeNumberInput(value: string): number | null {
  const normalized = value.replace(/[,\s]/g, "");
  if (
    normalized.length === 0 ||
    normalized === "-" ||
    normalized === "+" ||
    normalized === "." ||
    normalized === "-." ||
    normalized === "+."
  ) {
    return null;
  }

  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.round(parsed));
}

function buildDraftValues(
  override: ScenarioQuarterOverride,
): Record<ScalarOverrideFieldKey, string> {
  return {
    mqlToS0: formatOverrideInputValue(OVERRIDE_FIELDS[0], override.mqlToS0),
    s0ToS1: formatOverrideInputValue(OVERRIDE_FIELDS[1], override.s0ToS1),
    s1ToS2: formatOverrideInputValue(OVERRIDE_FIELDS[2], override.s1ToS2),
    avgDealSize: formatOverrideInputValue(OVERRIDE_FIELDS[3], override.avgDealSize),
  };
}

function renderProvenanceBadges(
  provenance: ResolvedPlanPacingProvenance | null,
){
  if (!provenance) return null;
  const badges: Array<ResolvedPlanPacingProvenance["presentationState"] | "stale"> = [
    provenance.presentationState,
  ];
  if (provenance.stale) badges.push("stale");
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((badge) => (
        <span
          key={badge}
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
            badge === "approved"
              ? "bg-emerald-50 text-emerald-700"
              : badge === "fallback"
                ? "bg-blue-50 text-blue-700"
                : badge === "stale"
                  ? "bg-amber-50 text-amber-700"
                  : "bg-slate-100 text-slate-600"
          }`}
        >
          {badge === "approved"
            ? "Approved"
            : badge === "fallback"
              ? "Fallback"
              : badge === "stale"
                ? "Stale"
                : "Provisional"}
        </span>
      ))}
    </div>
  );
}

export function ScenarioQuarterInspector({
  quarter,
  monthRange,
  override,
  baseline,
  mode,
  monthLabels,
  savedAeTargets,
  seatTargets,
  planAeMonthTargets,
  savedQuarterBookings,
  planQuarterBookings,
  planAeTarget,
  savedMqlWeekly,
  planMqlWeekly,
  scenarioMqlWeekly,
  scenarioQuarterBookings,
  scenarioGapToPlan,
  planReference,
  onChange,
  onAeTargetChange,
  onMqlWeeklyChange,
  onResetQuarter,
  onCopyAssumptionsForward,
}: Props) {
  const [draftValues, setDraftValues] = useState<Record<ScalarOverrideFieldKey, string>>(
    () => buildDraftValues(override),
  );
  const [draftAeTargets, setDraftAeTargets] = useState<string[]>(() =>
    seatTargets.map((value) => formatCountInput(value)),
  );
  const [draftMqlWeekly, setDraftMqlWeekly] = useState<string>(() =>
    formatWeeklyInput(scenarioMqlWeekly ?? savedMqlWeekly ?? 0),
  );

  useEffect(() => {
    setDraftValues(buildDraftValues(override));
  }, [override]);

  useEffect(() => {
    setDraftAeTargets(seatTargets.map((value) => formatCountInput(value)));
  }, [seatTargets]);

  useEffect(() => {
    setDraftMqlWeekly(formatWeeklyInput(scenarioMqlWeekly ?? savedMqlWeekly ?? 0));
  }, [savedMqlWeekly, scenarioMqlWeekly]);

  const mqlOverrideChanged =
    savedMqlWeekly !== null &&
    scenarioMqlWeekly !== null &&
    Math.abs(scenarioMqlWeekly - savedMqlWeekly) > 0.5;
  const hasPlanAeMonthTargets = planAeMonthTargets.some((value) => value !== null);

  function commitFieldValue(field: (typeof OVERRIDE_FIELDS)[number]): void {
    const parsed = parseOverrideInputValue(field, draftValues[field.key]);
    const nextValue = parsed ?? override[field.key];
    onChange(field.key, nextValue);
    setDraftValues((current) => ({
      ...current,
      [field.key]: formatOverrideInputValue(field, nextValue),
    }));
  }

  function commitAeTarget(monthOffset: number): void {
    const rawValue = draftAeTargets[monthOffset] ?? "";
    const fallback = seatTargets[monthOffset] ?? savedAeTargets[monthOffset] ?? 0;
    const parsed = parseWholeNumberInput(rawValue);
    const nextValue = parsed ?? fallback;

    onAeTargetChange(monthOffset, nextValue);
    setDraftAeTargets((current) =>
      current.map((value, index) => (index === monthOffset ? formatCountInput(nextValue) : value)),
    );
  }

  function commitMqlWeekly(): void {
    const fallback = scenarioMqlWeekly ?? savedMqlWeekly ?? 0;
    const parsed = parseWholeNumberInput(draftMqlWeekly);
    const nextValue = parsed ?? Math.round(fallback);
    onMqlWeeklyChange(nextValue);
    setDraftMqlWeekly(formatWeeklyInput(nextValue));
  }

  return (
    <Card className="overflow-hidden border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-[linear-gradient(135deg,rgba(248,250,252,0.97),rgba(239,246,255,0.92))] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{quarter} Scenario Inputs</h3>
            <p className="text-xs text-slate-500">{monthRange} operating window</p>
          </div>
          <Badge color={mode === "override" ? "blue" : "gray"}>
            {mode === "override" ? "Scenario Override" : "Baseline"}
          </Badge>
        </div>

        <div className="mt-4 rounded-2xl border border-white/80 bg-white/90 p-3 shadow-sm">
          <div className="grid gap-2">
            <div className="rounded-2xl border border-slate-200 bg-slate-50/85 p-3.5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <Text className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  Baseline
                </Text>
                <Text className="text-2xl font-semibold tracking-tight text-slate-900">
                  {formatMoney(savedQuarterBookings)}
                </Text>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-xl bg-white/90 px-3 py-2">
                  <Text className="text-[10px] uppercase tracking-wide text-slate-500">AE Seats</Text>
                  <Text className="mt-1 text-sm font-semibold text-slate-900">
                    {formatCountInput(savedAeTargets[savedAeTargets.length - 1] ?? 0)}
                  </Text>
                </div>
                <div className="rounded-xl bg-white/90 px-3 py-2">
                  <Text className="text-[10px] uppercase tracking-wide text-slate-500">MQLs / Wk</Text>
                  <Text className="mt-1 text-sm font-semibold text-slate-900">
                    {savedMqlWeekly === null ? "\u2014" : formatWeeklyVolume(savedMqlWeekly)}
                  </Text>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-red-100 bg-red-50/75 p-3.5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <Text className="text-[11px] font-semibold uppercase tracking-[0.18em] text-red-700">
                  Target / Reference
                </Text>
                <Text className="text-2xl font-semibold tracking-tight text-slate-900">
                  {planReference.comparable &&
                  planReference.quarterlySupported &&
                  planQuarterBookings !== null
                    ? formatMoney(planQuarterBookings)
                    : "\u2014"}
                </Text>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-xl bg-white/90 px-3 py-2">
                  <Text className="text-[10px] uppercase tracking-wide text-slate-500">AE Goal</Text>
                  <Text className="mt-1 text-sm font-semibold text-slate-900">
                    {planAeTarget === null ? "\u2014" : formatCountInput(planAeTarget)}
                  </Text>
                </div>
                <div className="rounded-xl bg-white/90 px-3 py-2">
                  <Text className="text-[10px] uppercase tracking-wide text-slate-500">MQL Pace</Text>
                  <Text className="mt-1 text-sm font-semibold text-slate-900">
                    {planMqlWeekly === null ? "\u2014" : formatWeeklyVolume(planMqlWeekly)}
                  </Text>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-blue-100 bg-blue-50/75 p-3.5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <Text className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-700">
                  Scenario
                </Text>
                <Text className="text-2xl font-semibold tracking-tight text-slate-900">
                  {formatMoney(scenarioQuarterBookings)}
                </Text>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-xl bg-white/90 px-3 py-2">
                  <Text className="text-[10px] uppercase tracking-wide text-slate-500">Gap To Plan</Text>
                  <Text
                    className={`mt-1 text-sm font-semibold ${
                      scenarioGapToPlan === null
                        ? "text-slate-500"
                        : scenarioGapToPlan >= 0
                          ? "text-emerald-700"
                          : "text-red-700"
                    }`}
                  >
                    {scenarioGapToPlan === null ? "\u2014" : formatSignedMoney(scenarioGapToPlan)}
                  </Text>
                </div>
                <div className="rounded-xl bg-white/90 px-3 py-2">
                  <Text className="text-[10px] uppercase tracking-wide text-slate-500">MQLs / Wk</Text>
                  <Text className="mt-1 text-sm font-semibold text-slate-900">
                    {scenarioMqlWeekly === null ? "\u2014" : formatWeeklyVolume(scenarioMqlWeekly)}
                  </Text>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {planReference.note ? (
        <div className="mx-5 mt-4 rounded-2xl border border-amber-200 bg-amber-50/85 p-3.5 shadow-sm">
          <Text className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-700">
            Planning Note
          </Text>
          <Text className="mt-1 text-[11px] leading-5 text-amber-900/80">{planReference.note}</Text>
        </div>
      ) : null}

      <div className="mx-5 mt-4 grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          onClick={onResetQuarter}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
        >
          Reset {quarter}
        </button>
        {onCopyAssumptionsForward ? (
          <button
            type="button"
            onClick={onCopyAssumptionsForward}
            className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2.5 text-xs font-medium text-blue-700 transition hover:border-blue-300 hover:bg-blue-100"
          >
            Apply assumptions forward
          </button>
        ) : null}
      </div>

      <div className="mx-5 mt-4 grid gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
              AE Seat Path
            </h4>
            <p className="text-[11px] leading-4 text-slate-500">
              Monthly AE totals are modeled at month grain. Earlier-month hires carry forward into
              later months.
            </p>
          </div>
          <span className="text-[11px] text-slate-500">
            {planReference.quarterlySupported && planAeTarget !== null
              ? `Plan quarter-end ${formatCountInput(planAeTarget)}`
              : "No renderable plan seat target"}
          </span>
        </div>
        <Text className="text-[11px] leading-4 text-slate-500">
          {!planReference.comparable
            ? "The selected plan has no operator-comparable view, so seat references are intentionally suppressed here."
            : !planReference.quarterlySupported
              ? "The selected comparable view does not support quarterly seat references, so this inspector keeps scenario seat edits but suppresses plan-owned seat targets."
              : hasPlanAeMonthTargets
            ? "The selected plan includes a month-by-month AE seat path for this quarter. Use it as the staffing reference while keeping scenario seat timing explicit."
            : "The selected plan currently provides a quarter-end AE target, not a month-by-month seat path. Monthly staffing timing remains scenario-defined until a richer hiring schedule is loaded."}
        </Text>

        <div className="grid gap-3">
          {monthLabels.map((label, monthOffset) => {
            const inputId = `${quarter}-ae-target-${monthOffset}`;
            const seatDelta =
              (seatTargets[monthOffset] ?? 0) - (savedAeTargets[monthOffset] ?? 0);
            return (
              <div
                key={inputId}
                className={`grid min-w-0 gap-3 rounded-xl border bg-white p-3 transition sm:grid-cols-[minmax(0,1fr)_132px] ${
                  Math.abs(seatDelta) > 0.5
                    ? "border-blue-200 shadow-sm ring-1 ring-blue-100"
                    : "border-slate-200"
                }`}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-800">{label}</span>
                    {Math.abs(seatDelta) > 0.5 ? (
                      <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                        Override {seatDelta > 0 ? "+" : ""}
                        {formatCountInput(seatDelta)}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                        Baseline
                      </span>
                    )}
                  </div>
                  <span className="mt-1 block text-[12px] text-slate-500">
                    Baseline {formatCountInput(savedAeTargets[monthOffset] ?? 0)} AEs
                  </span>
                  {planAeMonthTargets[monthOffset] !== null ? (
                    <span className="mt-1 block text-[12px] text-red-600">
                      Plan {formatCountInput(planAeMonthTargets[monthOffset] ?? 0)} AEs
                    </span>
                  ) : null}
                  <span className="mt-2 block text-[11px] leading-4 text-slate-500">
                    End-of-month seat target for this month.
                  </span>
                </div>
                <div className="min-w-0">
                  <label
                    htmlFor={inputId}
                    className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                  >
                    Scenario Seats
                  </label>
                  <input
                    id={inputId}
                    name={inputId}
                    type="text"
                    inputMode="numeric"
                    value={draftAeTargets[monthOffset] ?? ""}
                    onChange={(event) =>
                      setDraftAeTargets((current) =>
                        current.map((value, index) =>
                          index === monthOffset ? event.target.value : value,
                        ),
                      )
                    }
                    onBlur={() => commitAeTarget(monthOffset)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter") return;
                      event.currentTarget.blur();
                    }}
                    className="w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm tabular-nums text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mx-5 mt-4 mb-5 grid gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
            Demand, Conversion, and Economics
          </h4>
          <p className="mt-1 text-[11px] leading-4 text-slate-500">
            Baseline values come from the saved snapshot trajectory. Enter a new number to create
            an override for this quarter, or use the copy action above to carry the same operating
            bet into later quarters.
          </p>
        </div>

        <label
          htmlFor={`${quarter}-mql-weekly`}
          className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="text-xs font-semibold text-slate-800">Marketing MQLs / Week</span>
              <span className="mt-1 block text-[11px] leading-4 text-slate-500">
                Quarterly demand pace before MQL-to-S0 conversion.
              </span>
            </div>
            {mqlOverrideChanged ? (
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                Override
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex w-fit items-center rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
              Baseline {formatWeeklyVolume(savedMqlWeekly ?? 0)}
            </span>
            {planMqlWeekly !== null ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex w-fit items-center rounded-full bg-red-50 px-2.5 py-1 text-[11px] font-medium text-red-700">
                  Plan reference {formatWeeklyVolume(planMqlWeekly)}
                </span>
                {renderProvenanceBadges(planReference.provenance.mqlWeekly)}
              </div>
            ) : null}
          </div>
          <div className="relative">
            <input
              id={`${quarter}-mql-weekly`}
              name={`${quarter}-mql-weekly`}
              type="text"
              inputMode="numeric"
              value={draftMqlWeekly}
              onChange={(event) => setDraftMqlWeekly(event.target.value)}
              onBlur={commitMqlWeekly}
              onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                event.currentTarget.blur();
              }}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2.5 text-base font-medium tabular-nums text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <span className="text-[11px] leading-4 text-slate-500">
            Edit this to test a demand override for the active quarter.
          </span>
        </label>

        <div className="grid gap-3 md:grid-cols-2">
          {OVERRIDE_FIELDS.map((field) => {
            const inputId = `${quarter}-${field.key}`;
            const adornment =
              field.inputKind === "percent" ? "%" : field.inputKind === "currency" ? "$" : null;
            const planValue = planReference[field.key];
            const isOverridden = Math.abs(override[field.key] - baseline[field.key]) > 1e-9;
            return (
              <label
                key={field.key}
                htmlFor={inputId}
                className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-xs font-semibold text-slate-800">{field.label}</span>
                    <span className="mt-1 block text-[11px] leading-4 text-slate-500">
                      {field.help}
                    </span>
                  </div>
                  {isOverridden ? (
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                      Override
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="inline-flex w-fit items-center rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
                    Baseline {field.format(baseline[field.key])}
                  </span>
                  {typeof planValue === "number" ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex w-fit items-center rounded-full bg-red-50 px-2.5 py-1 text-[11px] font-medium text-red-700">
                        Plan reference {field.format(planValue)}
                      </span>
                      {renderProvenanceBadges(
                        field.key === "mqlToS0"
                          ? planReference.provenance.mqlToS0
                          : field.key === "s0ToS1"
                            ? planReference.provenance.s0ToS1
                            : field.key === "s1ToS2"
                              ? planReference.provenance.s1ToS2
                              : null,
                      )}
                    </div>
                  ) : null}
                </div>
                <div className="relative">
                  {adornment ? (
                    <span
                      className={`pointer-events-none absolute top-1/2 -translate-y-1/2 text-sm text-slate-400 ${
                        field.inputKind === "currency" ? "left-3" : "right-3"
                      }`}
                    >
                      {adornment}
                    </span>
                  ) : null}
                  <input
                    id={inputId}
                    name={inputId}
                    type="text"
                    inputMode={
                      field.inputKind === "count" || field.inputKind === "currency"
                        ? "numeric"
                        : "decimal"
                    }
                    value={draftValues[field.key]}
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      setDraftValues((current) => ({
                        ...current,
                        [field.key]: nextValue,
                      }));
                    }}
                    onBlur={() => commitFieldValue(field)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter") return;
                      event.currentTarget.blur();
                    }}
                    aria-describedby={`${inputId}-help`}
                    placeholder={formatOverrideInputValue(field, baseline[field.key])}
                    className={`w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2.5 text-base font-medium tabular-nums text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 ${
                      field.inputKind === "currency"
                        ? "pl-8 pr-3"
                        : field.inputKind === "percent"
                          ? "pl-3 pr-8"
                          : "px-3"
                    }`}
                  />
                </div>
                <span id={`${inputId}-help`} className="text-[11px] leading-4 text-slate-500">
                  Enter a new number to create a quarter-specific override.
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
