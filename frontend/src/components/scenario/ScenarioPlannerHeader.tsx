import { Badge, Card, Text } from "../ui";
import { formatMoney } from "../../lib/format";

interface Props {
  firstProjectedLabel: string;
  firstEditableQuarter: string;
  editableQuarterRangeLabel: string;
  q1ActualToDate: number;
  q1RemainingProjection: number;
  q1LockedForecast: number;
  planName: string | null;
  planFyTotal: number | null;
  comparisonScopeLabel: string | null;
  onResetAll: () => void;
  onCopyShareLink: () => void;
  shareStatus: "idle" | "copied" | "error";
}

export function ScenarioPlannerHeader({
  firstProjectedLabel,
  firstEditableQuarter,
  editableQuarterRangeLabel,
  q1ActualToDate,
  q1RemainingProjection,
  q1LockedForecast,
  planName,
  planFyTotal,
  comparisonScopeLabel,
  onResetAll,
  onCopyShareLink,
  shareStatus,
}: Props) {
  return (
    <Card className="overflow-hidden border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-[linear-gradient(135deg,rgba(248,250,252,0.98),rgba(239,246,255,0.92))] px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-5xl">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">Trajectory Scenario Planner</h2>
              <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600">
                First projected month {firstProjectedLabel}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Pressure-test operating bets against the gap between the saved trajectory and the
              selected plan. Baseline stays anchored to the saved snapshot, the plan remains a
              separate comparison target, and overrides show what would need to change to close the
              gap.
            </p>
            <div className="mt-4 flex flex-wrap items-start gap-2">
              <span className="inline-flex self-start rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-700">
                Baseline is anchored to the saved trajectory
              </span>
              <span className="inline-flex self-start rounded-full border border-red-200 bg-white px-3 py-1.5 text-[11px] font-medium text-red-700">
                Plan target stays separate
              </span>
              <span className="inline-flex self-start rounded-full border border-blue-200 bg-white px-3 py-1.5 text-[11px] font-medium text-blue-700">
                Overrides pressure-test the gap
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onCopyShareLink}
              className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 transition hover:border-blue-300 hover:bg-blue-100"
            >
              {shareStatus === "copied"
                ? "Link Copied"
                : shareStatus === "error"
                  ? "Copy Failed"
                  : "Copy Share Link"}
            </button>
            <button
              type="button"
              onClick={onResetAll}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            >
              Reset All
            </button>
          </div>
        </div>

        <div className="grid gap-3 px-0 pt-4 xl:grid-cols-[1.35fr_1fr_1fr_1fr]">
          <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4">
            <div className="flex items-center justify-between gap-3">
              <Text className="text-[11px] uppercase tracking-wide text-slate-600">
                Locked-Quarter Outlook
              </Text>
              <Badge color="gray">Locked</Badge>
            </div>
            <Text className="mt-1 text-[11px] leading-4 text-slate-500">
              Actuals are fixed. {firstProjectedLabel} stays pinned to the saved snapshot.
            </Text>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <div className="rounded-lg border border-white/80 bg-white/70 p-3">
                <div className="text-[11px] uppercase tracking-wide text-slate-500">Actuals to Date</div>
                <div className="mt-1 text-xl font-semibold text-slate-900">{formatMoney(q1ActualToDate)}</div>
              </div>
              <div className="rounded-lg border border-white/80 bg-white/70 p-3">
                <div className="text-[11px] uppercase tracking-wide text-slate-500">Remaining Projected</div>
                <div className="mt-1 text-xl font-semibold text-slate-900">{formatMoney(q1RemainingProjection)}</div>
              </div>
              <div className="rounded-lg border border-white/80 bg-white/70 p-3">
                <div className="text-[11px] uppercase tracking-wide text-slate-500">Total Locked Outlook</div>
                <div className="mt-1 text-xl font-semibold text-slate-900">{formatMoney(q1LockedForecast)}</div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <Text className="text-[11px] uppercase tracking-wide text-slate-500">Projection Starts</Text>
            <div className="mt-2 text-lg font-semibold text-slate-900">{firstProjectedLabel}</div>
            <Text className="mt-1 text-[11px] leading-4 text-slate-500">
              First full month that is still modeled rather than observed.
            </Text>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <Text className="text-[11px] uppercase tracking-wide text-slate-500">
              First Editable Quarter
            </Text>
            <div className="mt-2 text-lg font-semibold text-slate-900">{firstEditableQuarter || "—"}</div>
            <Text className="mt-1 text-[11px] leading-4 text-slate-500">
              Scenario overrides only affect {editableQuarterRangeLabel || "the editable quarters"}.
            </Text>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <Text className="text-[11px] uppercase tracking-wide text-slate-500">Selected Plan</Text>
            <div className="mt-2 text-base font-semibold text-slate-900">{planName ?? "\u2014"}</div>
            <Text className="mt-1 text-[12px] text-slate-500">
              {comparisonScopeLabel ? `${comparisonScopeLabel}. ` : ""}
              FY target {planName && typeof planFyTotal === "number" ? formatMoney(planFyTotal) : "\u2014"}.
            </Text>
            <Text className="mt-2 text-[11px] leading-4 text-slate-500">
              Comparison target only. It does not seed the baseline math.
            </Text>
          </div>
        </div>
      </div>
    </Card>
  );
}
