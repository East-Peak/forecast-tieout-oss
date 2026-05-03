import { useState } from "react";
import { ResponsiveContainer, Sankey, Tooltip } from "recharts";
import { Card, Text } from "../ui";
import { RateProvenancePopover } from "./RateProvenancePopover";
import type { QuarterTargets } from "../../types/targetSetter";
import type { RateProvenance } from "../../types/snapshot";

export interface FunnelSankeyProps {
  quarters: QuarterTargets[];
  /** Rate provenance keyed by stage transition, used for edge labels and popovers. */
  rateByEdge: {
    mql_to_s0: RateProvenance;
    outbound_to_s0: RateProvenance;
    s0_to_s1: RateProvenance;
    s1_to_s2: RateProvenance;
  };
}

/**
 * Sankey visualization of the two-tributary funnel, summed across the solve
 * scope (e.g., Q2–Q4 combined). Shows the merge at S0 and the conversion
 * drop-off through the rest of the funnel.
 *
 * Edge values are COUNTS at each stage (not MQL-ask-level). That means:
 * - MQL node's outbound flow is marketing_S0 (post-conversion count), not MQL count.
 * - This keeps Sankey edge widths proportional to actual volume at each stage.
 *
 * Conservation doesn't hold at S0→S1→S2 (classical funnel drop-off), which
 * is the point — Sankey visually shows the shrink through each rate.
 *
 * Edge labels: each edge shows a midpoint % label when linkWidth >= 6.
 * Edge provenance chip strip below the Sankey wraps each % in a
 * RateProvenancePopover so users can drill into the rate's source.
 */
export function FunnelSankey({ quarters, rateByEdge }: FunnelSankeyProps) {
  if (quarters.length === 0) return null;

  const sum = (key: keyof QuarterTargets): number =>
    quarters.reduce((acc, q) => acc + (q[key] as number), 0);

  const mqls = Math.round(sum("mqls"));
  const marketingS0 = Math.round(sum("s0"));
  const outboundS0 = Math.round(sum("outbound_s0"));
  const totalS0 = Math.round(sum("total_s0"));
  const totalS1 = Math.round(sum("total_s1"));
  const totalS2 = Math.round(sum("total_s2"));

  // MQLs that don't convert to S0 — rendered as a faded drop-off sink so the
  // Sankey honestly shows the MQL→S0 cohort shrink. Without this, recharts
  // would size the MQLs node at marketingS0 (the only flow out), which would
  // visually lie about the MQL pool.
  const mqlsDropOff = Math.max(0, mqls - marketingS0);

  // Recharts Sankey requires all link values > 0. Floor tiny flows.
  const safe = (n: number): number => (n > 0 ? n : 0.0001);

  const data = {
    nodes: [
      { name: "MQLs" },                // 0
      { name: "" },                    // 1 — drop-off sink (intentionally no label)
      { name: "Marketing S0" },        // 2
      { name: "Outbound S0" },         // 3
      { name: "Total S0" },            // 4
      { name: "Total S1" },            // 5
      { name: "Total S2 SQOs" },       // 6
    ],
    links: [
      { source: 0, target: 2, value: safe(marketingS0) },   // 0: MQLs → Marketing S0 (shows mql_to_s0 %)
      { source: 0, target: 1, value: safe(mqlsDropOff) },   // 1: MQLs → drop-off (no label)
      { source: 2, target: 4, value: safe(marketingS0) },   // 2: Marketing S0 → Total S0 (no label — pass-through)
      { source: 3, target: 4, value: safe(outboundS0) },    // 3: Outbound → Total S0 (no label — direct input)
      { source: 4, target: 5, value: safe(totalS1) },       // 4: Total S0 → Total S1 (shows s0_to_s1 %)
      { source: 5, target: 6, value: safe(totalS2) },       // 5: Total S1 → Total S2 (shows s1_to_s2 %)
    ],
  };

  // Parallel array to links[] — drives edge label + popover.
  // `null` means "don't show a label on this link" (for pass-throughs / direct inputs).
  const edgeMeta: Array<{ label: string; rate: RateProvenance } | null> = [
    { label: "MQL → S0", rate: rateByEdge.mql_to_s0 },  // 0
    null,                                                // 1: drop-off — hide
    null,                                                // 2: Marketing S0 → Total S0 pass-through
    null,                                                // 3: Outbound → Total S0 direct input
    { label: "S0 → S1", rate: rateByEdge.s0_to_s1 },    // 4
    { label: "S1 → S2", rate: rateByEdge.s1_to_s2 },    // 5
  ];

  // Filtered list for the chip strip (exclude null entries — no chip for pass-throughs).
  const edgeChips = edgeMeta.filter((m): m is { label: string; rate: RateProvenance } => m !== null);

  const scopeLabel = `${quarters[0].quarter}–${quarters[quarters.length - 1].quarter}`;

  return (
    <Card className="p-5">
      <div className="mb-3">
        <Text className="text-sm font-semibold text-slate-800">
          Funnel flow — {scopeLabel} combined
        </Text>
        <Text className="text-xs text-slate-500 mt-0.5">
          MQLs convert to Marketing S0; Outbound enters directly at S0. Unified funnel drops off
          through S0→S1→S2. Edge widths scale to count at each stage.
        </Text>
      </div>
      <div className="w-full" style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <Sankey
            data={data}
            nodeWidth={10}
            nodePadding={24}
            margin={{ top: 10, right: 140, bottom: 10, left: 60 }}
            link={<CustomLink edgeMeta={edgeMeta} />}
            node={
              <SankeyNode
                mqls={mqls}
                mqlsDropOff={mqlsDropOff}
                marketingS0={marketingS0}
                outboundS0={outboundS0}
                totalS0={totalS0}
                totalS1={totalS1}
                totalS2={totalS2}
              />
            }
          >
            <Tooltip />
          </Sankey>
        </ResponsiveContainer>
      </div>

      {/* Edge-provenance chip strip — only real conversion rates (MQL→S0, S0→S1, S1→S2) */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {edgeChips.map((e) => (
          <div key={e.label} className="inline-flex items-center gap-1">
            <span className="text-slate-500">{e.label}</span>
            <RateProvenancePopover label={e.label} rate={e.rate}>
              <span className="font-semibold text-slate-800">
                {(e.rate.value * 100).toFixed(1)}%
              </span>
            </RateProvenancePopover>
          </div>
        ))}
      </div>

      {/* Color-legend for the tributary nodes */}
      <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-blue-500" />
          Marketing tributary (MQL→S0)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-500" />
          Outbound tributary (SDR + direct AE)
        </span>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Custom link renderer — bezier path matching recharts default + midpoint % label
// ---------------------------------------------------------------------------

interface CustomLinkProps {
  sourceX?: number;
  sourceY?: number;
  sourceControlX?: number;
  targetX?: number;
  targetY?: number;
  targetControlX?: number;
  linkWidth?: number;
  index?: number;
  payload?: { target?: { name?: string } };
  edgeMeta: Array<{ label: string; rate: RateProvenance } | null>;
}

function CustomLink({
  sourceX = 0,
  sourceY = 0,
  sourceControlX = 0,
  targetX = 0,
  targetY = 0,
  targetControlX = 0,
  linkWidth = 0,
  index = 0,
  payload,
  edgeMeta,
}: CustomLinkProps) {
  const [hovered, setHovered] = useState(false);

  // Bezier path matching recharts' default Sankey link shape
  const d = `M ${sourceX},${sourceY} C ${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`;

  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;

  const meta = edgeMeta[index];
  const pct = meta ? Math.round(meta.rate.value * 100) : 0;
  const showLabel = linkWidth >= 6 && meta != null;

  // Drop-off link (target node name is empty) — hide entirely. The link still
  // exists in recharts' data so the source node is sized at the full cohort,
  // but we render nothing to keep the visual focused on the real flows.
  const isDropOff = payload?.target?.name === "";
  if (isDropOff) return null;

  return (
    <g>
      <path
        d={d}
        stroke={hovered ? "#94a3b8" : "#cbd5e1"}
        strokeOpacity={hovered ? 0.7 : 0.5}
        strokeWidth={linkWidth}
        fill="none"
        style={{ pointerEvents: "stroke", cursor: "default" }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {showLabel && (
        <text
          x={midX}
          y={midY}
          dy={4}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          fill="#1e293b"
          pointerEvents="none"
        >
          {pct}%
        </text>
      )}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Node renderer
// ---------------------------------------------------------------------------

interface SankeyNodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  payload?: { name?: string };
  mqls: number;
  mqlsDropOff: number;
  marketingS0: number;
  outboundS0: number;
  totalS0: number;
  totalS1: number;
  totalS2: number;
}

function SankeyNode(props: SankeyNodeProps) {
  const { x = 0, y = 0, width = 0, height = 0, index = 0, payload } = props;
  const name = payload?.name ?? "";

  // Assign colors per node index (matches data.nodes order in FunnelSankey)
  // 0: MQLs, 1: drop-off, 2: Marketing S0, 3: Outbound S0, 4: Total S0, 5: S1, 6: S2
  const colors = [
    "#3b82f6", // MQLs — blue (marketing tributary)
    "#e2e8f0", // drop-off — faded (nearly invisible)
    "#3b82f6", // Marketing S0 — blue
    "#f59e0b", // Outbound S0 — amber
    "#64748b", // Total S0 — slate
    "#475569", // Total S1 — slate
    "#334155", // Total S2 — slate
  ];
  const fill = colors[index] ?? "#64748b";

  // Pick the right count for the label, in same order as colors[]
  const counts = [
    props.mqls,
    props.mqlsDropOff,
    props.marketingS0,
    props.outboundS0,
    props.totalS0,
    props.totalS1,
    props.totalS2,
  ];
  const count = counts[index] ?? 0;

  // Hide the drop-off node entirely — no rect, no text.
  if (index === 1) return null;

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} rx={1.5} />
      <text
        x={x + width + 8}
        y={y + height / 2}
        dy={4}
        fontSize={12}
        fill="#334155"
        textAnchor="start"
      >
        <tspan fontWeight={600}>{name}</tspan>
        <tspan dx={6} fill="#64748b">
          {count.toLocaleString()}
        </tspan>
      </text>
    </g>
  );
}
