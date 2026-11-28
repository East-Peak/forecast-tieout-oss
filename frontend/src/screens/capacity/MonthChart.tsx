import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useBindingContext } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";
import { ChartLegend, ChartTooltip, usePlot } from "../../binding/ChartKit";
import type { LegendItem } from "../../binding/ChartKit";
import { Card } from "../../components/ui";
import { AXIS_STYLE, CHART_COLORS, CHART_SERIES, GRID_STYLE } from "../../lib/chartTheme";
import { formatMonthTick, formatValue } from "../../lib/format";
import { SERIES } from "./bindings";

const CHART_ID = "capacity-months";

/** Heads and ramped equivalents by month, past and forward, with the headcount target where the profile gives one. */
export function MonthChart() {
  const { files } = useBindingContext();
  const specs = useMemo<SeriesSpec[]>(() => [SERIES.ramped, SERIES.heads, SERIES.target], []);
  const { rows } = usePlot(specs);
  const asOfMonth = files.report.inputs.as_of.slice(0, 7);
  const legend: LegendItem[] = [
    { label: SERIES.ramped.label, color: CHART_COLORS.accentTint, kind: "bar" },
    { label: SERIES.heads.label, color: CHART_COLORS.brand, kind: "line" },
    { label: SERIES.target.label, color: CHART_COLORS.slate, kind: "dash" },
  ];
  return (
    <Card className="p-4 sm:p-5" data-testid="chart-container" data-chart={CHART_ID}>
      <h3 className="mb-1 text-sm font-semibold text-ft-brand">Heads and ramped equivalents, by month</h3>
      <p className="mb-4 max-w-4xl text-xs text-slate-500">
        A year of history to the left of the as-of line, a year of forecast to the right. A head ramps over the months after the
        start; the headcount target is a comparison line and never creates a hire.
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
          <XAxis dataKey="period" tickFormatter={formatMonthTick} tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
          <YAxis tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={44} />
          <Tooltip
            content={<ChartTooltip chartId={CHART_ID} specs={specs} periodFormat={(p) => formatValue("month", p)} />}
            cursor={{ stroke: CHART_COLORS.gray }}
          />
          <ReferenceLine x={asOfMonth} stroke={CHART_COLORS.muted} strokeDasharray="3 3" label={{ value: "As of", position: "insideTopRight", fill: CHART_COLORS.muted, fontSize: 11 }} />
          <Bar dataKey="ramped" {...CHART_SERIES.rampingBar} maxBarSize={22} />
          <Line dataKey="heads" type="monotone" {...CHART_SERIES.planLine} />
          <Line dataKey="target" type="monotone" {...CHART_SERIES.baselineLine} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend items={legend} />
    </Card>
  );
}
