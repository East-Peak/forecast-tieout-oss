import { useState } from "react";
import { Card, Text } from "../ui";

function formatDollars(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

export interface HeroTargetProps {
  /** e.g. "Q2–Q4" or "Q4" */
  scopeLabel: string;
  newPipeMustYield: number;
  planTotal: number;
  carriedContribution: number;
  activeQuarter?: {
    quarter: string;
    ytd: number;
    inQuarterRemaining: number;
  };
}

export function HeroTarget({
  scopeLabel,
  newPipeMustYield,
  planTotal,
  carriedContribution,
  activeQuarter,
}: HeroTargetProps) {
  const [tipOpen, setTipOpen] = useState(false);
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2">
        <Text className="text-xs uppercase tracking-wide font-semibold text-slate-500">
          GAP TO PLAN
        </Text>
        <Text className="text-xs text-slate-500">· {scopeLabel}</Text>
        <div className="relative ml-1">
          <button
            type="button"
            aria-label="What counts as carried pipe?"
            onClick={() => setTipOpen((s) => !s)}
            className="w-4 h-4 rounded-full border border-slate-300 text-[10px] text-slate-500 hover:bg-slate-50"
          >
            i
          </button>
          {tipOpen && (
            <div
              role="tooltip"
              className="absolute left-0 top-5 z-20 w-72 rounded-md border border-slate-200 bg-white p-2 text-xs text-slate-600 shadow-lg"
            >
              Carried pipe is a <em>rolling chain</em>: pipe in S2+ today that
              wins in later quarters, plus pipe created mid-scope from S0/S1
              that converts. Not just today&apos;s opening inventory.
            </div>
          )}
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold text-slate-900 tabular-nums">
        {formatDollars(newPipeMustYield)} new pipe must yield
      </div>
      <div className="mt-2 text-sm text-slate-600">
        <span>{formatDollars(planTotal)} plan</span>
        {" − "}
        <span>{formatDollars(carriedContribution)} from S2+ pipe</span>
        {" rolling into quarters"}
      </div>
      {activeQuarter && (
        <div className="mt-3 text-xs text-slate-500">
          <span>{activeQuarter.quarter}</span>
          {" · YTD "}
          <span>{formatDollars(activeQuarter.ytd)}</span>
          {" · "}
          <span>{formatDollars(activeQuarter.inQuarterRemaining)} remaining in-quarter</span>
        </div>
      )}
    </Card>
  );
}
