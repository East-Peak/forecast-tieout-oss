import type { ChangeEvent, ReactNode } from "react";
import type { PlanError } from "../../editor/protocol";

const MONTH_NAMES: Record<string, string> = {
  "01": "January",
  "02": "February",
  "03": "March",
  "04": "April",
  "05": "May",
  "06": "June",
  "07": "July",
  "08": "August",
  "09": "September",
  "10": "October",
  "11": "November",
  "12": "December",
};

/** A start month in words ("October", "January, next year"): no digit, so no figure stands outside a bound value. */
export const monthName = (month: string, first: string) => `${MONTH_NAMES[month.slice(5)]}${month.slice(0, 4) === first.slice(0, 4) ? "" : ", next year"}`;

export const fieldClass =
  "w-full min-w-0 rounded-ft border border-slate-200 bg-white px-2 py-1.5 text-sm text-text-primary shadow-ft outline-none focus:border-ft-accent focus:ring-2 focus:ring-ft-accentSoft";
export const buttonClass = "rounded-ft border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors hover:border-slate-300 disabled:opacity-50";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid min-w-0 gap-1">
      <span className="text-[11px] font-semibold uppercase text-slate-500">{label}</span>
      {children}
    </label>
  );
}

/** A number field read as a number, or as nothing when it was emptied. */
export const optional = (e: ChangeEvent<HTMLInputElement>) => (e.target.value === "" ? undefined : e.target.valueAsNumber);

/** `{ [name]: value }`, or nothing at all when the field was emptied (an absent field is left out of the plan). */
export function optionalField<K extends "cost" | "ramp_months">(name: K, value: number | undefined): Partial<Record<K, number>> {
  return value === undefined ? {} : ({ [name]: value } as Record<K, number>);
}

/** The core's own words for what it refused about one item, beside the item (its place in the plan's list is not repeated). */
export function Beside({ errors }: { errors: PlanError[] }) {
  if (errors.length === 0) return null;
  return (
    <p role="alert" className="mt-1 text-xs text-red-700">
      {errors.map((e) => e.message.replace(/^(hires|programs|actions)\[\d+\]: /, "")).join("; ")}
    </p>
  );
}
