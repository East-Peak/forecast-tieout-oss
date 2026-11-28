import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import { COLUMN } from "../../components/workbook/column";
import type { Binding } from "../../binding/Bound";
import { Badge, Callout } from "../../components/ui";
import { ScreenHeading } from "../../components/workbook";
import { MetricCard } from "../../components/workbook/MetricCard";
import { signOf } from "../../lib/format";
import { B, MONTHLY_METHODS, PLANNED, SIGNED } from "./bindings";
import { MonthlyChart } from "./MonthlyChart";
import type { Availability } from "./MonthlyChart";
import { QuarterChart } from "./QuarterChart";
import { QuarterTable } from "./QuarterTable";
import { RangeCheck } from "./RangeCheck";
import { ScenarioStrip } from "./ScenarioStrip";
import { Verdicts } from "./Verdicts";
import { WindowTable } from "./WindowTable";

function availability(methods: ReadonlyArray<{ method: string; available: boolean }>): Availability {
  const is = (name: string) => methods.find((m) => m.method === name)?.available === true;
  return { fitted: is(MONTHLY_METHODS.fitted) };
}

/** Shortfall or ahead, in a plain badge, from the sign of the report's gap (target less expected). */
function SignBadge({ binding }: { binding: Binding }) {
  const ctx = useBindingContext();
  const value = readBinding(ctx, binding);
  if (value === null) return null;
  const sign = signOf(value);
  const [color, word] = sign > 0 ? (["red", "Shortfall"] as const) : sign < 0 ? (["green", "Ahead"] as const) : (["slate", "On target"] as const);
  return (
    <Badge color={color} size="xs" data-testid="gap-badge" data-sign={String(sign)}>
      {word}
    </Badge>
  );
}

/** The report's label for a range, in small print beneath it. */
function RangeLabel({ binding }: { binding: Binding }) {
  return (
    <p className="mt-1 text-[11px] leading-tight text-slate-500" data-testid="range-label">
      <Bound binding={binding} />
    </p>
  );
}

/**
 * Forecast: where the year lands and how sure we are, for the selected scenario. Every figure is a
 * Bound value (a named pointer into a core-produced file); the charts are built from declared
 * paths; the screen calculates nothing. For a plan the headline, charts and tables are the with-plan
 * figures and the as-signed figure sits beside the headline. The binding list is ./bindings.ts.
 */
export default function ForecastScreen() {
  const { files } = useBindingContext();
  const available = availability(files.report.forecasts.methods);
  const plan = files.report.plan;
  const planned = plan !== undefined && !("unavailable" in plan);
  const V = planned ? PLANNED : SIGNED;

  return (
    <div className={COLUMN}>
      <ScreenHeading
        title="Forecast"
        subtitle="Where the year lands, and how sure we are."
        caption={
          <>
            <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} /> · <Bound binding={B.measure} />
          </>
        }
      />

      {!available.fitted ? (
        <Callout color="amber" title="The fitted forecast is unavailable">
          <Bound binding={B.fittedUnavailable} />. Targets and bookings to date are shown; nothing is forecast.
        </Callout>
      ) : null}
      {plan !== undefined && !planned ? (
        <Callout color="amber" title="This plan cannot be valued">
          <Bound binding={B.planUnavailable} />
        </Callout>
      ) : null}

      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-6 xl:grid-cols-5">
          <MetricCard label="Target" value={<Bound binding={B.yearTarget} />} note="The year's quarterly targets together" className="p-4 lg:col-span-2 xl:col-span-1" />
          <MetricCard
            label={planned ? "Expected, with this scenario" : "Expected for the year"}
            value={<Bound binding={V.yearExpected} />}
            note={planned ? undefined : "Booked to date plus forecast"}
            className="p-4 lg:col-span-2 xl:col-span-1"
          >
            {planned ? (
              <p className="mt-1 text-[11px] leading-tight text-slate-500">
                As signed: <Bound binding={B.signedExpected} />
              </p>
            ) : null}
          </MetricCard>
          <MetricCard label="Gap to target" value={<Bound binding={V.yearGap} />} className="p-4 lg:col-span-2 xl:col-span-1">
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <SignBadge binding={V.yearGap} />
              {planned ? (
                <span className="text-[11px] text-slate-500">
                  As signed: <Bound binding={B.signedGap} />
                </span>
              ) : null}
            </div>
          </MetricCard>
          <MetricCard
            label="80% range"
            value={
              <span className="text-xl lg:whitespace-nowrap" data-testid="range-figure">
                <Bound binding={V.range80Low} /> to <Bound binding={V.range80High} />
              </span>
            }
            note="Of the expected year"
            className="p-4 lg:col-span-3 xl:col-span-1"
          >
            {available.fitted && !planned ? <RangeLabel binding={B.rangeLabel80} /> : null}
          </MetricCard>
          <MetricCard
            label="95% range"
            value={
              <span className="text-xl lg:whitespace-nowrap" data-testid="range-figure">
                <Bound binding={V.range95Low} /> to <Bound binding={V.range95High} />
              </span>
            }
            note="Of the expected year"
            className="col-span-2 p-4 lg:col-span-3 xl:col-span-1"
          >
            {available.fitted && !planned ? <RangeLabel binding={B.rangeLabel95} /> : null}
          </MetricCard>
        </div>

        {available.fitted ? (
          <div className="rounded-ft border border-slate-200 bg-slate-50/80 px-4 py-2.5 text-sm text-slate-700" data-testid="range-trust">
            <span className="font-semibold text-ft-brand">How far to trust the ranges: </span>
            <Bound binding={V.yearRangeStatus} />
          </div>
        ) : null}
      </div>

      <Verdicts />

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] 2xl:items-start">
        <MonthlyChart available={available} planned={planned} />
        <QuarterChart fittedAvailable={available.fitted} planned={planned} />
      </div>
      <QuarterTable planned={planned} />
      <WindowTable planned={planned} fittedAvailable={available.fitted} />
      {available.fitted ? <RangeCheck /> : null}
      <ScenarioStrip />
    </div>
  );
}
