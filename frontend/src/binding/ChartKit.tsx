import { useMemo } from "react";
import type { ReactNode } from "react";
import { CHART_COLORS } from "../lib/chartTheme";
import { Bound, bind, useBindingContext } from "./Bound";
import { buildChart, pointFor } from "./chartData";
import type { PlotRow, SeriesSpec } from "./chartData";

/**
 * What every chart on a screen shares. `usePlot` builds the plotted rows from the declared series
 * (and nowhere else); the chart that draws them also writes them to `data-plotted`, so a test can
 * compare what was drawn with what the file holds. Tooltips read each value back from the file by
 * the same declared path, through Bound.
 */
export function usePlot(specs: readonly SeriesSpec[]): { periods: string[]; rows: PlotRow[] } {
  const { files } = useBindingContext();
  return useMemo(() => buildChart(files.report, [...specs]), [files.report, specs]);
}

export interface LegendItem {
  label: string;
  color: string;
  /** a band's thin edge, where it has one */
  outline?: string;
  kind: "bar" | "line" | "dash" | "band" | "tick";
}

export function ChartLegend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-600" data-testid="chart-legend">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block"
            style={
              item.kind === "bar"
                ? { width: 10, height: 10, borderRadius: 2, background: item.color }
                : item.kind === "band"
                  ? { width: 14, height: 10, borderRadius: 2, background: item.color, border: `1px solid ${item.outline ?? item.color}` }
                  : item.kind === "tick"
                    ? { width: 14, height: 3, background: item.color }
                    : {
                        width: 16,
                        height: 0,
                        borderTop: `2px ${item.kind === "dash" ? "dashed" : "solid"} ${item.color}`,
                      }
            }
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

interface TooltipProps {
  chartId: string;
  specs: readonly SeriesSpec[];
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<{ dataKey?: string | number | ((o: unknown) => unknown) | undefined; value?: unknown }>;
  periodFormat: (period: string) => string;
  /** more under the rows for the hovered period (bound values, like the rows) */
  extra?: (period: string) => ReactNode;
}

const unitOf = (spec: SeriesSpec) => (spec.format === "quantity" ? "quantity" : "usd");

/** The hover card. Its figures are read from the file at each series' declared path, not taken from the plotted numbers. */
export function ChartTooltip({ chartId, specs, active, label, payload, periodFormat, extra }: TooltipProps) {
  if (!active || !payload || label === undefined) return null;
  const period = String(label);
  const more = extra?.(period);
  const shown = payload.filter((p) => typeof p.dataKey === "string" && p.value !== null && p.value !== undefined);
  const seen = new Set<string>();
  const lines: ReactNode[] = [];
  for (const entry of shown) {
    const spec = specs.find((s) => s.key === entry.dataKey);
    if (!spec || seen.has(spec.key)) continue;
    seen.add(spec.key);
    const path = pointFor(spec, period);
    const id = `${chartId}.${spec.key}`;
    lines.push(
      <div key={spec.key} className="flex items-baseline justify-between gap-4" data-tooltip-row={spec.key}>
        <span className="text-slate-500">{spec.label}</span>
        <span className="font-medium text-slate-900">
          {spec.kind === "range" ? (
            <>
              <Bound binding={bind({ id: `${id}.low`, path: `${path}/0`, unit: unitOf(spec), format: spec.format ?? "usd-short" })} />
              {" to "}
              <Bound binding={bind({ id: `${id}.high`, path: `${path}/1`, unit: unitOf(spec), format: spec.format ?? "usd-short" })} />
            </>
          ) : (
            <Bound binding={bind({ id, path, unit: unitOf(spec), format: spec.format ?? "usd-short" })} />
          )}
        </span>
      </div>,
    );
  }
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md"
      data-testid="chart-tooltip"
      data-chart={chartId}
    >
      <div className="mb-1 font-semibold text-slate-900" data-exempt="period-label">
        {periodFormat(period)}
      </div>
      <div className="space-y-0.5">{lines}</div>
      {more ? <div className="mt-1 border-t border-slate-100 pt-1 text-slate-500" data-testid="tooltip-extra">{more}</div> : null}
    </div>
  );
}

export const SERIES_COLORS = {
  booked: CHART_COLORS.positive,
  fitted: CHART_COLORS.brand,
  band: CHART_COLORS.accent,
  target: CHART_COLORS.brand,
} as const;

/** The two ranges, the same on every chart that draws them: a mid green at moderate opacity, and a lighter one behind it with a thin pale edge. */
export const RANGE_STYLE = {
  range80: { fill: CHART_COLORS.accent, fillOpacity: 0.5 },
  range95: { fill: CHART_COLORS.accent, fillOpacity: 0.18, stroke: CHART_COLORS.accentTint, strokeWidth: 1 },
  legend80: "rgba(46,158,99,0.5)",
  legend95: "rgba(46,158,99,0.18)",
} as const;
