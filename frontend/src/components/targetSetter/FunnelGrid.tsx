import { Card, Text } from "../ui";
import { formatMoney } from "../../lib/format";
import { RateProvenancePopover } from "./RateProvenancePopover";
import type { QuarterTargets, Scenario } from "../../types/targetSetter";
import type { RateProvenance } from "../../types/snapshot";

export interface FunnelGridProps {
  quarters: QuarterTargets[];
  scenario: Scenario;
  rateByEdge: {
    mql_to_s0: RateProvenance;
    outbound_to_s0: RateProvenance;
    s0_to_s1: RateProvenance;
    s1_to_s2: RateProvenance;
  };
}

/**
 * Two-tributary funnel. Shows that S0/S1/S2 volume has two sources feeding it:
 *
 *   MQLs (marketing ask) ──┐
 *                          ├─► S0 ─► S1 ─► S2 ─► Pipeline ─► Wins
 *   Outbound S0 (SDR ask) ─┘
 *
 * Marketing-sourced S0 = MQLs × mql_to_s0 (from the MQL tributary).
 * Outbound S0 = the gap between Total S0 and Marketing-sourced S0, i.e. what
 * SDRs + direct AE outreach must produce. v1 assumes same S0→S1 and S1→S2
 * rates for both tributaries (documented simplification).
 *
 * Below S0 the funnel is unified: one cascade of conversion rates applied to
 * the combined volume, landing at Total Pipeline then Wins.
 */
export function FunnelGrid({ quarters, scenario, rateByEdge }: FunnelGridProps) {
  if (quarters.length === 0) {
    return (
      <Card className="p-5">
        <Text className="text-sm text-slate-500">
          No future quarters in solve scope — the plan year has elapsed.
        </Text>
      </Card>
    );
  }

  const blendedAcv = Object.keys(scenario.segment_share).reduce(
    (sum, seg) => sum + scenario.segment_share[seg] * scenario.acv[seg],
    0,
  );

  const hasInfeasible = quarters.some((q) => q.infeasible);

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-200 flex items-baseline justify-between">
        <div>
          <Text className="text-sm font-semibold text-slate-800">
            Funnel math — what the engine needs each quarter
          </Text>
          <Text className="text-xs text-slate-500 mt-0.5">
            Scenario: <span className="font-medium text-slate-700">{scenario.label}</span>
          </Text>
        </div>
        {hasInfeasible && (
          <span className="text-xs font-medium text-red-600">
            Some quarters infeasible — starting pipe alone exceeds target
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <colgroup>
            <col className="w-[42%]" />
            {quarters.map((q) => (
              <col key={q.quarter} />
            ))}
          </colgroup>
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-5 py-2 text-left text-xs uppercase tracking-wide text-slate-500 font-medium">
                Stage
              </th>
              {quarters.map((q) => (
                <th
                  key={q.quarter}
                  className="px-4 py-2 text-right text-xs uppercase tracking-wide text-slate-500 font-medium"
                >
                  {q.quarter}
                  {q.infeasible && (
                    <span className="ml-1 text-[10px] font-semibold text-red-600">(infeasible)</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* SECTION: TOP OF FUNNEL — TWO TRIBUTARIES */}
            <SectionLabelRow label="Top-of-funnel inputs" />

            <StageRow
              label="MQLs needed"
              sublabel="Marketing's ask"
              quarters={quarters}
              format={(q) => intFmt(q.mqls)}
              tributary="marketing"
            />
            <RateRow rate={rateByEdge.mql_to_s0} label="MQL → S0" />
            <StageRow
              label="Marketing-sourced S0"
              quarters={quarters}
              format={(q) => intFmt(q.s0)}
              tributary="marketing"
              muted
            />
            <StageRow
              label="Outbound-sourced S0"
              sublabel="SDR + direct AE outreach · same-rate proxy (see note below)"
              quarters={quarters}
              // Display value derived from rounded total − rounded marketing so the three rows
              // visibly sum to the Total S0 shown below (preserves additivity under rounding).
              format={(q) => intFmt(Math.round(q.total_s0) - Math.round(q.s0))}
              tributary="outbound"
            />

            {/* SECTION: UNIFIED FUNNEL AFTER S0 */}
            <MergeRow />
            <StageRow
              label="Total S0 meetings booked"
              quarters={quarters}
              format={(q) => intFmt(q.total_s0)}
            />
            <RateRow rate={rateByEdge.s0_to_s1} label="S0 → S1" />
            <StageRow
              label="Total S1 meetings held"
              quarters={quarters}
              format={(q) => intFmt(q.total_s1)}
            />
            <RateRow rate={rateByEdge.s1_to_s2} label="S1 → S2" />
            <StageRow
              label="Total S2 SQOs"
              quarters={quarters}
              format={(q) => intFmt(q.total_s2)}
            />
            <AnnotationRow text={`@ ${formatMoney(Math.round(blendedAcv))} blended ACV`} />
            <StageRow
              label="Total pipeline created"
              quarters={quarters}
              format={(q) => formatMoney(q.created_pipe)}
            />

            {/* SECTION: WATERFALL → BOOKINGS */}
            <SectionLabelRow label="Waterfall → bookings" topBorder />
            <AnnotationRow text={`× ${pctFmt(scenario.win_rate_created)} win rate (new pipe)`} />
            <StageRow
              label="Wins from new pipe"
              quarters={quarters}
              format={(q) => formatMoney(q.won_from_created)}
              muted
            />
            <AnnotationRow
              text={`+ ${pctFmt(scenario.win_rate_starting)} of S2+ pipe carried into quarter`}
            />
            <StageRow
              label="Wins from carried pipe"
              quarters={quarters}
              format={(q) => formatMoney(q.won_from_starting)}
              muted
            />
            <tr className="border-t-2 border-slate-300 bg-slate-50">
              <td className="px-5 py-3 text-sm font-semibold text-slate-900">
                Projected bookings
              </td>
              {quarters.map((q) => (
                <td
                  key={q.quarter}
                  className="px-4 py-3 text-right tabular-nums text-sm font-semibold text-slate-900"
                >
                  {formatMoney(q.won_from_starting + q.won_from_created)}
                </td>
              ))}
            </tr>
            <tr className="bg-slate-50 border-b border-slate-200">
              <td className="px-5 py-1 text-[11px] text-slate-500">Plan target</td>
              {quarters.map((q) => (
                <td
                  key={q.quarter}
                  className="px-4 py-1 text-right tabular-nums text-[11px] text-slate-500"
                >
                  {formatMoney(q.bookings_target)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <div className="px-5 py-2 border-t border-slate-200 bg-slate-50">
        <Text className="text-[11px] text-slate-500">
          <span className="font-medium text-slate-600">Same-rate proxy:</span> Outbound tributary
          is modeled with the same S0→S1 and S1→S2 rates as marketing. If real outbound converts
          better than marketing (plausible — pre-qualified before booking), this row overstates
          required outbound volume. If outbound converts{" "}
          <em>worse</em>, it understates. Treat it as a same-rate planning proxy, not a hard
          target, until outbound rates are fit separately.
        </Text>
      </div>
    </Card>
  );
}

function StageRow({
  label,
  sublabel,
  quarters,
  format,
  muted = false,
  tributary,
}: {
  label: string;
  sublabel?: string;
  quarters: QuarterTargets[];
  format: (q: QuarterTargets) => string;
  muted?: boolean;
  tributary?: "marketing" | "outbound";
}) {
  const tributaryDot =
    tributary === "marketing"
      ? "bg-blue-500"
      : tributary === "outbound"
        ? "bg-amber-500"
        : null;
  return (
    <tr className="border-t border-slate-100">
      <td
        className={`px-5 py-2 ${
          muted ? "text-slate-600" : "font-medium text-slate-800"
        }`}
      >
        <div className="flex items-start gap-2">
          {tributaryDot && (
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full mt-2 shrink-0 ${tributaryDot}`}
              aria-hidden
            />
          )}
          <div>
            {label}
            {sublabel && (
              <div className="text-[10px] font-normal text-slate-500 mt-0.5">{sublabel}</div>
            )}
          </div>
        </div>
      </td>
      {quarters.map((q) => (
        <td
          key={q.quarter}
          className={`px-4 py-2 text-right tabular-nums align-top ${
            muted ? "text-slate-600" : "font-medium text-slate-900"
          }`}
        >
          {format(q)}
        </td>
      ))}
    </tr>
  );
}

function SectionLabelRow({ label, topBorder = false }: { label: string; topBorder?: boolean }) {
  return (
    <tr className={topBorder ? "border-t border-slate-200" : ""}>
      <td colSpan={99} className="px-5 pt-3 pb-1">
        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
          {label}
        </span>
      </td>
    </tr>
  );
}

function MergeRow() {
  return (
    <tr>
      <td colSpan={99} className="pl-10 pr-5 py-1">
        <span className="text-[11px] text-slate-400 inline-flex items-center gap-1.5">
          <span className="font-mono text-slate-500">└┬┘</span>
          <span>tributaries merge — one funnel from here</span>
        </span>
      </td>
    </tr>
  );
}

function RateRow({
  rate,
  label,
}: {
  rate: RateProvenance;
  label: string;
}) {
  return (
    <tr>
      <td colSpan={99} className="pl-10 pr-5 py-1">
        <span className="text-[11px] text-slate-400 inline-flex items-center gap-1.5">
          <span className="font-mono">×</span>
          <span className="tabular-nums font-medium text-slate-500">
            <RateProvenancePopover label={label} rate={rate}>
              {pctFmt(rate.value)}
            </RateProvenancePopover>
          </span>
          <span>{label}</span>
        </span>
      </td>
    </tr>
  );
}

function AnnotationRow({ text }: { text: string }) {
  return (
    <tr>
      <td colSpan={99} className="pl-10 pr-5 py-1">
        <span className="text-[11px] text-slate-400">{text}</span>
      </td>
    </tr>
  );
}

function intFmt(n: number): string {
  return Math.round(n).toLocaleString();
}

function pctFmt(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}
