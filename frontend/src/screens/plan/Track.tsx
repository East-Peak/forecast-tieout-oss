import type { ReactNode } from "react";
import { Bar, Cell, ComposedChart, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { PlotRow } from "../../binding/chartData";
import { CHART_COLORS } from "../../lib/chartTheme";

/**
 * One row's track: its bars on a zero line, drawn on a scale the page shares, so that the zero line stands at the same
 * place in every row and a bar's length means the same dollars in each. Every bar is a span with its left end first
 * (the adapter's "bar"), green where it runs right of zero and red where it runs left. The figure at each bar's end is
 * the caller's own bound element, set in a box that starts at the bar's far end and is placed by the browser's layout,
 * so no position is calculated here. A gap in the file is no bar.
 */
const MARGIN = { top: 4, right: 4, bottom: 4, left: 4 } as const;

const isBelowZero = (value: unknown) => Array.isArray(value) && value[0] < 0;
const fillOf = (value: unknown) => (isBelowZero(value) ? CHART_COLORS.negative : CHART_COLORS.positive);

interface LabelProps {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
}

export function Track({ row, keys, domain, label, marks }: { row: PlotRow; keys: readonly string[]; domain: [number, number]; label: string; marks: Record<string, ReactNode> }) {
  return (
    <div className="relative h-full w-full [&_svg]:overflow-visible" role="img" aria-label={label} data-testid="track">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart layout="vertical" data={[row]} margin={MARGIN} barGap={4} barCategoryGap="8%">
          <XAxis type="number" domain={domain} hide />
          <YAxis type="category" dataKey="period" hide />
          <ReferenceLine x={0} stroke={CHART_COLORS.muted} />
          {keys.map((key) => (
            <Bar key={key} dataKey={key} maxBarSize={22} isAnimationActive={false}>
              <Cell fill={fillOf(row[key])} />
              <LabelList
                dataKey={key}
                content={(p: LabelProps) => (
                  <foreignObject x={p.x} y={p.y} width={p.width} height={p.height} style={{ overflow: "visible" }}>
                    <div className="relative h-full w-full">
                      <div
                        className={`absolute top-1/2 -translate-y-1/2 whitespace-nowrap leading-tight ${isBelowZero(row[key]) ? "right-full pr-1.5 text-right" : "left-full pl-1.5"}`}
                      >
                        {marks[key]}
                      </div>
                    </div>
                  </foreignObject>
                )}
              />
            </Bar>
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
