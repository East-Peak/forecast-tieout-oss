import { Bar, Cell, ComposedChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { PlotRow } from "../../binding/chartData";
import { AXIS_STYLE, CHART_COLORS } from "../../lib/chartTheme";
import { formatValue, signOf } from "../../lib/format";

/**
 * One row's bars, drawn by their own small chart on a scale the page shares: every row of every group is given the
 * same `domain`, so a bar's length means the same dollars wherever it stands, and the row sits beside its own table
 * cells whatever height they take. Green is more booked and red is less, the two colors the app already uses for
 * ahead and shortfall. A gap in the file is a gap in the chart.
 */
const MARGIN = { top: 4, right: 12, bottom: 4, left: 12 } as const;
const colorOf = (value: unknown) => (typeof value === "number" && signOf(value) < 0 ? CHART_COLORS.negative : CHART_COLORS.positive);

export function BarCell({ row, keys, domain, label }: { row: PlotRow; keys: readonly string[]; domain: [number, number]; label: string }) {
  return (
    <div className="relative h-16 xl:absolute xl:inset-0 xl:h-auto" role="img" aria-label={label} data-testid="bar-cell">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart layout="vertical" data={[row]} margin={MARGIN} barGap={3} barCategoryGap="12%">
          <XAxis type="number" domain={domain} hide />
          <YAxis type="category" dataKey="period" hide />
          <ReferenceLine x={0} stroke={CHART_COLORS.muted} />
          {keys.map((key) => (
            <Bar key={key} dataKey={key} maxBarSize={16} isAnimationActive={false}>
              <Cell fill={colorOf(row[key])} />
            </Bar>
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The scale the rows share, drawn once at the head of a group: the same domain and the same margins as every row's chart. */
export function AxisHeader({ domain }: { domain: [number, number] }) {
  return (
    <div className="h-9 w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart layout="vertical" data={[]} margin={{ ...MARGIN, top: 0, bottom: 0 }}>
          <XAxis
            type="number"
            domain={domain}
            tickCount={5}
            tickFormatter={(v: number) => formatValue("usd-short", v)}
            tick={AXIS_STYLE.tick}
            axisLine={AXIS_STYLE.axisLine}
            tickLine={false}
            height={30}
          />
          <YAxis type="category" hide />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
