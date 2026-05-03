import { Card, Text } from "../ui";
import type { SolveResult, QuarterKey } from "../../types/targetSetter";

export interface ScenarioComparisonEntry {
  id: string;
  label: string;
  result: SolveResult;
  /** Funnel rates that produced these numbers — shown under each column so the
   *  reader can see *why* scenarios differ. */
  funnel: {
    mql_to_s0: number;
    s0_to_s1: number;
    s1_to_s2: number;
  };
}

export interface ScenarioComparisonProps {
  scenarios: ScenarioComparisonEntry[];
  /** Active scenario id — highlighted column. Optional. */
  activeId?: string;
}

/**
 * Tight one-metric strip: MQLs-needed per quarter per scenario.
 * Answers the sensitivity question the Funnel Grid doesn't:
 * "how much does the Marketing ask move under different assumptions?"
 */
export function ScenarioComparison({ scenarios, activeId }: ScenarioComparisonProps) {
  if (scenarios.length === 0) return null;
  const firstQuarter = scenarios[0].result.scope[0];
  const quartersToRender: QuarterKey[] = firstQuarter ? [firstQuarter] : [];

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-slate-200">
        <Text className="text-sm font-semibold text-slate-800">
          Scenario sensitivity — MQLs required
        </Text>
        <Text className="text-xs text-slate-500 mt-0.5">
          First quarter in scope — same bookings target, different funnel assumptions
        </Text>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-5 py-2 text-left text-xs uppercase tracking-wide text-slate-500 font-medium">
                Quarter
              </th>
              {scenarios.map((s) => {
                const isActive = s.id === activeId;
                const yieldPct =
                  s.funnel.mql_to_s0 * s.funnel.s0_to_s1 * s.funnel.s1_to_s2;
                return (
                  <th
                    key={s.id}
                    className={`px-4 py-2 text-right text-xs font-medium ${
                      isActive ? "bg-blue-600 text-white" : "text-slate-500"
                    }`}
                  >
                    <div className="uppercase tracking-wide">{s.label}</div>
                    <div
                      className={`text-[10px] font-normal normal-case mt-0.5 ${
                        isActive ? "text-blue-100" : "text-slate-400"
                      }`}
                    >
                      Front-end yield: {(yieldPct * 100).toFixed(2)}%
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {quartersToRender.map((q) => (
              <tr key={q} className="border-t border-slate-100">
                <td className="px-5 py-2 font-medium text-slate-700">{q}</td>
                {scenarios.map((s) => {
                  const qt = s.result.quarters.find((row) => row.quarter === q);
                  const isActive = s.id === activeId;
                  return (
                    <td
                      key={s.id}
                      className={`px-4 py-2 text-right tabular-nums font-semibold ${
                        isActive ? "bg-blue-50 text-blue-900" : "text-slate-600"
                      }`}
                    >
                      {qt ? Math.round(qt.mqls).toLocaleString() : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
