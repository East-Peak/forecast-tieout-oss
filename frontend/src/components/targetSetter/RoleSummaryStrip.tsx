import { Text } from "../ui";
import { MetricCard } from "../workbook";
import type { RoleSummaryCard, TotalFooter } from "../../types/targetSetter";

export interface RoleSummaryStripProps {
  scopeLabel: string;
  cards: RoleSummaryCard[];
  /** Optional combined total shown below the role strip. */
  total?: TotalFooter;
}

function fmt(n: number, integer: boolean): string {
  return integer ? Math.round(n).toLocaleString() : `$${Math.round(n).toLocaleString()}`;
}

export function RoleSummaryStrip({ scopeLabel, cards, total }: RoleSummaryStripProps) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {cards.map((c) => (
          <MetricCard
            key={c.role}
            label={c.metricLabel}
            value={fmt(c.totalValue, c.integer)}
            className="p-4"
          >
            <Text className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">
              {c.role.toUpperCase()}
            </Text>
            <div className="text-xs text-slate-500">{scopeLabel} total</div>
            <div className="mt-2 text-xs">
              {c.qoqDelta !== null ? (
                <span className={c.qoqDelta >= 0 ? "text-emerald-700" : "text-red-700"}>
                  {c.qoqDelta >= 0 ? "+" : ""}
                  {(c.qoqDelta * 100).toFixed(0)}% vs Q1 actuals
                </span>
              ) : (
                <span
                  title="Historical baseline requires splitting Marketing vs SDR-sourced streams — not available in current snapshot schema"
                  className="text-slate-400"
                >
                  (baseline not available)
                </span>
              )}
            </div>
            <div className="mt-2 text-xs text-slate-500">
              Per quarter:{" "}
              <span className="tabular-nums text-slate-700">
                {c.perQuarter.map((q) => fmt(q.value, c.integer)).join(" / ")}
              </span>
            </div>
            {c.secondary && (
              <div className="mt-3 pt-2 border-t border-slate-100">
                <div className="text-xs text-slate-500">{c.secondary.label}</div>
                <div className="text-lg font-semibold text-slate-800 tabular-nums mt-0.5">
                  {fmt(c.secondary.totalValue, c.secondary.integer)}
                </div>
                <div className="text-xs text-slate-500">
                  Per quarter:{" "}
                  <span className="tabular-nums text-slate-700">
                    {c.secondary.perQuarter.map((q) => fmt(q.value, c.secondary!.integer)).join(" / ")}
                  </span>
                </div>
              </div>
            )}
          </MetricCard>
        ))}
      </div>
      {total && (
        <MetricCard
          label={total.label}
          value={fmt(total.totalValue, total.integer)}
          className="p-3 bg-slate-50 border-slate-200"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              {total.components && (
                <div className="text-xs text-slate-500 mt-0.5 tabular-nums">
                  {total.components
                    .map((c) => `${c.label} ${fmt(c.value, total.integer)}`)
                    .join(" + ")}
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="text-xs text-slate-500">
                Per quarter:{" "}
                <span className="tabular-nums text-slate-700">
                  {total.perQuarter.map((q) => fmt(q.value, total.integer)).join(" / ")}
                </span>
              </div>
            </div>
          </div>
        </MetricCard>
      )}
    </div>
  );
}
