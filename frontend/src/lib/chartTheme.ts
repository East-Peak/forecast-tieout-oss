export const CHART_COLORS = {
  brand: "#123d2b",
  accent: "#2e9e63",
  accentTint: "#8fdcb0",
  accentSoft: "rgba(66,193,126,0.15)",
  capacity: "#d97706",
  positive: "#15803d",
  negative: "#dc2626",
  slate: "#475569",
  muted: "#64748b",
  gray: "#94a3b8",
  lightGray: "#f1f5f9",
  dropOff: "#e2e8f0",
} as const;

export const AXIS_STYLE = {
  tick: { fontSize: 11, fill: CHART_COLORS.muted, fontFamily: "Inter, system-ui, sans-serif" },
  axisLine: { stroke: "#e2e8f0" },
} as const;

export const GRID_STYLE = {
  strokeDasharray: "none",
  stroke: CHART_COLORS.lightGray,
  horizontal: true,
  vertical: false,
} as const;

export const TOOLTIP_STYLE = {
  contentStyle: {
    fontSize: 12,
    fontFamily: "Inter, system-ui, sans-serif",
    borderRadius: 8,
    border: "1px solid #e2e8f0",
    boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
    padding: "8px 12px",
  },
  labelStyle: { fontWeight: 600, marginBottom: 4 },
} as const;

export const LEGEND_STYLE = {
  iconSize: 8,
  wrapperStyle: { fontSize: 12, fontFamily: "Inter, system-ui, sans-serif", paddingTop: 8 },
} as const;

export const CHART_SERIES = {
  actualBar: {
    fill: CHART_COLORS.positive,
    radius: [2, 2, 0, 0] as [number, number, number, number],
    isAnimationActive: false,
  },
  lossBar: {
    fill: CHART_COLORS.negative,
    radius: [0, 0, 2, 2] as [number, number, number, number],
    isAnimationActive: false,
  },
  pipelineBar: {
    fill: CHART_COLORS.accent,
    radius: [2, 2, 0, 0] as [number, number, number, number],
    isAnimationActive: false,
  },
  existingArea: {
    fill: CHART_COLORS.accent,
    stroke: CHART_COLORS.accent,
    strokeWidth: 2,
    fillOpacity: 0.68,
    isAnimationActive: false,
  },
  futureArea: {
    fill: CHART_COLORS.accentTint,
    stroke: CHART_COLORS.accentTint,
    strokeWidth: 2,
    fillOpacity: 0.72,
    isAnimationActive: false,
  },
  expectedLine: {
    stroke: CHART_COLORS.accent,
    strokeWidth: 2,
    dot: false,
    isAnimationActive: false,
  },
  planLine: {
    stroke: CHART_COLORS.brand,
    strokeWidth: 2,
    dot: false,
    isAnimationActive: false,
  },
  capacityLine: {
    stroke: CHART_COLORS.capacity,
    strokeWidth: 2,
    strokeDasharray: "6 3",
    dot: false,
    isAnimationActive: false,
  },
  baselineLine: {
    stroke: CHART_COLORS.slate,
    strokeWidth: 2,
    strokeDasharray: "6 3",
    dot: false,
    isAnimationActive: false,
  },
  rampedBar: {
    fill: CHART_COLORS.accent,
    radius: [2, 2, 0, 0] as [number, number, number, number],
    isAnimationActive: false,
  },
  rampingBar: {
    fill: CHART_COLORS.accentTint,
    radius: [2, 2, 0, 0] as [number, number, number, number],
    isAnimationActive: false,
  },
} as const;

export const REFERENCE_LINE_STYLE = {
  zero: { stroke: CHART_COLORS.gray, strokeWidth: 1 },
  projected: {
    stroke: CHART_COLORS.muted,
    strokeWidth: 2,
    label: { value: "Projected", position: "top", fill: CHART_COLORS.muted, fontSize: 11 },
  },
} as const;

export const SANKEY_COLORS = {
  marketing: CHART_COLORS.accent,
  outbound: CHART_COLORS.capacity,
  dropOff: CHART_COLORS.dropOff,
  totalS0: CHART_COLORS.muted,
  totalS1: CHART_COLORS.slate,
  totalS2: CHART_COLORS.brand,
  link: CHART_COLORS.dropOff,
  linkHover: CHART_COLORS.gray,
  label: CHART_COLORS.brand,
  labelMuted: CHART_COLORS.muted,
} as const;

export function currencyFormatter(v: number): string {
  return `$${(v / 1_000_000).toFixed(1)}M`;
}

export function currencyTooltipFormatter(value: number, name: string): [string, string] {
  return [currencyFormatter(value), name];
}
