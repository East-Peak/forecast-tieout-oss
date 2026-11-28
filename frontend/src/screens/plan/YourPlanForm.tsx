import { useEffect, useRef } from "react";
import type { FormEvent } from "react";
import { Card } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { useYourPlan, useYourPlanSnapshot } from "../../editor/YourPlanContext";
import type { Facts, HireDoc, PlanDoc, PlanError, ProgramDoc } from "../../editor/protocol";
import { MAX_ITEMS } from "../../editor/yourPlan";
import { ActionsFieldset } from "./ActionsFieldset";
import { Beside, Field, buttonClass, fieldClass, monthName, optional, optionalField } from "./formParts";

const MAX_HIRES_EACH = 20;

/**
 * "Your plan": the hires and programs the core will value, starting from the company's demo plan. Editing changes
 * a draft held for the session; nothing is computed until Apply, which the core does in this browser.
 */
export function YourPlanForm({ company }: { company: string }) {
  const yourPlan = useYourPlan();
  if (!yourPlan) return null;
  return <Form company={company} store={yourPlan.store} />;
}

function Form({ company, store }: { company: string; store: NonNullable<ReturnType<typeof useYourPlan>>["store"] }) {
  const snap = useYourPlanSnapshot(store);
  const facts = snap.facts[company] as Facts | undefined;
  const draft = snap.drafts[company] as PlanDoc | undefined;
  const applied = snap.applied[company];
  const top = useRef<HTMLDivElement>(null);
  const shown = Boolean(facts && draft);
  // a draft asked for from the worksheet or the grid is what the visitor lands on (the actions' own effect brings it into view)
  const toDraft = snap.revealed?.company === company;
  // Opening the editor, from this screen or another, lands on the form: in view, with its heading focused.
  useEffect(() => {
    if (!shown || toDraft) return;
    const heading = top.current?.querySelector("h2");
    heading?.setAttribute("tabindex", "-1");
    heading?.focus({ preventScroll: true });
    top.current?.scrollIntoView?.({ block: "start" });
  }, [shown]);
  if (!facts || !draft) return null;
  const feedback = snap.feedback.company === company ? snap.feedback : { company: null, errors: [], problems: [], failure: null, busy: false };
  const first = facts.months[0];
  const set = (next: PlanDoc) => store.setDraft(company, next);
  const hires = draft.hires;
  const programs = draft.programs;
  const full = [...hires, ...programs].length >= MAX_ITEMS;
  const unapplied = applied !== undefined && JSON.stringify(applied.plan) !== JSON.stringify(draft);
  const replaceHire = (i: number, patch: Partial<HireDoc>) => set({ ...draft, hires: hires.map((h, k) => (k === i ? { ...h, ...patch } : h)) });
  const replaceProgram = (i: number, change: (p: ProgramDoc) => ProgramDoc) => set({ ...draft, programs: programs.map((p, k) => (k === i ? change(p) : p)) });
  const errorsOf = (section: "hires" | "programs", i: number): PlanError[] => feedback.errors.filter((e) => e.section === section && e.position === i);
  const unplaced = feedback.errors.filter((e) => e.section === null);
  const monthOptions = facts.months.map((m) => (
    <option key={m} value={m}>
      {monthName(m, first)}
    </option>
  ));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void store.apply(company);
  };

  return (
    <div ref={top} className="scroll-mt-52">
    <Card data-testid="plan-form">
      <SectionHeader
        title="Your plan"
        subtitle="Change the hires and programs, then Apply. The same core that wrote the other scenarios computes it here, in your browser; nothing is sent anywhere."
      />
      <form onSubmit={submit} className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-3" disabled={feedback.busy}>
          <legend className="text-[11px] font-semibold uppercase text-slate-500">Hires</legend>
          {hires.map((hire, i) => (
            <div key={i} data-testid="hire-row" className="rounded-ft border border-slate-100 p-3">
              <div className="grid grid-cols-2 items-end gap-3 xl:grid-cols-[2fr_1fr_2fr_auto]">
                <Field label="Segment">
                  <select className={fieldClass} value={hire.segment} onChange={(e) => replaceHire(i, { segment: e.target.value })}>
                    {facts.segments.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="How many">
                  <input className={fieldClass} type="number" required min={0} max={MAX_HIRES_EACH} step={1} value={hire.count} onChange={(e) => replaceHire(i, { count: e.target.valueAsNumber })} />
                </Field>
                <Field label="Starts">
                  <select className={fieldClass} value={hire.start} onChange={(e) => replaceHire(i, { start: e.target.value })}>
                    {monthOptions}
                  </select>
                </Field>
                <button type="button" className={buttonClass} onClick={() => set({ ...draft, hires: hires.filter((_, k) => k !== i) })}>
                  Remove hire
                </button>
              </div>
              <Beside errors={errorsOf("hires", i)} />
            </div>
          ))}
          <div>
            <button
              type="button"
              className={buttonClass}
              disabled={full}
              onClick={() => set({ ...draft, hires: [...hires, { segment: facts.segments[0]?.value ?? "", start: first, count: 1 }] })}
            >
              Add a hire
            </button>
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-3" disabled={feedback.busy}>
          <legend className="text-[11px] font-semibold uppercase text-slate-500">Programs</legend>
          {programs.map((program, i) => (
            <div key={i} data-testid="program-row" className="rounded-ft border border-slate-100 p-3">
              <div className="grid grid-cols-2 items-end gap-3 xl:grid-cols-[2fr_2fr_2fr_2fr_1fr_auto]">
                <Field label="Program name">
                  <input className={fieldClass} type="text" value={program.name} onChange={(e) => replaceProgram(i, (p) => ({ ...p, name: e.target.value }))} />
                </Field>
                <Field label="Created pipeline">
                  <input className={fieldClass} type="number" required min={0} max={facts.max_dollars} step="any" value={program.pipeline} onChange={(e) => replaceProgram(i, (p) => ({ ...p, pipeline: e.target.valueAsNumber }))} />
                </Field>
                <Field label="Starts">
                  <select className={fieldClass} value={program.start} onChange={(e) => replaceProgram(i, (p) => ({ ...p, start: e.target.value }))}>
                    {monthOptions}
                  </select>
                </Field>
                <Field label="Cost (optional)">
                  <input className={fieldClass} type="number" min={0} max={facts.max_dollars} step="any" value={program.cost ?? ""} onChange={(e) => replaceProgram(i, ({ cost: _cost, ...p }) => ({ ...p, ...optionalField("cost", optional(e)) }))} />
                </Field>
                <Field label="Ramp in months (optional)">
                  <input className={fieldClass} type="number" min={1} step={1} value={program.ramp_months ?? ""} onChange={(e) => replaceProgram(i, ({ ramp_months: _ramp, ...p }) => ({ ...p, ...optionalField("ramp_months", optional(e)) }))} />
                </Field>
                <button type="button" className={buttonClass} onClick={() => set({ ...draft, programs: programs.filter((_, k) => k !== i) })}>
                  Remove program
                </button>
              </div>
              <Beside errors={errorsOf("programs", i)} />
            </div>
          ))}
          <div>
            <button
              type="button"
              className={buttonClass}
              disabled={full}
              onClick={() => set({ ...draft, programs: [...programs, { name: "", pipeline: 0, start: first }] })}
            >
              Add a program
            </button>
          </div>
        </fieldset>

        <ActionsFieldset company={company} store={store} facts={facts} draft={draft} applied={applied?.plan} origins={snap.origins[company] ?? {}} revealed={snap.revealed?.company === company ? snap.revealed : null} errors={feedback.errors} busy={feedback.busy} monthOptions={monthOptions} />

        {unplaced.length > 0 ? (
          <div data-testid="plan-form-errors" role="alert" className="text-xs text-red-700">
            {unplaced.map((e) => e.message).join("; ")}
          </div>
        ) : null}
        {feedback.problems.length > 0 ? (
          <div data-testid="plan-refused" role="alert" className="rounded-ft border border-red-200 bg-red-50 p-3 text-xs text-red-800">
            <p className="font-semibold">The computed report did not pass the core's own checks, so it is not shown.</p>
            <ul className="mt-1 list-disc pl-4">
              {feedback.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {feedback.failure ? (
          <div data-testid="plan-failure" role="alert" className="flex flex-wrap items-center gap-3 rounded-ft border border-red-200 bg-red-50 p-3 text-xs text-red-800">
            <p className="min-w-0 flex-1">
              <span className="font-semibold">{feedback.failure.kind === "timeout" ? "The computation took too long and was stopped." : "The computation stopped."}</span> {feedback.failure.message}
            </p>
            <button type="button" className={buttonClass} onClick={() => void store.apply(company)}>
              Try again
            </button>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={feedback.busy}
            className="rounded-ft border border-ft-accent bg-ft-accentSoft px-4 py-1.5 text-sm font-semibold text-ft-brand transition-colors disabled:opacity-60"
          >
            {feedback.busy ? "Computing in your browser…" : "Apply"}
          </button>
          {unapplied ? (
            <span data-testid="plan-unapplied" className="text-xs text-slate-600">
              The form has changes that are not applied yet; the figures below are for the plan as last applied.
            </span>
          ) : null}
        </div>
      </form>
    </Card>
    </div>
  );
}
