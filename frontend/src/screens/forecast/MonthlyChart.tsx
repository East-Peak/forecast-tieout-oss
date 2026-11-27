import { useMemo } from "react";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesSpec } from "../../binding/chartData";
import { ChartLegend, ChartTooltip, SERIES_COLORS, usePlot } from "../../binding/ChartKit";
import type { LegendItem } from "../../binding/ChartKit";
import { Card } from "../../components/ui";
import { AXIS_STYLE, CHART_COLORS, CHART_SERIES, GRID_STYLE } from "../../lib/chartTheme";
import { formatMonthTick, formatValue } from "../../lib/format";
import { MONTHLY_SERIES } from "./bindings";

const MONTHLY_CHART_ID = "monthly";

/** Which of the three forecasts the report says are available (a missing forecast is not drawn as zeros). */
export interface Availability {
  fitted: boolean;
  stage: boolean;
  runRate: boolean;
}

export function MonthlyChart({ available }: { available: Availability }) {
  const specs = useMemo<SeriesSpec[]>(
    () => [
      MONTHLY_SERIES.booked,
      ...(available.fitted ? [MONTHLY_SERIES.band95, MONTHLY_SERIES.band80, MONTHLY_SERIES.fitted] : []),
      ...(available.stage ? [MONTHLY_SERIES.stage] : []),
      ...(available.runRate ? [MONTHLY_SERIES.runRate] : []),
    ],
    [available.fitted, available.stage, available.runRate],
  );
  const { rows } = usePlot(specs);
  const legend: LegendItem[] = [
    { label: "Booked", color: SERIES_COLORS.booked, kind: "bar" },
    ...(available.fitted
      ? [
          { label: MONTHLY_SERIES.fitted.label, color: SERIES_COLORS.fitted, kind: "line" as const },
          { label: MONTHLY_SERIES.band80.label, color: "rgba(46,158,99,0.38)", kind: "band" as const },
          { label: MONTHLY_SERIES.band95.label, color: "rgba(46,158,99,0.16)", kind: "band" as const },
        ]
      : []),
    ...(available.stage ? [{ label: MONTHLY_SERIES.stage.label, color: SERIES_COLORS.stage, kind: "dash" as const }] : []),
    ...(available.runRate ? [{ label: MONTHLY_SERIES.runRate.label, color: SERIES_COLORS.runRate, kind: "dash" as const }] : []),
  ];

  return (
    <Card
      className="p-5"
      data-testid="chart-container"
      data-chart={MONTHLY_CHART_ID}
      data-plotted={JSON.stringify(rows)}
    >
      <h3 className="mb-1 text-sm font-semibold text-ft-brand">Bookings by month, and the three forecasts</h3>
      <p className="mb-4 text-xs text-slate-500">
        Months booked to date, then each forecast by month. The fitted model carries a range; the two baselines are point
        forecasts and have none.
      </p>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid
            horizontal={GRID_STYLE.horizontal}
            vertical={GRID_STYLE.vertical}
            stroke={GRID_STYLE.stroke}
            strokeDasharray={GRID_STYLE.strokeDasharray}
          />
          <XAxis
            dataKey="period"
            tickFormatter={formatMonthTick}
            tick={AXIS_STYLE.tick}
            axisLine={AXIS_STYLE.axisLine}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={16}
          />
          <YAxis
            tickFormatter={(v: number) => formatValue("usd-short", v)}
            tick={AXIS_STYLE.tick}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            content={<ChartTooltip chartId={MONTHLY_CHART_ID} specs={specs} periodFormat={(p) => formatValue("month", p)} />}
            cursor={{ stroke: CHART_COLORS.gray }}
          />
          <Bar dataKey="booked" fill={SERIES_COLORS.booked} radius={[2, 2, 0, 0]} maxBarSize={22} isAnimationActive={false} />
          {available.fitted ? (
            <>
              <Area dataKey="band95" stroke="none" fill={CHART_COLORS.accent} fillOpacity={0.14} isAnimationActive={false} connectNulls={false} />
              <Area dataKey="band80" stroke="none" fill={CHART_COLORS.accent} fillOpacity={0.3} isAnimationActive={false} connectNulls={false} />
              <Line dataKey="fitted" type="monotone" {...CHART_SERIES.expectedLine} />
            </>
          ) : null}
          {available.stage ? (
            <Line dataKey="stage" type="monotone" {...CHART_SERIES.baselineLine} />
          ) : null}
          {available.runRate ? (
            <Line dataKey="runRate" type="monotone" {...CHART_SERIES.baselineLine} stroke={SERIES_COLORS.runRate} strokeDasharray="2 3" />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend items={legend} />
    </Card>
  );
}
