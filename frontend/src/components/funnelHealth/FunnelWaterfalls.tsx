import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card } from "../ui";
import { SectionHeader } from "../workbook";
import {
  AXIS_STYLE,
  GRID_STYLE,
  TOOLTIP_STYLE,
  LEGEND_STYLE,
} from "../../lib/chartTheme";
import type { FunnelHealthWaterfalls } from "../../lib/funnelHealthViewModel";

interface FunnelWaterfallsProps {
  waterfalls: FunnelHealthWaterfalls;
}

export function FunnelWaterfalls({ waterfalls }: FunnelWaterfallsProps) {
  return (
    <>
      <SectionHeader
        title="Funnel Waterfall: Plan vs Trajectory"
        subtitle="Grouped bar comparison of weekly funnel activity rates."
      />
      {waterfalls.quarters.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {waterfalls.quarters.map((quarter) => (
            <Card
              key={quarter.quarter}
              className="p-5"
              data-testid="chart-container"
              data-chart-title={`Funnel Waterfall ${quarter.quarter}`}
              data-primary-series="trajectory"
              data-primary-values={JSON.stringify(quarter.primaryValues)}
            >
              <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-3">
                {quarter.quarter}
              </h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={quarter.data}>
                  <CartesianGrid
                    horizontal={GRID_STYLE.horizontal}
                    vertical={GRID_STYLE.vertical}
                    stroke={GRID_STYLE.stroke}
                    strokeDasharray={GRID_STYLE.strokeDasharray}
                  />
                  <XAxis
                    dataKey="stage"
                    tick={AXIS_STYLE.tick}
                    axisLine={AXIS_STYLE.axisLine}
                    tickLine={false}
                  />
                  <YAxis
                    tick={AXIS_STYLE.tick}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE.contentStyle}
                    labelStyle={TOOLTIP_STYLE.labelStyle}
                  />
                  <Legend
                    iconSize={LEGEND_STYLE.iconSize}
                    wrapperStyle={LEGEND_STYLE.wrapperStyle}
                  />
                  <Bar
                    dataKey="plan"
                    fill="#94a3b8"
                    name="Top-Down Plan"
                    radius={[2, 2, 0, 0]}
                    isAnimationActive={false}
                  />
                  <Bar
                    dataKey="trajectory"
                    fill="#2563eb"
                    name="Trajectory"
                    radius={[2, 2, 0, 0]}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-500">{waterfalls.emptyMessage}</p>
        </div>
      )}
    </>
  );
}
