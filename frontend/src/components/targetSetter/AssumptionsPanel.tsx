export function AssumptionsPanel() {
  return (
    <details
      open
      className="text-sm border border-slate-200 rounded-lg p-4 bg-slate-50"
    >
      <summary className="cursor-pointer font-medium text-slate-800">
        Key assumptions
      </summary>
      <ul className="list-disc pl-5 mt-3 space-y-1.5 text-slate-700">
        <li>
          <strong>Two tributaries feed the funnel at S0.</strong> Marketing MQLs flow through
          MQL→S0; Outbound (SDRs + direct AE outreach) contributes S0 meetings directly without a
          prior MQL stage. Both merge at S0 into one unified funnel.
        </li>
        <li>
          <strong>
            Outbound uses the same S0→S1 and S1→S2 rates as marketing in v1 (same-rate proxy).
          </strong>{" "}
          Real outbound rates may differ — higher if pre-qualified before booking, lower if cold.
          Treat outbound numbers as a same-rate approximation, not a validated forecast.
        </li>
        <li>
          <strong>Bookings = closed-won ARR only.</strong> Expansion, PLG, and renewals tied out
          separately.
        </li>
      </ul>
      <details className="mt-3 pl-4 border-l-2 border-slate-200">
        <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700">
          More assumptions
        </summary>
        <ul className="list-disc pl-5 mt-2 space-y-1.5 text-xs text-slate-600">
          <li>
            AE self-gen share is measured at the S2 dollar level and back-fed through the
            funnel to imply outbound S0/S1.
          </li>
          <li>
            MQL → S2 creation is modeled as same-quarter. Real lag &gt;90 days will miscalibrate
            monthly cadence.
          </li>
          <li>
            Waterfall runs aggregate; segment split only affects the
            pipeline-dollars-to-deal-count conversion via ACV.
          </li>
          <li>AE-sourced and marketing-sourced deals share the segment ACV in v1.</li>
          <li>Monthly distribution is flat-thirds or 25/35/40 — no seasonality fit.</li>
          <li>
            Observed waterfall rates (starting-win / created-win / push / loss) are calibrated
            constants in v1 — not dynamically recomputed per snapshot.
          </li>
          <li>
            Active quarter is excluded from the inverse solve (shown as YTD + remaining-gap only).
          </li>
        </ul>
      </details>
    </details>
  );
}
