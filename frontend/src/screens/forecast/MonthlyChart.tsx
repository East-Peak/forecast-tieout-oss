import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bound, useBindingContext } from "../../binding/Bound";
import type { SeriesSpec } from "../../binding/chartData";
import { ChartLegend, ChartTooltip, RANGE_STYLE, SERIES_COLORS, usePlot } from "../../binding/ChartKit";
import type { LegendItem } from "../../binding/ChartKit";
import { Card } from "../../components/ui";
import { useDesktop } from "../../editor/YourPlanContext";
import { AXIS_STYLE, CHART_COLORS, GRID_STYLE } from "../../lib/chartTheme";
import { formatMonthTick, formatValue } from "../../lib/format";
import { B, PLANNED, SIGNED, monthlySeries } from "./bindings";

const MONTHLY_CHART_ID = "monthly";
/** Every month's column, range bars and tick share one slot and one width: a month is a month on both sides of the as-of line. */
/** (a phone's months are narrower: its slot is too, and the tick with it). */
const WIDE = { size: 14, overlap: -14, tick: 7, tickStart: -7 };
const NARROW = { size: 8, overlap: -8, tick: 5, tickStart: -5 };

/** Which forecasts the report says are available (a missing forecast is not drawn as zeros). */
export interface Availability {
  fitted: boolean;
}

/** The expected value of a forecast month: a short horizontal tick, crossing the range bars behind it. */
function Tick({ cx, cy, color, narrow }: { cx?: number; cy?: number; color: string; narrow: boolean }) {
  if (typeof cx !== "number" || typeof cy !== "number") return null;
  return (
    <g transform={`translate(${cx} ${cy})`} data-testid="expected-tick">
      <line x1={narrow ? NARROW.tickStart : WIDE.tickStart} x2={narrow ? NARROW.tick : WIDE.tick} y1={0} y2={0} stroke={color} strokeWidth={3} />
    </g>
  );
}

/** The as-of line's label: the date, a bound figure, set beside the line by the browser's layout. */
function AsOfLabel({ viewBox }: { viewBox?: { x?: number; y?: number } }) {
  return (
    <foreignObject x={viewBox?.x} y={viewBox?.y} width={1} height={1} style={{ overflow: "visible" }}>
      <div className="relative">
        <div className="absolute right-1.5 top-0 whitespace-nowrap text-[11px] text-slate-500">
          As of <Bound binding={B.asOfMarker} />
        </div>
      </div>
    </foreignObject>
  );
}

/**
 * Bookings by month: the months booked so far are columns from zero; each forecast month is a floating range, the 80%
 * range over the lighter 95% range of the same width, with the model's expected value as a tick across them. Nothing is
 * smoothed and nothing joins one month to the next. The ranges are the report's own [low, high] pairs, drawn as they are;
 * the dashed line stands on the boundary between the last booked month and the first forecast month.
 */
export function MonthlyChart({ available, planned }: { available: Availability; planned: boolean }) {
  const { files } = useBindingContext();
  const S = useMemo(() => monthlySeries(planned), [planned]);
  const specs = useMemo<SeriesSpec[]>(() => [S.booked, ...(available.fitted ? [S.band95, S.band80, ...(planned ? [S.signed] : []), S.fitted] : [])], [S, available.fitted, planned]);
  const { rows } = usePlot(specs);
  const narrow = !useDesktop();
  const slot = narrow ? NARROW : WIDE;
  const forecastMonths = files.report.forecasts.windows;
  const firstForecast = forecastMonths[0];
  const bandsLabel = planned ? PLANNED.bandsLabel : SIGNED.bandsLabel;
  const legend: LegendItem[] = [
    { label: S.booked.label, color: SERIES_COLORS.booked, kind: "bar" },
    ...(available.fitted
      ? [
          { label: S.fitted.label, color: SERIES_COLORS.fitted, kind: "tick" as const },
          ...(planned ? [{ label: S.signed.label, color: CHART_COLORS.slate, kind: "tick" as const }] : []),
          { label: S.band80.label, color: RANGE_STYLE.legend80, kind: "band" as const },
          { label: S.band95.label, color: RANGE_STYLE.legend95, outline: CHART_COLORS.accentTint, kind: "band" as const },
        ]
      : []),
  ];

  return (
    <Card className="p-4 sm:p-5" data-testid="chart-container" data-chart={MONTHLY_CHART_ID}>
      <h3 className="mb-1 text-sm font-semibold text-ft-brand">Bookings by month, and the forecast</h3>
      <p className="mb-1 text-xs text-slate-500">
        The ranges are for each month&apos;s bookings taken alone, not for the twelve months together.
        {available.fitted ? (
          <>
            {" "}
            The ranges are <Bound binding={bandsLabel} />.
          </>
        ) : null}
      </p>
      <p className="mb-4 text-xs text-slate-500" data-testid="baseline-note">
        Compare with the stage-weighted pipeline and the last twelve months&apos; pace in the verdict above and on Trust.
      </p>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }} barGap={slot.overlap} barSize={slot.size} barCategoryGap="20%" accessibilityLayer>
          <CartesianGrid horizontal={GRID_STYLE.horizontal} vertical={GRID_STYLE.vertical} stroke={GRID_STYLE.stroke} strokeDasharray={GRID_STYLE.strokeDasharray} />
          <XAxis dataKey="period" tickFormatter={formatMonthTick} tick={AXIS_STYLE.tick} axisLine={AXIS_STYLE.axisLine} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
          <YAxis tickFormatter={(v: number) => formatValue("usd-short", v)} tick={AXIS_STYLE.tick} axisLine={false} tickLine={false} width={56} />
          <Tooltip
            content={
              <ChartTooltip
                chartId={MONTHLY_CHART_ID}
                specs={specs}
                periodFormat={(p) => formatValue("month", p)}
                extra={(period) => (available.fitted && forecastMonths.includes(period) ? <Bound binding={bandsLabel} /> : null)}
              />
            }
            cursor={{ fill: "rgba(148,163,184,0.12)" }}
          />
          {available.fitted ? <ReferenceLine x={firstForecast} position="start" stroke={CHART_COLORS.muted} strokeDasharray="3 3" label={<AsOfLabel />} /> : null}
          <Bar dataKey="booked" fill={SERIES_COLORS.booked} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          {available.fitted ? (
            <>
              <Bar dataKey="band95" {...RANGE_STYLE.range95} isAnimationActive={false} />
              <Bar dataKey="band80" {...RANGE_STYLE.range80} isAnimationActive={false} />
              {planned ? <Line dataKey="signed" stroke="none" dot={<Tick color={CHART_COLORS.slate} narrow={narrow} />} activeDot={false} isAnimationActive={false} connectNulls={false} /> : null}
              <Line dataKey="fitted" stroke="none" dot={<Tick color={SERIES_COLORS.fitted} narrow={narrow} />} activeDot={false} isAnimationActive={false} connectNulls={false} />
            </>
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend items={legend} />
    </Card>
  );
}
