import type { QuarterTargets } from "../../types/targetSetter";
import type { MonthlyShape } from "../../lib/targetSetter/distribute";
import { distributeMonthly, distributeWeekly } from "../../lib/targetSetter/distribute";

export interface OutputsTableProps {
  quarters: QuarterTargets[];
  distributionShape: MonthlyShape;
}

type MetricKey = "mqls" | "s0" | "s1" | "marketing_s2_total" | "created_pipe";

const METRICS: { key: MetricKey; label: string; shortLabel: string; integer: boolean }[] = [
  { key: "mqls", label: "MQLs", shortLabel: "MQL", integer: true },
  { key: "s0", label: "S0 Meetings Booked", shortLabel: "S0", integer: true },
  { key: "s1", label: "S1 Meetings Held", shortLabel: "S1", integer: true },
  { key: "marketing_s2_total", label: "S2 SQOs (marketing)", shortLabel: "S2 mkt", integer: true },
  { key: "created_pipe", label: "Created S2 Pipeline ($)", shortLabel: "Created $", integer: false },
];

function formatValue(v: number, integer: boolean): string {
  return integer ? Math.round(v).toLocaleString() : `$${Math.round(v).toLocaleString()}`;
}

export function OutputsTable({ quarters, distributionShape }: OutputsTableProps) {
  if (quarters.length === 0) {
    return <div className="text-sm text-gray-500">No quarters in solve scope (late in plan year).</div>;
  }

  return (
    <div className="overflow-x-auto space-y-4">
      <table className="min-w-full border text-sm">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Metric</th>
            {quarters.map((q) => (
              <th key={q.quarter} className="p-2 text-right">
                {q.quarter}
                {q.infeasible && <span className="ml-2 text-red-600 text-xs">(infeasible)</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {METRICS.map((m) => (
            <tr key={m.key} className="border-t">
              <td className="p-2 font-medium">{m.label}</td>
              {quarters.map((q) => (
                <td key={q.quarter} className="p-2 text-right">
                  {formatValue(q[m.key], m.integer)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <details open>
        <summary className="cursor-pointer text-sm font-medium">
          Monthly breakout (shape: {distributionShape === "flat" ? "flat thirds" : "25 / 35 / 40"})
        </summary>
        <table className="min-w-full border text-sm mt-2">
          <thead>
            <tr className="bg-gray-50">
              <th className="p-2 text-left">Quarter / Metric</th>
              <th className="p-2 text-right">M1</th>
              <th className="p-2 text-right">M2</th>
              <th className="p-2 text-right">M3</th>
            </tr>
          </thead>
          <tbody>
            {quarters.flatMap((q) =>
              METRICS.map((m) => {
                const parts = distributeMonthly({
                  quarterly: q[m.key],
                  shape: distributionShape,
                  integer: m.integer,
                });
                return (
                  <tr key={`${q.quarter}-${m.key}`} className="border-t">
                    <td className="p-2 text-xs">
                      {q.quarter} · {m.shortLabel}
                    </td>
                    {parts.map((p, i) => (
                      <td key={i} className="p-2 text-right text-xs">
                        {formatValue(p, m.integer)}
                      </td>
                    ))}
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </details>

      <details open>
        <summary className="cursor-pointer text-sm font-medium">Weekly MQL breakout (13-week flat)</summary>
        <table className="min-w-full border text-xs mt-2">
          <thead>
            <tr className="bg-gray-50">
              <th className="p-2 text-left">Quarter</th>
              {Array.from({ length: 13 }).map((_, i) => (
                <th key={i} className="p-1 text-right">
                  W{i + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {quarters.map((q) => {
              const parts = distributeWeekly({ quarterly: q.mqls });
              return (
                <tr key={q.quarter} className="border-t">
                  <td className="p-2">{q.quarter}</td>
                  {parts.map((p, i) => (
                    <td key={i} className="p-1 text-right">
                      {p}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </div>
  );
}
