import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Text } from "../../components/ui";
import { useYourPlan } from "../../editor/YourPlanContext";
import { YOUR_PLAN } from "../../editor/yourPlan";
import { B, ROWS } from "./bindings";
import { WS } from "./worksheetBindings";

const pill = "rounded-ft border px-3 py-1 text-sm transition-colors";

/**
 * The summary row of the planning worksheet: the target, the roster as signed, the working plan and what is left,
 * with the twelve-month gain and cash cost beside the working plan. The scenario choices and the control that opens
 * the editor in place sit above it. With no plan in force the row says so in the report's own words.
 */
export function Summary({ planInForce }: { planInForce: boolean | null }) {
  const { company, scenario, files, choose } = useBindingContext();
  const yourPlan = useYourPlan();
  const entry = files.index.companies.find((c) => c.id === company);
  const editing = scenario === YOUR_PLAN;
  const row = files.comparison.rows.find((r) => r.scenario === scenario);
  const notValued = row?.bookings_change === null;
  return (
    <Card className="p-4" data-testid="worksheet-summary">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2" data-testid="scenario-picker">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Scenario">
          <span className="mr-1 text-[11px] font-semibold uppercase text-slate-500">Scenario</span>
          {entry?.scenarios.map((s, i) => {
            if (s.id === YOUR_PLAN) return null; // the visitor's own plan is reached through Edit plan
            const chosen = s.id === scenario;
            return (
              <button
                key={s.id}
                type="button"
                aria-pressed={chosen}
                data-scenario-id={s.id}
                onClick={() => choose?.(company, s.id)}
                className={`${pill} ${chosen ? "border-ft-accent bg-ft-accentSoft font-semibold text-ft-brand" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"}`}
              >
                <Bound binding={B.pickLabel} row={`${ROWS.scenarios}/${i}`} />
              </button>
            );
          })}
        </div>
        {yourPlan?.desktop ? (
          <button
            type="button"
            aria-pressed={editing}
            onClick={() => choose?.(company, YOUR_PLAN)}
            className="rounded-ft border border-ft-accent bg-white px-3 py-1 text-sm font-semibold text-ft-accent transition-colors hover:bg-ft-accentSoft aria-pressed:bg-ft-accentSoft aria-pressed:text-ft-brand"
          >
            Edit plan
          </button>
        ) : null}
      </div>
      <Text className="mt-2 text-xs text-slate-600">
        <Bound binding={B.scenarioDescription} />
        {yourPlan && !yourPlan.desktop ? <span className="text-slate-500"> Editing your own plan needs a larger screen.</span> : null}
      </Text>

      {planInForce === null ? null : (
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-slate-100 pt-4 lg:grid-cols-4" data-testid="worksheet-figures">
        <Figure label="Target">
          <Bound binding={WS.target} />
        </Figure>
        <Figure label="As signed">
          <Bound binding={WS.asSigned} />
        </Figure>
        <Figure label="Working plan">
          <Bound binding={WS.workingPlan} />
          {planInForce ? (
            <p className="mt-1 text-[11px] font-normal leading-tight text-slate-500" data-testid="worksheet-gain">
              Next twelve months: <Bound binding={notValued ? WS.gainNotValued : WS.gain} /> more booked, <Bound binding={WS.cost} /> cash cost
            </p>
          ) : null}
        </Figure>
        <Figure label="Remaining gap">
          <Bound binding={WS.remainingGap} />
        </Figure>
      </dl>
      )}
      {row?.note != null ? (
        <p className="mt-3 text-xs text-slate-700" data-testid="summary-note">
          <Bound binding={B.cmpNote} />
        </p>
      ) : null}
      {planInForce !== false ? null : (
        <p className="mt-3 text-xs text-slate-700" data-testid="no-plan">
          <Bound binding={WS.noPlanNote} />
          {yourPlan?.desktop ? (
            <>
              {" "}
              <button type="button" onClick={() => choose?.(company, YOUR_PLAN)} className="font-medium text-ft-brand underline">
                Build a plan
              </button>{" "}
              to see what it changes, or pick a scenario above.
            </>
          ) : (
            " Pick a scenario above to see what a plan changes."
          )}
        </p>
      )}
    </Card>
  );
}

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-display text-2xl font-semibold text-slate-900">{children}</dd>
    </div>
  );
}
