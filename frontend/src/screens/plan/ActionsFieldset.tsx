import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import type { ActionDriver, Facts, PlanDoc, PlanError } from "../../editor/protocol";
import { percentText, probabilityOf } from "../../editor/percent";
import type { YourPlanStore } from "../../editor/store";
import { ACTION_DRIVERS, defaultName, nextAction, sliceLabel } from "../../editor/yourPlan";
import type { ActionOrigin } from "../../editor/yourPlan";
import { driverReading } from "../../editor/winRate";
import { DRIVER_CHOICE, EVIDENCE, EVIDENCE_AMOUNT, FORM, FORM_BY_DRIVER } from "./driverActionBindings";
import { Beside, Field, buttonClass, fieldClass, optional, optionalField } from "./formParts";

/** The ramp the core allows, in months (its own limit: a longer one is refused in its words). */
const MAX_RAMP_MONTHS = 60;

/** What the drivers are called in the form's choice, and the target field's label for each. */
const DRIVER_NAMES: Record<ActionDriver, { choice: string; target: string }> = {
  win_rate: { choice: DRIVER_CHOICE.win_rate, target: "Target win rate (percent)" },
  won_arr: { choice: DRIVER_CHOICE.won_arr, target: "Target won ARR per win (dollars)" },
  productivity: { choice: DRIVER_CHOICE.productivity, target: "Target creation productivity (deals)" },
};

/** The bar a draft was started from, in the visitor's words for it. */
const BAR: Record<ActionDriver, string> = { win_rate: "win-rate", won_arr: "deal-size", productivity: "creation" };

const GRID_NOTES: Record<ActionDriver, string> = {
  win_rate: "Started from a grid cell. The target begins at the pooled baseline: the cell's own number is a dated cohort rate, not the win rate the model changes.",
  won_arr:
    "Started from a grid cell. The target begins at the pooled baseline: the cell's own number is the average won ARR of the lane's wins, a blend of sizes that a forecast prices by sharing the pooled bookings out, not the size the model changes.",
  productivity:
    "Started from a grid cell. The target begins at the pooled baseline: the cell's own number is the deals created in the period, while the action changes how many deals the slice's people create per ramped AE-month (or per day where that term is not in use).",
};

const originNote = (origin: ActionOrigin, driver: ActionDriver): string =>
  origin === "grid"
    ? GRID_NOTES[driver]
    : `Started from the ${BAR[driver]} bar. Its value will differ from the bar's figure: the bar assumes an immediate company-wide change from the as-of date, and this action starts and ramps as set here.`;

/** A target typed in the driver's own terms (dollars, deals), kept as typed: the plan holds the text, and the core reads it. */
function TextTarget({ label, value, onChange }: { label: string; value: string | number; onChange: (value: string) => void }) {
  return (
    <Field label={label}>
      <input className={fieldClass} type="text" inputMode="decimal" autoComplete="off" required value={String(value)} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

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

/** The plan's actions, beside its hires and programs: a list, and for each a name, the driver it changes, a slice, a start, a ramp and a target in that driver's terms. */
export function ActionsFieldset({ company, store, facts, draft, applied, origins, revealed, errors, busy, monthOptions }: Props) {
  const { files } = useBindingContext();
  const actions = draft.actions ?? [];
  const root = useRef<HTMLFieldSetElement>(null);
  const slices = [{ value: "company", label: "Company" }, ...facts.segments];
  const next = nextAction(draft, facts);
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
      {"line" in files.report.driver_actions ? (
        <p className="text-xs text-slate-600" data-testid="actions-line">
          <Bound binding={FORM.line} />
        </p>
      ) : null}
      {actions.map((action, i) => {
        const placed = applied?.actions?.find((a) => a.id === action.id);
        const asApplied = placed !== undefined && JSON.stringify(placed) === JSON.stringify(action);
        const section = files.report.driver_actions;
        // the core's entry is the action's only when it is for the same driver (the report is the last Apply's)
        const at = "joint_gain" in section ? section.items.findIndex((item) => item.id === action.id && item.driver === action.driver) : -1;
        const evidence = asApplied && at !== -1 && "joint_gain" in section ? { row: `/driver_actions/items/${at}`, outside: section.items[at].evidence.position !== "inside" } : null;
        const reading = driverReading(files.report, action.driver);
        const form = FORM_BY_DRIVER[action.driver];
        const origin = asApplied ? undefined : origins[action.id];
        const mine = errors.filter((e) => e.section === "actions" && e.position === i);
        return (
          <div key={action.id} data-testid="action-row" data-action-id={action.id} className="rounded-ft border border-slate-100 p-3">
            <div className="grid grid-cols-2 items-end gap-3 xl:grid-cols-[1.8fr_1.5fr_1.2fr_1.5fr_1.2fr]">
              <Field label="Action name">
                <input className={fieldClass} type="text" value={action.name ?? ""} onChange={(e) => replace(i, (a) => ({ ...a, name: e.target.value }))} />
              </Field>
              <Field label="Changes">
                <select
                  className={fieldClass}
                  value={action.driver}
                  onChange={(e) => {
                    const driver = e.target.value as ActionDriver;
                    const target = driverReading(files.report, driver).baseline ?? "";
                    // a name the form gave (and the visitor did not change) follows the driver; one the visitor wrote stays
                    const keepsName = action.name !== defaultName(sliceLabel(facts, action.slice), action.driver);
                    replace(i, (a) => ({ ...a, driver, target, name: keepsName ? a.name : defaultName(sliceLabel(facts, a.slice), driver) }));
                  }}
                >
                  {ACTION_DRIVERS.map((d) => (
                    <option key={d} value={d}>
                      {DRIVER_NAMES[d].choice}
                    </option>
                  ))}
                </select>
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
              {action.driver === "win_rate" ? (
                <PercentField label={DRIVER_NAMES.win_rate.target} probability={action.target} onChange={(target) => replace(i, (a) => ({ ...a, target }))} />
              ) : (
                <TextTarget label={DRIVER_NAMES[action.driver].target} value={action.target} onChange={(target) => replace(i, (a) => ({ ...a, target }))} />
              )}
              <button type="button" className={buttonClass} onClick={() => setActions(actions.filter((_, k) => k !== i))}>
                Remove action
              </button>
            </div>
            {reading.present ? (
              <p className="mt-2 text-xs text-slate-600" data-testid="action-evidence">
                Pooled baseline <Bound binding={form.baseline} className="font-semibold text-slate-900" />; worksheet low <Bound binding={form.low} className="font-semibold text-slate-900" />, high{" "}
                <Bound binding={form.high} className="font-semibold text-slate-900" />
                {action.driver === "win_rate" ? null : (
                  <>
                    {" "}
                    (<Bound binding={FORM_BY_DRIVER[action.driver].unit} />)
                  </>
                )}
                .{" "}
                {evidence ? (
                  action.driver === "win_rate" ? (
                    <>
                      As applied: <Bound binding={EVIDENCE.change} row={evidence.row} className="font-semibold text-slate-900" /> points on the baseline, resulting rate{" "}
                      <Bound binding={EVIDENCE.resulting} row={evidence.row} className="font-semibold text-slate-900" />.{" "}
                      {evidence.outside ? <Bound binding={EVIDENCE.label} row={evidence.row} className="font-medium text-amber-800" /> : null}
                    </>
                  ) : (
                    <>
                      As applied: <Bound binding={EVIDENCE_AMOUNT.changePercent} row={evidence.row} className="font-semibold text-slate-900" /> percent on the baseline, resulting{" "}
                      <Bound binding={action.driver === "won_arr" ? EVIDENCE_AMOUNT.resultingSize : EVIDENCE_AMOUNT.resultingCreation} row={evidence.row} className="font-semibold text-slate-900" />.{" "}
                      {evidence.outside ? <Bound binding={EVIDENCE.label} row={evidence.row} className="font-medium text-amber-800" /> : null}
                    </>
                  )
                ) : (
                  <span data-testid="action-pending">
                    {action.driver === "win_rate" ? "The core reports the change in points and the resulting rate when you apply." : "The core reports the change in percent and the resulting value when you apply."}
                  </span>
                )}
              </p>
            ) : (
              <p className="mt-2 text-xs text-slate-600">The worksheet cannot be built for this plan, so there is no baseline to show beside the target.</p>
            )}
            {origin ? (
              <p className="mt-1 text-xs text-slate-600" data-testid="action-origin">
                {originNote(origin, action.driver)}
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
          disabled={next === null}
          onClick={() => next && store.draftAction(company, { slice: next.slice, driver: next.driver, target: driverReading(files.report, next.driver).baseline ?? "", origin: null })}
        >
          Add an action
        </button>
      </div>
    </fieldset>
  );
}
