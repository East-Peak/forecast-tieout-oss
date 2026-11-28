import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import type { Facts, PlanDoc, PlanError } from "../../editor/protocol";
import { percentText, probabilityOf } from "../../editor/percent";
import type { YourPlanStore } from "../../editor/store";
import type { ActionOrigin } from "../../editor/yourPlan";
import { winRateReading } from "../../editor/winRate";
import { EVIDENCE, FORM } from "./driverActionBindings";
import { Beside, Field, buttonClass, fieldClass, optional, optionalField } from "./formParts";

/** The ramp the core allows, in months (its own limit: a longer one is refused in its words). */
const MAX_RAMP_MONTHS = 60;

const ORIGIN_NOTES: Record<ActionOrigin, string> = {
  tornado:
    "Started from the win-rate bar. Its value will differ from the bar's figure: the bar assumes an immediate company-wide change from the as-of date, and this action starts and ramps as set here.",
  grid:
    "Started from a grid cell. The target begins at the pooled baseline: the cell's own number is a dated cohort rate, not the win rate the model changes.",
};

/** A percent as the visitor types it, kept as typed (a trailing point stays); the plan holds the probability, with the point moved in the text. */
function PercentField({ label, probability, onChange }: { label: string; probability: string | number; onChange: (probability: string) => void }) {
  const [typed, setTyped] = useState(percentText(probability));
  useEffect(() => {
    // another change to the plan (a removed row, a new draft) replaces what is shown; the visitor's own typing does not
    if (probabilityOf(typed) !== String(probability)) setTyped(percentText(probability));
  }, [probability]);
  return (
    <Field label={label}>
      <input
        className={fieldClass}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        required
        value={typed}
        onChange={(e) => {
          setTyped(e.target.value);
          onChange(probabilityOf(e.target.value));
        }}
      />
    </Field>
  );
}

interface Props {
  company: string;
  store: YourPlanStore;
  facts: Facts;
  draft: PlanDoc;
  /** the plan as last applied: the core's figures belong to an action only as it was then */
  applied: PlanDoc | undefined;
  origins: Record<string, ActionOrigin>;
  revealed: { company: string; id: string } | null;
  errors: PlanError[];
  busy: boolean;
  monthOptions: ReactNode;
}

/** The plan's win-rate actions, beside its hires and programs: a list, and for each a name, a slice, a start, a ramp and a target. */
export function ActionsFieldset({ company, store, facts, draft, applied, origins, revealed, errors, busy, monthOptions }: Props) {
  const { files } = useBindingContext();
  const actions = draft.actions ?? [];
  const reading = winRateReading(files.report);
  const root = useRef<HTMLFieldSetElement>(null);
  const slices = [{ value: "company", label: "Company" }, ...facts.segments];
  const used = new Set(actions.map((a) => a.slice));
  const next = actions.length === 0 ? "company" : (facts.segments.find((s) => !used.has(s.value))?.value ?? "company");
  /** the plan with these actions: none is no list at all, so a plan whose last action was removed is the plan it was before */
  const setActions = (next: NonNullable<PlanDoc["actions"]>) => {
    const { actions: _held, ...rest } = draft;
    store.setDraft(company, next.length === 0 ? rest : { ...rest, actions: next });
  };
  const replace = (i: number, change: (a: NonNullable<PlanDoc["actions"]>[number]) => NonNullable<PlanDoc["actions"]>[number]) => setActions(actions.map((a, k) => (k === i ? change(a) : a)));

  useEffect(() => {
    if (!revealed) return;
    const row = root.current?.querySelector(`[data-action-id="${revealed.id}"]`);
    row?.scrollIntoView?.({ block: "center" });
    row?.querySelector<HTMLInputElement>("input[type='text']")?.focus({ preventScroll: true });
    store.acknowledgeReveal();
  }, [revealed, store]);

  return (
    <fieldset ref={root} className="flex flex-col gap-3" disabled={busy} data-testid="actions-fieldset">
      <legend className="text-[11px] font-semibold uppercase text-slate-500">Actions</legend>
      {reading.present ? (
        <p className="text-xs text-slate-600" data-testid="actions-line">
          <Bound binding={FORM.line} />
        </p>
      ) : null}
      {actions.map((action, i) => {
        const placed = applied?.actions?.find((a) => a.id === action.id);
        const asApplied = placed !== undefined && JSON.stringify(placed) === JSON.stringify(action);
        const section = files.report.driver_actions;
        const at = "joint_gain" in section ? section.items.findIndex((item) => item.id === action.id) : -1;
        const evidence = asApplied && at !== -1 && "joint_gain" in section ? { row: `/driver_actions/items/${at}`, outside: section.items[at].evidence.position !== "inside" } : null;
        const origin = asApplied ? undefined : origins[action.id];
        const mine = errors.filter((e) => e.section === "actions" && e.position === i);
        return (
          <div key={action.id} data-testid="action-row" data-action-id={action.id} className="rounded-ft border border-slate-100 p-3">
            <div className="grid grid-cols-2 items-end gap-3 xl:grid-cols-[2fr_1.4fr_1.6fr_1.4fr_1.4fr_auto]">
              <Field label="Action name">
                <input className={fieldClass} type="text" value={action.name ?? ""} onChange={(e) => replace(i, (a) => ({ ...a, name: e.target.value }))} />
              </Field>
              <Field label="Slice">
                <select className={fieldClass} value={action.slice} onChange={(e) => replace(i, (a) => ({ ...a, slice: e.target.value }))}>
                  {slices.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Starts">
                <select className={fieldClass} value={action.start} onChange={(e) => replace(i, (a) => ({ ...a, start: e.target.value }))}>
                  {monthOptions}
                </select>
              </Field>
              <Field label="Ramp in months (zero is immediate)">
                <input
                  className={fieldClass}
                  type="number"
                  min={0}
                  max={MAX_RAMP_MONTHS}
                  step={1}
                  value={action.ramp_months ?? ""}
                  onChange={(e) => replace(i, ({ ramp_months: _ramp, ...a }) => ({ ...a, ...optionalField("ramp_months", optional(e)) }))}
                />
              </Field>
              <PercentField label="Target win rate (percent)" probability={action.target} onChange={(target) => replace(i, (a) => ({ ...a, target }))} />
              <button type="button" className={buttonClass} onClick={() => setActions(actions.filter((_, k) => k !== i))}>
                Remove action
              </button>
            </div>
            {reading.present ? (
              <p className="mt-2 text-xs text-slate-600" data-testid="action-evidence">
                Pooled baseline <Bound binding={FORM.baseline} className="font-semibold text-slate-900" />; worksheet low <Bound binding={FORM.low} className="font-semibold text-slate-900" />, high{" "}
                <Bound binding={FORM.high} className="font-semibold text-slate-900" />.{" "}
                {evidence ? (
                  <>
                    As applied: <Bound binding={EVIDENCE.change} row={evidence.row} className="font-semibold text-slate-900" /> points on the baseline, resulting rate{" "}
                    <Bound binding={EVIDENCE.resulting} row={evidence.row} className="font-semibold text-slate-900" />.{" "}
                    {evidence.outside ? <Bound binding={EVIDENCE.label} row={evidence.row} className="font-medium text-amber-800" /> : null}
                  </>
                ) : (
                  <span data-testid="action-pending">The core reports the change in points and the resulting rate when you apply.</span>
                )}
              </p>
            ) : (
              <p className="mt-2 text-xs text-slate-600">The worksheet cannot be built for this plan, so there is no baseline to show beside the target.</p>
            )}
            {origin ? (
              <p className="mt-1 text-xs text-slate-600" data-testid="action-origin">
                {ORIGIN_NOTES[origin]}
              </p>
            ) : null}
            <Beside errors={mine} />
          </div>
        );
      })}
      <div>
        <button
          type="button"
          className={buttonClass}
          disabled={actions.length >= facts.segments.length}
          onClick={() => store.draftAction(company, { slice: next, target: reading.baseline ?? "", origin: null })}
        >
          Add an action
        </button>
      </div>
    </fieldset>
  );
}
