// Shared Recharts styling to match ngrok-level polish

export const CHART_COLORS = {
  blue: "#2563eb",        // Primary data (existing pipeline)
  emerald: "#059669",     // Secondary data (future pipeline)
  red: "#dc2626",         // Targets, gaps
  amber: "#d97706",       // Capacity, warnings
  gray: "#94a3b8",        // Muted/reference lines
  lightGray: "#f1f5f9",   // Grid lines (very subtle)
} as const;

export const AXIS_STYLE = {
  tick: { fontSize: 11, fill: "#64748b", fontFamily: "'Inter', system-ui, sans-serif" },
  axisLine: { stroke: "#e2e8f0" },
} as const;

export const GRID_STYLE = {
  strokeDasharray: "none",  // solid, not dashed — cleaner
  stroke: "#f1f5f9",        // very subtle
  horizontal: true,
  vertical: false,          // no vertical gridlines
} as const;

export const TOOLTIP_STYLE = {
  contentStyle: {
    fontSize: 12,
    fontFamily: "'Inter', system-ui, sans-serif",
    borderRadius: 8,
    border: "1px solid #e2e8f0",
    boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
    padding: "8px 12px",
  },
  labelStyle: { fontWeight: 600, marginBottom: 4 },
} as const;

export const LEGEND_STYLE = {
  iconSize: 8,
  wrapperStyle: { fontSize: 12, fontFamily: "'Inter', system-ui, sans-serif", paddingTop: 8 },
} as const;

export function currencyFormatter(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function currencyTooltipFormatter(value: number, name: string): [string, string] {
  return [currencyFormatter(value), name];
}
