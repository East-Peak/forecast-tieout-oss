import { Badge, Card, Text } from "../ui";
import type { ScenarioQuarterKey } from "../../engine/scenario";
import type { ScenarioQuarterSummaryRow } from "../../lib/scenarioPlanner";
import { formatMoney, formatSignedMoney } from "../../lib/scenarioPlanner";

interface Props {
  quarterRows: ScenarioQuarterSummaryRow[];
  activeQuarter: ScenarioQuarterKey;
  onSelectQuarter: (quarter: ScenarioQuarterKey) => void;
}

export function ScenarioQuarterFocus({
  quarterRows,
  activeQuarter,
  onSelectQuarter,
}: Props) {
  return (
    <Card className="mb-6 p-5">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Quarter Focus</h3>
          <p className="mt-1 text-xs text-slate-500">
            Click a quarter card to edit it. The charts stay in view while the active quarter
            inspector on the right updates.
          </p>
        </div>
        <Text className="text-[11px] text-slate-500">
          Editing: <span className="font-medium text-slate-700">{activeQuarter}</span>
        </Text>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {quarterRows
          .filter((row) => row.status !== "Locked")
          .map((row) => {
            const isActive = row.quarter === activeQuarter;
            return (
              <button
                key={row.quarter}
                type="button"
                onClick={() => onSelectQuarter(row.quarter as ScenarioQuarterKey)}
                className={`group relative overflow-hidden rounded-2xl border p-4 text-left transition ${
                  isActive
                    ? "border-blue-300 bg-[linear-gradient(135deg,rgba(239,246,255,0.95),rgba(255,255,255,1))] shadow-sm ring-1 ring-blue-100"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <div
                  className={`absolute inset-x-0 top-0 h-1 ${
                    isActive ? "bg-blue-500" : "bg-transparent group-hover:bg-slate-200"
                  }`}
                />
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{row.quarter}</div>
                    <div className="text-xs text-slate-500">{row.monthRange}</div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <Badge color={row.status === "Override" ? "blue" : "gray"}>{row.status}</Badge>
                    <span
                      className={`text-[11px] font-medium ${
                        isActive ? "text-blue-700" : "text-slate-500"
                      }`}
                    >
                      {isActive ? "Editing now" : "Click to edit"}
                    </span>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-3">
                  <div className="rounded-xl border border-slate-200/80 bg-white/80 p-3">
                    <div className="text-[10px] uppercase tracking-wide text-slate-500">Baseline</div>
                    <div className="mt-1 text-base font-semibold text-slate-900">
                      {formatMoney(row.baselineCapped)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-red-100 bg-red-50/60 p-3">
                    <div className="text-[10px] uppercase tracking-wide text-red-700">Plan</div>
                    <div className="mt-1 text-base font-semibold text-slate-900">
                      {typeof row.planTarget === "number" ? formatMoney(row.planTarget) : "\u2014"}
                    </div>
                  </div>
                  <div
                    className={`rounded-xl p-3 ${
                      row.gapToPlan === null
                        ? "border border-slate-200 bg-slate-50/70"
                        : row.gapToPlan >= 0
                        ? "border border-emerald-100 bg-emerald-50/70"
                        : "border border-rose-100 bg-rose-50/70"
                    }`}
                  >
                    <div
                      className={`text-[10px] uppercase tracking-wide ${
                        row.gapToPlan === null
                          ? "text-slate-500"
                          : row.gapToPlan >= 0
                            ? "text-emerald-700"
                            : "text-rose-700"
                      }`}
                    >
                      Gap
                    </div>
                    <div
                      className={`mt-1 text-base font-semibold ${
                        row.gapToPlan === null
                          ? "text-slate-600"
                          : row.gapToPlan >= 0
                            ? "text-emerald-800"
                            : "text-rose-800"
                      }`}
                    >
                      {typeof row.gapToPlan === "number" ? formatSignedMoney(row.gapToPlan) : "\u2014"}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
      </div>
    </Card>
  );
}
