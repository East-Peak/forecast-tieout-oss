import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesSpec } from "../../binding/chartData";
import { ChartLegend, ChartTooltip, usePlot } from "../../binding/ChartKit";
import type { LegendItem } from "../../binding/ChartKit";
import { Card } from "../../components/ui";
import { AXIS_STYLE, CHART_COLORS, CHART_SERIES, GRID_STYLE } from "../../lib/chartTheme";
import { formatValue } from "../../lib/format";
import { SERIES } from "./bindings";

const CHART_ID = "pipeline-quarters";

/** For each quarter still to come: the pipeline the model expects to be created, and the extra required on top (nothing where no amount helps). */
export function QuarterChart() {
  const specs = useMemo<SeriesSpec[]>(() => [SERIES.expected, SERIES.required], []);
  const { rows } = usePlot(specs);
  const legend: LegendItem[] = [
    { label: SERIES.expected.label, color: CHART_COLORS.accentTint, kind: "bar" },
    { label: SERIES.required.label, color: CHART_COLORS.capacity, kind: "bar" },
  ];
  return (
    <Card className="p-4 sm:p-5" data-testid="chart-container" data-chart={CHART_ID}>
      <h3 className="mb-1 text-sm font-semibold text-ft-brand">Pipeline to create, quarter by quarter</h3>
      <p className="mb-4 text-xs text-slate-500">
        A quarter where no amount of extra pipeline helps has no second bar: the table says why.
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
          <XAxis dataKey="period" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
          <YAxis tickFormatter={(v: number) => formatValue("usd-short", v)} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={64} />
          <Tooltip
            content={<ChartTooltip chartId={CHART_ID} specs={specs} periodFormat={(p) => p} />}
            cursor={{ fill: CHART_COLORS.lightGray }}
          />
          <Bar dataKey="expected" {...CHART_SERIES.rampingBar} maxBarSize={48} />
          <Bar dataKey="required" fill={CHART_COLORS.capacity} radius={[2, 2, 0, 0]} isAnimationActive={false} maxBarSize={48} />
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend items={legend} />
    </Card>
  );
}
