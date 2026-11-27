import { Bound, useBindingContext } from "../../binding/Bound";
import { Card } from "../../components/ui";
import { useYourPlan } from "../../editor/YourPlanContext";
import { YOUR_PLAN } from "../../editor/yourPlan";
import { B, ROWS } from "./bindings";

/** The scenarios this company has, as buttons; the chosen one is pressed and described. Choosing one reloads the screen from that scenario's report. */
export function ScenarioPicker() {
  const { company, scenario, files, choose } = useBindingContext();
  const yourPlan = useYourPlan();
  const entry = files.index.companies.find((c) => c.id === company);
  if (!entry) return null;
  const editor = entry.scenarios.find((s) => s.id === YOUR_PLAN);
  const editorChosen = scenario === YOUR_PLAN;
  return (
    <Card className="p-4" data-testid="scenario-picker">
      <p className="mb-2 text-[11px] font-semibold uppercase text-slate-500">Scenario</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Scenario">
        {entry.scenarios.map((s, i) => {
          if (s.id === YOUR_PLAN) return null;
          const chosen = s.id === scenario;
          return (
            <button
              key={s.id}
              type="button"
              aria-pressed={chosen}
              data-scenario-id={s.id}
              onClick={() => choose?.(company, s.id)}
              className={`rounded-ft border px-3 py-1.5 text-sm transition-colors ${
                chosen ? "border-ft-accent bg-ft-accentSoft font-semibold text-ft-brand" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
              }`}
            >
              <Bound binding={B.pickLabel} row={`${ROWS.scenarios}/${i}`} />
            </button>
          );
        })}
      </div>
      {editor ? (
        <div className="mt-3 border-t border-slate-200 pt-3">
          <button
            type="button"
            aria-pressed={editorChosen}
            data-scenario-id={editor.id}
            onClick={() => choose?.(company, editor.id)}
            className={`rounded-ft border border-ft-accent px-3 py-1.5 text-sm font-semibold transition-colors ${
              editorChosen ? "bg-ft-accentSoft text-ft-brand" : "bg-white text-ft-accent hover:bg-ft-accentSoft"
            }`}
          >
            Build your own plan
          </button>
          <p className="mt-1 text-xs text-slate-600">Change the hires and programs and see every screen update. Computed in your browser.</p>
        </div>
      ) : null}
      <p className="mt-2 text-xs text-slate-600">
        <Bound binding={B.scenarioDescription} />
      </p>
      {yourPlan && !yourPlan.desktop ? <p className="mt-2 text-xs text-slate-500">Editing your own plan needs a larger screen.</p> : null}
    </Card>
  );
}
