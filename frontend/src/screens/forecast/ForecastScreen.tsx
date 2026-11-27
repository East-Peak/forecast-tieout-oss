import { Bound, useBindingContext } from "../../binding/Bound";
import { Callout } from "../../components/ui";
import { MetricStrip, ProseNote, SectionHeader } from "../../components/workbook";
import type { MetricItem } from "../../components/workbook";
import { B, MONTHLY_METHODS } from "./bindings";
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
  return {
    fitted: is(MONTHLY_METHODS.fitted),
    stage: is(MONTHLY_METHODS.stage),
    runRate: is(MONTHLY_METHODS.runRate),
  };
}

/**
 * Forecast: where the year lands and how sure we are. Every figure is a Bound value (a named
 * pointer into the scenario's report); the charts are built from declared paths; the screen
 * calculates nothing. The committed binding list is ./bindings.ts.
 */
export default function ForecastScreen() {
  const { files } = useBindingContext();
  const available = availability(files.report.forecasts.methods);

  const metrics: MetricItem[] = [
    { label: "Target", value: <Bound binding={B.yearTarget} />, note: "The fiscal year's quarterly targets together" },
    {
      label: "Expected for the year",
      value: <Bound binding={B.yearExpected} />,
      note: "Booked to date plus the fitted forecast",
    },
    {
      label: "Gap to target",
      value: <Bound binding={B.yearGap} />,
      note: "Target less expected: positive is a shortfall, negative is ahead",
    },
    {
      label: "80% range",
      value: (
        <span className="text-xl">
          <Bound binding={B.range80Low} /> to <Bound binding={B.range80High} />
        </span>
      ),
      note: "Of the expected year",
    },
    {
      label: "95% range",
      value: (
        <span className="text-xl">
          <Bound binding={B.range95Low} /> to <Bound binding={B.range95High} />
        </span>
      ),
      note: "Of the expected year",
    },
  ];

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <SectionHeader
        title="Forecast"
        subtitle="Where the year lands, and how sure we are. Every figure is read from the report the core wrote for this company and scenario."
      />
      <p className="-mt-3 text-xs text-slate-500">
        <Bound binding={B.fiscalYear} /> · as of <Bound binding={B.asOf} /> · measure: <Bound binding={B.measure} />
      </p>

      {!available.fitted ? (
        <Callout color="amber" title="The fitted forecast is unavailable">
          <Bound binding={B.fittedUnavailable} />. Targets and bookings to date are shown; nothing is forecast, and no
          range is drawn.
        </Callout>
      ) : null}

      <MetricStrip metrics={metrics} />

      {available.fitted ? (
        <ProseNote>
          How far to trust the ranges, rest of the year: <Bound binding={B.yearRangeStatus} />
        </ProseNote>
      ) : null}

      <Verdicts />

      <MonthlyChart available={available} />
      {!available.stage ? (
        <p className="-mt-3 text-xs text-slate-500">
          Stage-weighted pipeline: <Bound binding={B.stageUnavailable} />
        </p>
      ) : null}
      {!available.runRate ? (
        <p className="-mt-3 text-xs text-slate-500">
          Trailing run-rate: <Bound binding={B.runRateUnavailable} />
        </p>
      ) : null}

      <QuarterChart fittedAvailable={available.fitted} />
      <QuarterTable />
      <WindowTable />
      {available.fitted ? <RangeCheck /> : null}
      <ScenarioStrip />
    </div>
  );
}
