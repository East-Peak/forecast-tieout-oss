import { useEffect, useMemo, useState } from "react";
import { MetricStrip } from "../components/workbook";
import type { MetricItem } from "../components/workbook";
import { ScenarioForecastCharts } from "../components/scenario/ScenarioForecastCharts";
import { ScenarioPlannerHeader } from "../components/scenario/ScenarioPlannerHeader";
import { ScenarioQuarterFocus } from "../components/scenario/ScenarioQuarterFocus";
import { ScenarioQuarterInspector } from "../components/scenario/ScenarioQuarterInspector";
import { ScenarioSummaryTables } from "../components/scenario/ScenarioSummaryTables";
import { Text } from "../components/ui";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import {
  applyAeSeatTargetEdit,
  buildDefaultScenarioOverrides,
  cloneScenarioOverrides,
  computeScenario,
  getOverridableQuarters,
  hasQuarterOverride,
} from "../engine/scenario";
import type { ScenarioOverrides, ScenarioQuarterKey } from "../engine/scenario";
import { formatMonthLabel } from "../lib/format";
import {
  buildPlanMonthlyReference,
  getCurrentDateInTimeZone,
  getPlanFyTarget,
  getPlanQuarterTarget,
} from "../lib/plans";
import {
  copyQuarterAssumptionsForward,
  cumulative,
  formatMoney,
  formatSavedDelta,
  formatSignedMoney,
  getQuarterMarketingMqlWeekly,
  getQuarterPlanReference,
  quarterMonthRange,
  resetQuarterOverrides,
  sumQuarter,
  type ScenarioQuarterSummaryRow,
} from "../lib/scenarioPlanner";

export default function ScenarioPlanner() {
  const {
    snapshot,
    selectedOrgProfile,
    selectedPlan: plan,
    planSelectionNotice,
  } = usePlanningSessionContext();

  // --- Local scenario state (discarded on navigation away) ---
  const baselineOverrides = useMemo(
    () => buildDefaultScenarioOverrides(snapshot),
    [snapshot],
  );
  const [overrides, setOverrides] = useState<ScenarioOverrides>(() =>
    cloneScenarioOverrides(buildDefaultScenarioOverrides(snapshot)),
  );

  // Reset overrides when snapshot changes
  useEffect(() => {
    setOverrides(cloneScenarioOverrides(buildDefaultScenarioOverrides(snapshot)));
  }, [snapshot]);

  const baselineResult = useMemo(
    () => computeScenario(snapshot, baselineOverrides),
    [snapshot, baselineOverrides],
  );
  const result = useMemo(
    () => computeScenario(snapshot, overrides),
    [snapshot, overrides],
  );

  const overridableQuarters = useMemo(
    () => getOverridableQuarters(snapshot),
    [snapshot],
  );
  const defaultActiveQuarter = overridableQuarters[0] ?? "";

  const [activeQuarter, setActiveQuarter] = useState<ScenarioQuarterKey>(defaultActiveQuarter);
  const [shareStatus, setShareStatus] = useState<"idle" | "copied" | "error">("idle");

  useEffect(() => {
    setActiveQuarter(defaultActiveQuarter);
  }, [snapshot, defaultActiveQuarter]);

  useEffect(() => {
    if (shareStatus === "idle") return;
    const timer = window.setTimeout(() => setShareStatus("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [shareStatus]);

  function onOverridesChange(
    next: ScenarioOverrides | ((current: ScenarioOverrides) => ScenarioOverrides),
  ) {
    setOverrides((current) =>
      typeof next === "function" ? next(current) : next,
    );
  }

  const bb = snapshot.scenario_building_blocks;
  const months = bb.months;
  const actualFlags = bb.monthly_is_actual;
  const firstProjectedIndex = actualFlags.findIndex((value) => !value);
  const firstProjectedLabel =
    firstProjectedIndex === -1 ? "All months locked" : formatMonthLabel(months[firstProjectedIndex]);

  const planMonthlyReference = buildPlanMonthlyReference(months, plan);
  const planMonthly = planMonthlyReference.values;
  const planCumulative = cumulative(planMonthly);
  const planFyTotal = getPlanFyTarget(plan);
  const comparablePlanActive = plan?.availability.comparableOnOperatorPages ?? false;
  const comparableQuarterly = plan?.availability.quarterlyComparable ?? false;
  const showComparableMonthlyRail =
    planMonthlyReference.basis === "explicit_monthly_plan" ||
    planMonthlyReference.basis === "derived_even_quarter_split" ||
    planMonthlyReference.basis === "mixed";
  const evaluationAsOf = getCurrentDateInTimeZone(
    typeof selectedOrgProfile?.metadata.timezone === "string"
      ? selectedOrgProfile.metadata.timezone
      : undefined,
  );

  const cappedDelta = result.fy_capped - baselineResult.fy_capped;
  const gapToPlan =
    comparablePlanActive && typeof planFyTotal === "number"
      ? result.fy_capped - planFyTotal
      : null;
  const baselineGapToPlan =
    comparablePlanActive && typeof planFyTotal === "number"
      ? baselineResult.fy_capped - planFyTotal
      : null;
  const gapClosureDelta =
    gapToPlan !== null && baselineGapToPlan !== null ? gapToPlan - baselineGapToPlan : null;
  const addedAes = Math.max(
    0,
    Math.round(
      (result.monthly_ae_count[result.monthly_ae_count.length - 1] ?? 0) -
        (baselineResult.monthly_ae_count[baselineResult.monthly_ae_count.length - 1] ?? 0),
    ),
  );

  const funnelQuarterLookup = Object.fromEntries(
    snapshot.model_output.funnel_health.trajectory_quarters.map((row) => [row.quarter, row]),
  );
  const quarterReferenceLookup = Object.fromEntries(
    overridableQuarters.map((quarter) => {
      const quarterRow =
        typeof funnelQuarterLookup[quarter] === "object" && funnelQuarterLookup[quarter] !== null
          ? (funnelQuarterLookup[quarter] as Record<string, unknown>)
          : undefined;
      return [
        quarter,
        getQuarterPlanReference(quarter, quarterRow, plan, {
          snapshotAsOf: snapshot.as_of,
          evaluationAsOf,
          timeZone:
            typeof selectedOrgProfile?.metadata.timezone === "string"
              ? selectedOrgProfile.metadata.timezone
              : undefined,
        }),
      ];
    }),
  ) as Record<ScenarioQuarterKey, ReturnType<typeof getQuarterPlanReference>>;
  const savedMqlWeeklyLookup = Object.fromEntries(
    overridableQuarters.map((quarter) => {
      const quarterRow =
        typeof funnelQuarterLookup[quarter] === "object" && funnelQuarterLookup[quarter] !== null
          ? (funnelQuarterLookup[quarter] as Record<string, unknown>)
          : undefined;
      return [quarter, getQuarterMarketingMqlWeekly(quarterRow)];
    }),
  ) as Record<ScenarioQuarterKey, number | null>;

  const metrics: MetricItem[] = [
    {
      label: "Scenario FY Forecast",
      value: formatMoney(result.fy_capped),
      delta: formatSavedDelta(cappedDelta),
      deltaType: cappedDelta >= 0 ? "increase" : "decrease",
    },
    {
      label: "Baseline Forecast",
      value: formatMoney(baselineResult.fy_capped),
    },
    {
      label: comparablePlanActive ? "FY Plan Target" : "Comparison Scope",
      value:
        comparablePlanActive && typeof planFyTotal === "number"
          ? formatMoney(planFyTotal)
          : plan?.comparisonScopeLabel ?? "\u2014",
      delta:
        comparablePlanActive
          ? undefined
          : "Primary gap math suppressed",
      deltaType: "unchanged",
    },
    ...(comparablePlanActive && gapToPlan !== null
      ? [
          {
            label: "Scenario Gap To Plan",
            value: formatSignedMoney(gapToPlan),
            delta:
              gapClosureDelta !== null ? formatSavedDelta(gapClosureDelta) : undefined,
            deltaType:
              gapClosureDelta !== null && gapClosureDelta >= 0 ? "increase" : "decrease",
          } satisfies MetricItem,
        ]
      : []),
    {
      label: "Added AEs",
      value: addedAes.toFixed(0),
    },
  ];

  const monthlyChartData = months.map((month, index) => ({
    month: formatMonthLabel(month),
    "Existing Pipeline": result.monthly_inventory_wins[index] ?? 0,
    "Future Pipeline": result.monthly_future_wins[index] ?? 0,
    "Scenario Forecast": result.monthly_capped[index] ?? 0,
    "AE Capacity": result.monthly_capacity[index] ?? 0,
    [planMonthlyReference.label]: planMonthly[index] ?? 0,
  }));

  const cumulativeChartData = months.map((month, index) => ({
    month: formatMonthLabel(month),
    "Baseline Forecast": baselineResult.cumulative_capped[index] ?? 0,
    "Scenario Forecast": result.cumulative_capped[index] ?? 0,
    "Cumulative Plan Reference": planCumulative[index] ?? 0,
  }));

  const quarterByMonth = snapshot.scenario_building_blocks.quarter_by_month ?? [];
  // The "in-progress" / locked quarter is the first quarter we see that isn't
  // in the overridable list — it has at least some actuals so the user can't
  // override it.
  const lockedQuarter = quarterByMonth.find(
    (q): q is string => q !== null && !overridableQuarters.includes(q),
  ) ?? null;
  // All quarters present in the snapshot, in chronological order. Replaces the
  // deprecated DISPLAY_QUARTERS literal — derived from snapshot data so it works
  // for any fiscal calendar.
  const allQuarters: string[] = Array.from(
    new Set(quarterByMonth.filter((q): q is string => q !== null)),
  );
  const quarterRows: ScenarioQuarterSummaryRow[] = allQuarters.map((quarter) => {
    const planTarget = getPlanQuarterTarget(plan, quarter);
    const scenarioCapped = sumQuarter(quarterByMonth, quarter, result.monthly_capped);
    const scenarioExpected = sumQuarter(quarterByMonth, quarter, result.monthly_expected);
    const baselineCapped = sumQuarter(quarterByMonth, quarter, baselineResult.monthly_capped);
    const status: ScenarioQuarterSummaryRow["status"] =
      quarter === lockedQuarter
        ? "Locked"
        : hasQuarterOverride(quarter, overrides, baselineOverrides)
          ? "Override"
          : "Baseline";

    return {
      quarter,
      monthRange: quarterMonthRange(months, quarterByMonth, quarter),
      status,
      planTarget,
      baselineCapped,
      scenarioCapped,
      scenarioExpected,
      gapToPlan: typeof planTarget === "number" ? scenarioCapped - planTarget : null,
    };
  });

  const activeQuarterRow = quarterRows.find((row) => row.quarter === activeQuarter);
  const activeQuarterPlanReference = quarterReferenceLookup[activeQuarter];
  const activeSavedMqlWeekly = savedMqlWeeklyLookup[activeQuarter];
  const activeQuarterMonths = months.filter((_month, index) => quarterByMonth[index] === activeQuarter);
  const activePlanAeMonthTargets = activeQuarterMonths.map((month) =>
    typeof plan?.targets.explicitMonthlyAeTargets[month] === "number"
      ? plan.targets.explicitMonthlyAeTargets[month]
      : null,
  );
  const activeScenarioMqlWeekly =
    activeSavedMqlWeekly === null
      ? null
      : activeSavedMqlWeekly * (1 + (overrides[activeQuarter].mqlChangePct ?? 0));

  const monthlyRows = months.map((month, index) => ({
    month: formatMonthLabel(month),
    basis: actualFlags[index] ? "Actual" : "Projected",
    existing: result.monthly_inventory_wins[index] ?? 0,
    future: result.monthly_future_wins[index] ?? 0,
    uncapped: result.monthly_expected[index] ?? 0,
    capped: result.monthly_capped[index] ?? 0,
    capacity: result.monthly_capacity[index] ?? 0,
    overflow: result.monthly_overflow[index] ?? 0,
  }));

  // "Locked quarter" pacing: how much has actually booked + how much is still
  // expected within the in-progress quarter. Sourced from snapshot's
  // quarter_by_month + monthly_is_actual so the page works for any fiscal calendar.
  const q1ActualToDate = months.reduce((total, _month, index) => {
    if (quarterByMonth[index] !== lockedQuarter) return total;
    if (!actualFlags[index]) return total;
    return total + (baselineResult.monthly_capped[index] ?? 0);
  }, 0);
  const q1LockedForecast = lockedQuarter
    ? sumQuarter(quarterByMonth, lockedQuarter, baselineResult.monthly_capped)
    : 0;
  const q1RemainingProjection = Math.max(0, q1LockedForecast - q1ActualToDate);

  if (!activeQuarterRow) return null;

  async function handleCopyShareLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShareStatus("copied");
    } catch {
      setShareStatus("error");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <ScenarioPlannerHeader
        firstProjectedLabel={firstProjectedLabel}
        firstEditableQuarter={overridableQuarters[0] ?? ""}
        editableQuarterRangeLabel={
          overridableQuarters.length > 1
            ? `${overridableQuarters[0]}–${overridableQuarters[overridableQuarters.length - 1]}`
            : overridableQuarters[0] ?? ""
        }
        q1ActualToDate={q1ActualToDate}
        q1RemainingProjection={q1RemainingProjection}
        q1LockedForecast={q1LockedForecast}
        planName={plan?.name ?? null}
        planFyTotal={planFyTotal}
        comparisonScopeLabel={plan?.comparisonScopeLabel ?? null}
        onResetAll={() => onOverridesChange(cloneScenarioOverrides(baselineOverrides))}
        onCopyShareLink={handleCopyShareLink}
        shareStatus={shareStatus}
      />

      {planSelectionNotice ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {planSelectionNotice.message}
        </div>
      ) : null}

      {!comparablePlanActive && plan ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {plan.name} does not ship an operator-comparable default view. Scenario target rails and primary gap math are intentionally suppressed.
        </div>
      ) : null}

      {comparablePlanActive && !comparableQuarterly ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          The selected comparable view does not support quarterly grain. Quarter gaps and quarter-level plan references are suppressed.
        </div>
      ) : null}

      <MetricStrip metrics={metrics} />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_470px]">
        <div className="min-w-0">
          <ScenarioQuarterFocus
            quarterRows={quarterRows}
            activeQuarter={activeQuarter}
            onSelectQuarter={setActiveQuarter}
          />

          <ScenarioForecastCharts
            monthlyChartData={monthlyChartData}
            cumulativeChartData={cumulativeChartData}
            planMonthlyLabel={planMonthlyReference.label}
            planNote={planMonthlyReference.note}
            showPlanMonthly={comparablePlanActive && showComparableMonthlyRail}
            showPlanCumulative={comparablePlanActive && showComparableMonthlyRail}
          />

          <ScenarioSummaryTables
            quarterRows={quarterRows}
            activeQuarter={activeQuarter}
            monthlyRows={monthlyRows}
          />

          <Text className="mt-6 text-xs text-slate-400">
            Data as of {snapshot.as_of} · Snapshot generated{" "}
            {new Date(snapshot.generated_at).toLocaleString()} · Git {snapshot.git_sha.slice(0, 7)}
          </Text>
        </div>

        <div className="xl:sticky xl:top-6 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto">
          <ScenarioQuarterInspector
            quarter={activeQuarter}
            monthRange={activeQuarterRow.monthRange}
            override={overrides[activeQuarter]}
            baseline={baselineOverrides[activeQuarter]}
            mode={activeQuarterRow.status === "Override" ? "override" : "baseline"}
            monthLabels={activeQuarterMonths.map((month) => formatMonthLabel(month))}
            savedAeTargets={[...baselineOverrides[activeQuarter].aeMonthTargets]}
            seatTargets={[...overrides[activeQuarter].aeMonthTargets]}
            planAeMonthTargets={activePlanAeMonthTargets}
            savedQuarterBookings={activeQuarterRow.baselineCapped}
            planQuarterBookings={activeQuarterRow.planTarget}
            planAeTarget={activeQuarterPlanReference.quarterEndAeTarget}
            savedMqlWeekly={activeSavedMqlWeekly}
            planMqlWeekly={activeQuarterPlanReference.mqlWeekly}
            scenarioMqlWeekly={activeScenarioMqlWeekly}
            scenarioQuarterBookings={activeQuarterRow.scenarioCapped}
            scenarioGapToPlan={activeQuarterRow.gapToPlan}
            planReference={activeQuarterPlanReference}
            onChange={(field, value) =>
              onOverridesChange((current) => ({
                ...current,
                [activeQuarter]: {
                  ...current[activeQuarter],
                  [field]: value,
                },
              }))
            }
            onAeTargetChange={(monthOffset, value) =>
              onOverridesChange((current) =>
                applyAeSeatTargetEdit(current, baselineOverrides, activeQuarter, monthOffset, value),
              )
            }
            onMqlWeeklyChange={(value) =>
              onOverridesChange((current) => ({
                ...current,
                [activeQuarter]: {
                  ...current[activeQuarter],
                  mqlChangePct:
                    activeSavedMqlWeekly && activeSavedMqlWeekly > 0
                      ? value === Math.round(activeSavedMqlWeekly)
                        ? 0
                        : value / activeSavedMqlWeekly - 1
                      : 0,
                },
              }))
            }
            onResetQuarter={() =>
              onOverridesChange((current) =>
                resetQuarterOverrides(current, baselineOverrides, activeQuarter),
              )
            }
            onCopyAssumptionsForward={
              overridableQuarters.indexOf(activeQuarter) ===
              overridableQuarters.length - 1
                ? null
                : () =>
                    onOverridesChange((current) =>
                      copyQuarterAssumptionsForward(
                        current,
                        activeQuarter,
                        activeScenarioMqlWeekly,
                        savedMqlWeeklyLookup,
                      ),
                    )
            }
          />
        </div>
      </div>
    </div>
  );
}
