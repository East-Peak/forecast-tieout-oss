import { useId, useState } from "react";
import { formatValue } from "../lib/format";
import type { LanesData } from "./types";

const FACTOR_ORDER = ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26", "FY26"];

/** The plan basis in one line, with the plain-sentence explanation of what the goals are and are not behind a disclosure. */
export function PlanBasis({ meta }: { meta: LanesData["meta"] }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const date = formatValue("date", meta.plan_basis.cutoff);
  const factors = FACTOR_ORDER.filter((q) => meta.scale_factors[q]);
  return (
    <div className="text-xs text-slate-600" data-testid="plan-basis">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>
          <span className="font-semibold text-slate-800">{meta.plan_basis.label_text}</span>, {date}
        </span>
        <span className="text-slate-400">{meta.company}, data as of {formatValue("date", meta.as_of)}</span>
        <button type="button" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((v) => !v)} className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:border-slate-300">
          <span aria-hidden="true" className="mr-1 text-slate-400">i</span>
          How the goals are made {open ? "▴" : "▾"}
        </button>
      </div>
      {open ? (
        <div id={panel} className="mt-2 grid items-start gap-x-8 gap-y-5 rounded-ft border border-slate-200 bg-white p-4 leading-snug text-slate-700 shadow-ft lg:grid-cols-2" data-testid="plan-basis-detail">
          <div className="space-y-5">
          <section>
            <h3 className="text-xs font-semibold text-ft-brand">What the goals are</h3>
            <p className="mt-1">
              The goals are derived benchmarks, not a commitment anyone made. The core refit its model as of {date}, using only what was known then, and froze that fit: its rates, deal sizes, timing and the pipeline open on that date. Each upstream goal is what the entered bookings targets would require through that frozen basis. Ownership, segment and quota have no history in the files, so the plan basis is a reconstruction, not the original operating plan.
            </p>
          </section>
          <section>
            <h3 className="text-xs font-semibold text-ft-brand">Segment rows use their own deal sizes</h3>
            <p className="mt-1">
              Each segment forecasts with its own average deal sizes, then the segment forecasts are scaled so that they sum to the company forecast. The scaling applies only to creation still to come, never to actuals or to deals already open.
            </p>
            <table className="mt-2 w-full max-w-md text-left tabular-nums">
              <thead className="text-slate-500">
                <tr>
                  <th scope="col" className="py-0.5 font-medium">Period</th>
                  <th scope="col" className="py-0.5 text-right font-medium">Bookings scale</th>
                  <th scope="col" className="py-0.5 text-right font-medium">Created ARR scale</th>
                </tr>
              </thead>
              <tbody>
                {factors.map((q) => (
                  <tr key={q} className="border-t border-slate-100">
                    <th scope="row" className="py-0.5 font-normal">{q}</th>
                    <td className="py-0.5 text-right">{formatValue("multiple", formatValue("decimal2", meta.scale_factors[q].bookings))}</td>
                    <td className="py-0.5 text-right">{formatValue("multiple", formatValue("decimal2", meta.scale_factors[q].created_arr))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          </div>
          <div className="space-y-5">
          <section>
            <h3 className="text-xs font-semibold text-ft-brand">The schedule over-covers the targets</h3>
            <p className="mt-1">
              The creation schedule behind the upstream goals produces {formatValue("usd-short", meta.schedule_totals.bookings)} of bookings against {formatValue("usd-short", meta.schedule_totals.target)} of targets, because pipeline created to fund one quarter also lands in later ones. Target-equivalent wins are computed from the target, not from the schedule.
            </p>
            <table className="mt-2 w-full max-w-md text-left tabular-nums">
              <thead className="text-slate-500">
                <tr>
                  <th scope="col" className="py-0.5 font-medium">Quarter</th>
                  <th scope="col" className="py-0.5 text-right font-medium">Schedule bookings</th>
                  <th scope="col" className="py-0.5 text-right font-medium">Target</th>
                </tr>
              </thead>
              <tbody>
                {meta.frozen_schedule.map((q) => (
                  <tr key={q.quarter} className="border-t border-slate-100">
                    <th scope="row" className="py-0.5 font-normal">{q.quarter}</th>
                    <td className="py-0.5 text-right">{formatValue("usd-short", q.bookings)}</td>
                    <td className="py-0.5 text-right">{formatValue("usd-short", q.target)}</td>
                  </tr>
                ))}
                <tr className="border-t border-slate-200 font-medium">
                  <th scope="row" className="py-0.5">Year</th>
                  <td className="py-0.5 text-right">{formatValue("usd-short", meta.schedule_totals.bookings)}</td>
                  <td className="py-0.5 text-right">{formatValue("usd-short", meta.schedule_totals.target)}</td>
                </tr>
              </tbody>
            </table>
          </section>
          <section>
            <h3 className="text-xs font-semibold text-ft-brand">A known gap in this prototype</h3>
            <p className="mt-1">
              The company's upstream goals and the segments' upstream goals do not yet sum exactly: the segments' own deal sizes and the quarterly goals cannot all reconcile to the fixed company goals. Treat a segment's goal as a benchmark for that segment, not as a share of the company's that is guaranteed to add up.
            </p>
          </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
