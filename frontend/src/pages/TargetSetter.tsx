import { useMemo, useState, useEffect } from "react";
import { SectionHeader } from "../components/workbook";
import { Card, Text } from "../components/ui";
import { usePlanningSessionContext } from "../context/PlanningSessionContext";
import { formatMoney } from "../lib/format";
import { daysUntilQuarterEnd } from "../engine/scenario";
import { buildObservedScenario } from "../lib/targetSetter/observedScenario";
import { loadScenariosFromSnapshot } from "../lib/targetSetter/scenarios";
import { computeStartingPipe, computeYtdBookings } from "../lib/targetSetter/snapshotData";
import { determineSolveScope } from "../lib/targetSetter/scope";
import { solve } from "../lib/targetSetter/solve";
import { extractQuarterlyBookingsFromPlan } from "../lib/targetSetter/planExtract";
import { computeMqlQoqDelta } from "../lib/targetSetter/qoqDelta";
import type { MonthlyShape } from "../lib/targetSetter/distribute";
import type { Scenario, QuarterKey } from "../types/targetSetter";
import { HeroTarget } from "../components/targetSetter/HeroTarget";
import { ScenarioSelector } from "../components/targetSetter/ScenarioSelector";
import { RateAdjust } from "../components/targetSetter/RateAdjust";
import { RoleSummaryStrip } from "../components/targetSetter/RoleSummaryStrip";
import { FunnelGrid } from "../components/targetSetter/FunnelGrid";
import { FunnelSankey } from "../components/targetSetter/FunnelSankey";
import { ScenarioComparison } from "../components/targetSetter/ScenarioComparison";
import { OutputsTable } from "../components/targetSetter/OutputsTable";
import { AssumptionsPanel } from "../components/targetSetter/AssumptionsPanel";
import {
  buildRateByEdge,
  buildScenarioOptions,
  buildRoleCards,
  buildTotalS0Footer,
} from "../lib/targetSetter/pageHelpers";

export default function TargetSetter() {
  const { snapshot, selectedPlan } = usePlanningSessionContext();

  // Hook order discipline: all hooks before any early return.

  const observedScenario = useMemo(() => buildObservedScenario(snapshot), [snapshot]);
  const namedScenarios = useMemo(() => loadScenariosFromSnapshot(snapshot), [snapshot]);

  const defaultScenarioId = useMemo<string | null>(() => {
    if (observedScenario) return observedScenario.id;
    if (namedScenarios.length > 0) return namedScenarios[0].id;
    return null;
  }, [observedScenario, namedScenarios]);

  const [scenarioId, setScenarioId] = useState<string | null>(defaultScenarioId);
  const [customScenario, setCustomScenario] = useState<Scenario | null>(null);
  const [distributionShape, setDistributionShape] = useState<MonthlyShape>("flat");

  // Track snapshot identity. When it changes, reset custom state synchronously
  // (during render — official React pattern for resetting state on prop change).
  // This prevents one-render staleness where customScenario from a prior profile
  // would be solved against the new snapshot.
  const [prevSnapshot, setPrevSnapshot] = useState(snapshot);
  if (prevSnapshot !== snapshot) {
    setPrevSnapshot(snapshot);
    setCustomScenario(null);
    // Reset scenarioId to the new snapshot's default, computed above. Using
    // defaultScenarioId (already reflecting the new snapshot) prevents one-render
    // staleness where a prior "custom" id would be solved against the new snapshot.
    // The reconciliation useEffect below is defensive depth for the case where
    // named scenarios change without the snapshot reference changing.
    setScenarioId(defaultScenarioId);
  }

  // Reconcile stale scenarioId when snapshot/profile changes.
  const validIds = useMemo(() => {
    const set = new Set<string>();
    if (observedScenario) set.add(observedScenario.id);
    for (const s of namedScenarios) set.add(s.id);
    if (customScenario) set.add("custom");
    return set;
  }, [observedScenario, namedScenarios, customScenario]);

  useEffect(() => {
    if (scenarioId !== null && !validIds.has(scenarioId)) {
      setScenarioId(defaultScenarioId);
    }
  }, [validIds, defaultScenarioId, scenarioId]);

  const activeScenario = useMemo<Scenario | null>(() => {
    if (scenarioId === null) return null;
    if (scenarioId === "custom" && customScenario) return customScenario;
    if (scenarioId === "observed") return observedScenario;
    return (
      namedScenarios.find((s) => s.id === scenarioId) ??
      observedScenario ??
      namedScenarios[0] ??
      null
    );
  }, [scenarioId, customScenario, observedScenario, namedScenarios]);

  // Scenario selection: clears any custom adjustments when picking a baseline pill.
  const handleScenarioSelect = (id: string) => {
    if (id === "custom") return; // "Custom" pill is read-only; user enters custom by adjusting rates
    setCustomScenario(null);
    setScenarioId(id);
  };

  // Rate adjustment: snapshots the current activeScenario as the starting custom, applies the edit.
  const handleRateAdjust = (
    partial: Partial<{
      mql_to_s0: number;
      s0_to_s1: number;
      s1_to_s2: number;
      win_rate_created: number;
    }>,
  ) => {
    setCustomScenario((prev) => {
      const base = prev ?? {
        ...(activeScenario ?? ({} as Scenario)),
        id: "custom" as const,
        label: "Custom",
      };
      return { ...base, ...partial };
    });
    setScenarioId("custom");
  };

  const handleResetCustom = () => {
    setCustomScenario(null);
    setScenarioId(defaultScenarioId);
  };

  const starting_pipe = useMemo(
    () => computeStartingPipe(snapshot.pipeline.inventory_by_stage),
    [snapshot],
  );

  const { active: activeQuarter } = useMemo(
    () => determineSolveScope(snapshot, snapshot.as_of),
    [snapshot],
  );

  const { bookings_targets, planMissingBanner } = useMemo(() => {
    const extracted = extractQuarterlyBookingsFromPlan(snapshot, selectedPlan);
    if (extracted) return { bookings_targets: extracted, planMissingBanner: null as string | null };
    return {
      bookings_targets: {} as Record<QuarterKey, number>,
      planMissingBanner: "No plan selected — add a plan file to enable bookings targets." as string | null,
    };
  }, [snapshot, selectedPlan]);

  const active_ytd_bookings = useMemo(() => {
    if (!activeQuarter) return 0;
    return computeYtdBookings(snapshot, {
      bookings: snapshot.actuals.bookings_by_month,
      activeQuarter,
      asOf: snapshot.as_of,
    });
  }, [snapshot, activeQuarter]);

  // All hooks above — safe to early-return after this point.

  const result = useMemo(() => {
    if (!activeScenario) return null;
    return solve({
      snapshot,
      as_of: snapshot.as_of,
      starting_pipe,
      bookings_targets,
      scenario: activeScenario,
      active_ytd_bookings,
    });
  }, [snapshot, starting_pipe, bookings_targets, activeScenario, active_ytd_bookings]);

  const allScenarios = useMemo(() => {
    if (!activeScenario) return [];
    const common = {
      snapshot,
      starting_pipe,
      bookings_targets,
      as_of: snapshot.as_of,
      active_ytd_bookings,
    };
    const buildFunnel = (s: Scenario) => ({
      mql_to_s0: s.mql_to_s0,
      s0_to_s1: s.s0_to_s1,
      s1_to_s2: s.s1_to_s2,
    });

    const entries: Array<{
      id: string;
      label: string;
      result: ReturnType<typeof solve>;
      funnel: { mql_to_s0: number; s0_to_s1: number; s1_to_s2: number };
    }> = [];

    if (observedScenario) {
      entries.push({
        id: observedScenario.id,
        label: observedScenario.label,
        result: solve({ ...common, scenario: observedScenario }),
        funnel: buildFunnel(observedScenario),
      });
    }

    for (const s of namedScenarios) {
      entries.push({
        id: s.id,
        label: s.label,
        result: solve({ ...common, scenario: s }),
        funnel: buildFunnel(s),
      });
    }

    if (customScenario) {
      entries.push({
        id: "custom",
        label: "Custom",
        result: solve({ ...common, scenario: customScenario }),
        funnel: buildFunnel(customScenario),
      });
    }
    return entries;
  }, [
    observedScenario,
    namedScenarios,
    customScenario,
    activeScenario,
    starting_pipe,
    bookings_targets,
    snapshot,
    active_ytd_bookings,
  ]);

  const scopeLabel = useMemo(() => {
    if (!result) return "—";
    const scope = result.scope;
    if (scope.length === 0) return "—";
    if (scope.length === 1) return scope[0];
    return `${scope[0]}–${scope[scope.length - 1]}`;
  }, [result]);

  const planTotal = useMemo(
    () => (result ? result.quarters.reduce((s, q) => s + q.bookings_target, 0) : 0),
    [result],
  );

  const carriedContribution = useMemo(
    () => (result ? result.quarters.reduce((s, q) => s + q.won_from_starting, 0) : 0),
    [result],
  );

  const newPipeMustYield = planTotal - carriedContribution;

  const activeQuarterContext = useMemo(() => {
    if (!activeQuarter) return undefined;
    const activePlanTarget = bookings_targets[activeQuarter] ?? 0;
    return {
      quarter: activeQuarter,
      ytd: active_ytd_bookings,
      inQuarterRemaining: activePlanTarget - active_ytd_bookings,
    };
  }, [activeQuarter, bookings_targets, active_ytd_bookings]);

  const rateByEdge = useMemo(() => {
    if (!activeScenario) return null;
    return buildRateByEdge(activeScenario, snapshot);
  }, [activeScenario, snapshot]);

  const scenarioOptions = useMemo(
    () => buildScenarioOptions(snapshot, customScenario !== null),
    [snapshot, customScenario],
  );

  const mqlQoq = useMemo(() => {
    if (!result || !activeScenario || scenarioId !== "observed") return null;
    return computeMqlQoqDelta({
      snapshot,
      actuals: snapshot.actuals,
      asOf: snapshot.as_of,
      targetQNext: result.quarters[0]?.mqls ?? 0,
    });
  }, [scenarioId, snapshot, result, activeScenario]);

  const roleCards = useMemo(
    () => (result ? buildRoleCards(result.quarters, mqlQoq) : []),
    [result, mqlQoq],
  );

  const totalS0Footer = useMemo(
    () => (result ? buildTotalS0Footer(result.quarters) : null),
    [result],
  );

  const totalProjected = result
    ? result.quarters.reduce((s, q) => s + q.won_from_starting + q.won_from_created, 0)
    : 0;

  const daysToEnd = activeQuarter
    ? daysUntilQuarterEnd(snapshot, snapshot.as_of, activeQuarter)
    : 0;
  const startingPipeBanner =
    daysToEnd > 30 && activeQuarter
      ? `Starting pipeline is current open S2+ inventory (not projected ${activeQuarter} end). Accuracy improves as ${activeQuarter} progresses — currently ${daysToEnd} days remaining.`
      : null;

  // Empty state: no TargetSetter configuration in this snapshot.
  if (!activeScenario) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] text-center space-y-2">
        <p className="text-sm text-text-secondary">
          This profile has no TargetSetter configuration. Add{" "}
          <code className="font-mono text-xs">scenarios.yaml</code> and/or{" "}
          <code className="font-mono text-xs">target_setter_defaults</code> to enable.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Title + description */}
      <SectionHeader
        title="Target Setter"
        subtitle="What the engine says Marketing, SDRs, and AEs need to generate each quarter to hit plan — and where the math comes from."
      />

      {/* Banners */}
      {planMissingBanner && (
        <Card className="p-3 bg-blue-50 border border-blue-200">
          <Text className="text-sm text-slate-700">{planMissingBanner}</Text>
        </Card>
      )}
      {startingPipeBanner && (
        <Card className="p-3 bg-amber-50 border border-amber-200">
          <Text className="text-sm text-slate-700">{startingPipeBanner}</Text>
        </Card>
      )}

      {/* Section 1: Hero */}
      <HeroTarget
        scopeLabel={scopeLabel}
        newPipeMustYield={newPipeMustYield}
        planTotal={planTotal}
        carriedContribution={carriedContribution}
        activeQuarter={activeQuarterContext}
      />

      {/* Section 2: Scenario selector + adjust panel */}
      <div>
        <SectionHeader
          title="Funnel ask"
          subtitle="Pick a scenario or adjust rates to see how the ask moves. Other waterfall rates (starting-pipe win rate, push, loss) stay pinned to the observed calibration."
        />
        <div className="space-y-3">
          <ScenarioSelector
            activeId={scenarioId ?? ""}
            scenarios={scenarioOptions}
            onSelect={handleScenarioSelect}
          />
          <RateAdjust
            rates={{
              mql_to_s0: activeScenario.mql_to_s0,
              s0_to_s1: activeScenario.s0_to_s1,
              s1_to_s2: activeScenario.s1_to_s2,
              win_rate_created: activeScenario.win_rate_created,
            }}
            onChange={handleRateAdjust}
            canReset={scenarioId !== "observed"}
            onReset={handleResetCustom}
          />
        </div>
      </div>

      {/* Section 3: Sensitivity peek */}
      <ScenarioComparison scenarios={allScenarios} activeId={scenarioId ?? ""} />

      {/* Section 4: Role summary strip */}
      {result && totalS0Footer && (
        <RoleSummaryStrip scopeLabel={scopeLabel} cards={roleCards} total={totalS0Footer} />
      )}

      {/* Section 5: Funnel view */}
      {result && rateByEdge && (
        <>
          <FunnelSankey quarters={result.quarters} rateByEdge={rateByEdge} />
          <FunnelGrid
            quarters={result.quarters}
            scenario={activeScenario}
            rateByEdge={rateByEdge}
          />
        </>
      )}

      {/* Section 6: Monthly/weekly cadence */}
      {result && (
        <div>
          <SectionHeader
            title="Monthly & weekly cadence"
            subtitle="How each quarter's target distributes across months (and weeks for MQLs)."
          />
          <div className="flex items-center gap-2 mb-3">
            <Text className="text-xs text-slate-600">Monthly distribution:</Text>
            <select
              value={distributionShape}
              onChange={(e) => setDistributionShape(e.target.value as MonthlyShape)}
              className="border border-slate-300 rounded px-2 py-1 text-xs tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Monthly distribution shape"
            >
              <option value="flat">Flat thirds (33 / 33 / 34)</option>
              <option value="back_loaded">Back-loaded (25 / 35 / 40)</option>
            </select>
          </div>
          <OutputsTable quarters={result.quarters} distributionShape={distributionShape} />
        </div>
      )}

      {/* Section 7: Assumptions */}
      <div className="space-y-3">
        <AssumptionsPanel />
      </div>

      {/* Warnings (informational, not blocking) */}
      {result && result.warnings.length > 0 && (
        <Card className="p-3 bg-amber-50 border border-amber-200 space-y-1">
          {result.warnings.map((w, i) => (
            <Text key={i} className="text-xs text-slate-700">
              {w}
            </Text>
          ))}
        </Card>
      )}

      {/* Hidden sentinel for tests */}
      <span className="sr-only" data-testid="targetsetter-projected-bookings">
        {formatMoney(totalProjected)}
      </span>
    </div>
  );
}
