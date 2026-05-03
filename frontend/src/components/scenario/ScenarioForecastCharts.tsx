import { Card } from "../ui";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AXIS_STYLE,
  CHART_COLORS,
  GRID_STYLE,
  LEGEND_STYLE,
  TOOLTIP_STYLE,
  currencyFormatter,
  currencyTooltipFormatter,
} from "../../lib/chartTheme";

interface Props {
  monthlyChartData: Array<Record<string, number | string>>;
  cumulativeChartData: Array<Record<string, number | string>>;
  planMonthlyLabel: string;
  planNote: string | null;
  showPlanMonthly: boolean;
  showPlanCumulative: boolean;
}

export function ScenarioForecastCharts({
  monthlyChartData,
  cumulativeChartData,
  planMonthlyLabel,
  planNote,
  showPlanMonthly,
  showPlanCumulative,
}: Props) {
  return (
    <>
      <Card className="mb-6 p-5">
        <h3 className="text-sm font-semibold text-slate-900">Monthly Scenario vs Plan</h3>
        <p className="mt-1 text-xs text-slate-500">
          Existing inventory and future generation stay stacked, while the active scenario, modeled
          AE capacity, and monthly plan reference show whether the operating bet closes the gap.
        </p>
        {planNote ? <p className="mt-1 text-[11px] text-slate-500">{planNote}</p> : null}
        <div className="mt-4">
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={monthlyChartData}>
              <CartesianGrid
                horizontal={GRID_STYLE.horizontal}
                vertical={GRID_STYLE.vertical}
                stroke={GRID_STYLE.stroke}
                strokeDasharray={GRID_STYLE.strokeDasharray}
              />
              <XAxis
                dataKey="month"
                tick={AXIS_STYLE.tick}
                axisLine={AXIS_STYLE.axisLine}
                tickLine={false}
              />
              <YAxis
                tickFormatter={currencyFormatter}
                tick={AXIS_STYLE.tick}
                axisLine={false}
                tickLine={false}
                width={70}
              />
              <Tooltip
                formatter={currencyTooltipFormatter}
                contentStyle={TOOLTIP_STYLE.contentStyle}
                labelStyle={TOOLTIP_STYLE.labelStyle}
              />
              <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
              <Area
                type="monotone"
                dataKey="Existing Pipeline"
                stackId="bookings"
                fill={CHART_COLORS.blue}
                stroke={CHART_COLORS.blue}
                strokeWidth={2}
                fillOpacity={0.72}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="Future Pipeline"
                stackId="bookings"
                fill={CHART_COLORS.emerald}
                stroke={CHART_COLORS.emerald}
                strokeWidth={2}
                fillOpacity={0.72}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="Scenario Forecast"
                stroke={CHART_COLORS.amber}
                strokeWidth={2.5}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="AE Capacity"
                stroke={CHART_COLORS.gray}
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                isAnimationActive={false}
              />
              {showPlanMonthly ? (
                <Line
                  type="monotone"
                  dataKey={planMonthlyLabel}
                  stroke={CHART_COLORS.red}
                  strokeWidth={2}
                  strokeDasharray="3 3"
                  dot={false}
                  isAnimationActive={false}
                />
              ) : null}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="mb-6 p-5">
        <h3 className="text-sm font-semibold text-slate-900">Cumulative Gap Closure</h3>
        <p className="mt-1 text-xs text-slate-500">
          Compare the active scenario against the saved trajectory and the selected plan reference.
        </p>
        {planNote ? <p className="mt-1 text-[11px] text-slate-500">{planNote}</p> : null}
        <div className="mt-4">
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={cumulativeChartData}>
              <CartesianGrid
                horizontal={GRID_STYLE.horizontal}
                vertical={GRID_STYLE.vertical}
                stroke={GRID_STYLE.stroke}
                strokeDasharray={GRID_STYLE.strokeDasharray}
              />
              <XAxis
                dataKey="month"
                tick={AXIS_STYLE.tick}
                axisLine={AXIS_STYLE.axisLine}
                tickLine={false}
              />
              <YAxis
                tickFormatter={currencyFormatter}
                tick={AXIS_STYLE.tick}
                axisLine={false}
                tickLine={false}
                width={70}
              />
              <Tooltip
                formatter={currencyTooltipFormatter}
                contentStyle={TOOLTIP_STYLE.contentStyle}
                labelStyle={TOOLTIP_STYLE.labelStyle}
              />
              <Legend iconSize={LEGEND_STYLE.iconSize} wrapperStyle={LEGEND_STYLE.wrapperStyle} />
              <Line
                type="monotone"
                dataKey="Baseline Forecast"
                stroke={CHART_COLORS.gray}
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="Scenario Forecast"
                stroke={CHART_COLORS.blue}
                strokeWidth={2.5}
                dot={false}
                isAnimationActive={false}
              />
              {showPlanCumulative ? (
                <Line
                  type="monotone"
                  dataKey="Cumulative Plan Reference"
                  stroke={CHART_COLORS.red}
                  strokeWidth={2}
                  strokeDasharray="3 3"
                  dot={false}
                  isAnimationActive={false}
                />
              ) : null}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </>
  );
}
