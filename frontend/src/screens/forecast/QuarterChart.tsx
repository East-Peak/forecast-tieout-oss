import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesSpec } from "../../binding/chartData";
import { ChartLegend, ChartTooltip, SERIES_COLORS, usePlot } from "../../binding/ChartKit";
import { Card } from "../../components/ui";
import { AXIS_STYLE, CHART_COLORS, CHART_SERIES, GRID_STYLE } from "../../lib/chartTheme";
import { formatValue } from "../../lib/format";
import { quarterSeries } from "./bindings";

const QUARTER_CHART_ID = "quarters";

export function QuarterChart({ fittedAvailable, planned }: { fittedAvailable: boolean; planned: boolean }) {
  const S = useMemo(() => quarterSeries(planned), [planned]);
  const specs = useMemo<SeriesSpec[]>(
    () => [S.target, ...(fittedAvailable ? [S.expected, S.range80] : [])],
    [S, fittedAvailable],
  );
  const { rows } = usePlot(specs);
  return (
    <Card className="p-4 sm:p-5" data-testid="chart-container" data-chart={QUARTER_CHART_ID}>
      <h3 className="mb-1 text-sm font-semibold text-ft-brand">Each quarter against its target</h3>
      <p className="mb-4 text-xs text-slate-500">
        Expected bookings per quarter, with the range of each open quarter beside it. A closed quarter has no range. Open a quarter in the table below for its range.
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
          <XAxis dataKey="period" tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} />
          <YAxis tickFormatter={(v: number) => formatValue("usd-short", v)} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={56} />
          <Tooltip content={<ChartTooltip chartId={QUARTER_CHART_ID} specs={specs} periodFormat={(p) => p} />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
          {fittedAvailable ? (
            <>
              <Bar dataKey="expected" fill={SERIES_COLORS.fitted} fillOpacity={0.85} radius={[2, 2, 0, 0]} maxBarSize={44} isAnimationActive={false} />
              <Bar dataKey="range80" fill={CHART_COLORS.brand} fillOpacity={0.55} radius={2} maxBarSize={10} isAnimationActive={false} />
            </>
          ) : null}
          <Line dataKey="target" {...CHART_SERIES.planLine} strokeDasharray="4 3" dot={{ r: 3, fill: SERIES_COLORS.target }} type="linear" />
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend
        items={[
          ...(fittedAvailable
            ? [
                { label: "Expected", color: SERIES_COLORS.fitted, kind: "bar" as const },
                { label: "80% range", color: "rgba(18,61,43,0.55)", kind: "bar" as const },
              ]
            : []),
          { label: "Target", color: SERIES_COLORS.target, kind: "dash" },
        ]}
      />
    </Card>
  );
}
