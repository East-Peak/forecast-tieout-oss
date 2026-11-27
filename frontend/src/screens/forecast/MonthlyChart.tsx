import { useMemo } from "react";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bound, useBindingContext } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";
import { ChartLegend, ChartTooltip, SERIES_COLORS, usePlot } from "../../binding/ChartKit";
import type { LegendItem } from "../../binding/ChartKit";
import { Card } from "../../components/ui";
import { AXIS_STYLE, CHART_COLORS, CHART_SERIES, GRID_STYLE } from "../../lib/chartTheme";
import { formatMonthTick, formatValue } from "../../lib/format";
import { PLANNED, SIGNED, monthlySeries } from "./bindings";

const MONTHLY_CHART_ID = "monthly";

/** Which of the three forecasts the report says are available (a missing forecast is not drawn as zeros). */
export interface Availability {
  fitted: boolean;
  stage: boolean;
  runRate: boolean;
}

export function MonthlyChart({ available, planned }: { available: Availability; planned: boolean }) {
  const { files } = useBindingContext();
  const S = useMemo(() => monthlySeries(planned), [planned]);
  const specs = useMemo<SeriesSpec[]>(
    () => [
      S.booked,
      ...(available.fitted ? [S.band95, S.band80, ...(planned ? [S.signed] : []), S.fitted] : []),
      ...(available.stage ? [S.stage] : []),
      ...(available.runRate ? [S.runRate] : []),
    ],
    [S, available.fitted, available.stage, available.runRate, planned],
  );
  const { rows } = usePlot(specs);
  // the month the report was run in: history to its left, forecast to its right
  const asOfMonth = files.report.inputs.as_of.slice(0, 7);
  const legend: LegendItem[] = [
    { label: S.booked.label, color: SERIES_COLORS.booked, kind: "bar" },
    ...(available.fitted
      ? [
          { label: S.fitted.label, color: SERIES_COLORS.fitted, kind: "line" as const },
          ...(planned ? [{ label: S.signed.label, color: CHART_COLORS.brand, kind: "dash" as const }] : []),
          { label: S.band80.label, color: "rgba(46,158,99,0.34)", kind: "band" as const },
          { label: S.band95.label, color: "rgba(46,158,99,0.14)", kind: "band" as const },
        ]
      : []),
    ...(available.stage ? [{ label: S.stage.label, color: SERIES_COLORS.stage, kind: "dash" as const }] : []),
    ...(available.runRate ? [{ label: S.runRate.label, color: SERIES_COLORS.runRate, kind: "dash" as const }] : []),
  ];

  return (
    <Card className="p-4 sm:p-5" data-testid="chart-container" data-chart={MONTHLY_CHART_ID}>
      <h3 className="mb-1 text-sm font-semibold text-ft-brand">Bookings by month, and the forecasts</h3>
      <p className="mb-4 text-xs text-slate-500">
        History to the left of the as-of line, forecast to the right. Only the fitted model has a range.
        {available.fitted ? (
          <>
            {" "}
            The bands are <Bound binding={planned ? PLANNED.bandsLabel : SIGNED.bandsLabel} />.
          </>
        ) : null}
      </p>
      <p className="-mt-3 mb-4 text-xs text-slate-500" data-testid="baseline-note">
        The two dotted lines are the simple yardsticks the fitted model is scored against. The stage-weighted line falls away because today&apos;s open deals close out first and only a thin flow of new pipeline follows them.
      </p>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
          <XAxis dataKey="period" tickFormatter={formatMonthTick} tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
          <YAxis tickFormatter={(v: number) => formatValue("usd-short", v)} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={56} />
          <Tooltip
            content={<ChartTooltip chartId={MONTHLY_CHART_ID} specs={specs} periodFormat={(p) => formatValue("month", p)} />}
            cursor={{ stroke: CHART_COLORS.gray }}
          />
          <ReferenceLine x={asOfMonth} stroke={CHART_COLORS.muted} strokeDasharray="3 3" label={{ value: "As of", position: "insideTopRight", fill: CHART_COLORS.muted, fontSize: 11 }} />
          <Bar dataKey="booked" fill={SERIES_COLORS.booked} radius={[2, 2, 0, 0]} maxBarSize={22} isAnimationActive={false} />
          {available.fitted ? (
            <>
              <Area dataKey="band95" stroke="none" fill={CHART_COLORS.accent} fillOpacity={0.1} isAnimationActive={false} connectNulls={false} />
              <Area dataKey="band80" stroke="none" fill={CHART_COLORS.accent} fillOpacity={0.26} isAnimationActive={false} connectNulls={false} />
              {planned ? (
                <Line dataKey="signed" type="monotone" {...CHART_SERIES.planLine} strokeDasharray="5 3" strokeWidth={1.5} />
              ) : null}
              <Line dataKey="fitted" type="monotone" {...CHART_SERIES.expectedLine} />
            </>
          ) : null}
          {available.stage ? <Line dataKey="stage" type="monotone" {...CHART_SERIES.baselineLine} /> : null}
          {available.runRate ? (
            <Line dataKey="runRate" type="monotone" {...CHART_SERIES.baselineLine} stroke={SERIES_COLORS.runRate} strokeDasharray="2 3" />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend items={legend} />
    </Card>
  );
}
