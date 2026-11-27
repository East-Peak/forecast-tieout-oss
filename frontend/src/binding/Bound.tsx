import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { TieoutReport } from "../generated/report";
import { formatValue, signOf } from "../lib/format";
import type { FormatName } from "../lib/format";
import { resolvePointer } from "./pointer";

/**
 * Every business value the app shows goes through this component: it names the file
 * (the scenario's report, the index, or the comparison), a pointer into it, a unit and
 * one of the named formats. The browser formats; it calculates nothing.
 */
export type SourceName = "report" | "index" | "comparison";
type Unit = "usd" | "fraction" | "count" | "date" | "month" | "text";

const FORMATS: Record<Unit, FormatName[]> = {
  usd: ["usd-full", "usd-short"],
  fraction: ["percent1"],
  count: ["count"],
  date: ["date"],
  month: ["month"],
  text: ["text"],
};

export interface Binding {
  /** a stable name; the screen's committed list and the tests refer to it */
  id: string;
  source: SourceName;
  /** JSON pointer into the file; for a row binding, relative to the row */
  path: string;
  unit: Unit;
  format: FormatName;
  /**
   * If the file may hold null here, how it is said in words: the pointer to the sentence that
   * gives the reason (relative to the row unless ``absolute``), or the words themselves.
   */
  unavailable?: { reason?: string; words?: string; absolute?: boolean };
  /** "shortfall": a positive figure is a shortfall (red), a negative one is ahead (green) */
  tint?: "shortfall";
}

export function bind(b: Omit<Binding, "source"> & { source?: SourceName }): Binding {
  if (!FORMATS[b.unit].includes(b.format)) {
    throw new Error(`binding ${b.id}: format ${b.format} does not belong to unit ${b.unit}`);
  }
  return { source: "report", ...b };
}

interface Files {
  report: TieoutReport;
  index: ReportIndex;
  comparison: ScenarioComparison;
}
interface BindingContextValue {
  company: string;
  scenario: string;
  files: Files;
}

const BindingContext = createContext<BindingContextValue | null>(null);

export function BindingProvider({
  company,
  scenario,
  files,
  children,
}: BindingContextValue & { children: ReactNode }) {
  return <BindingContext.Provider value={{ company, scenario, files }}>{children}</BindingContext.Provider>;
}

export function useBindingContext(): BindingContextValue {
  const value = useContext(BindingContext);
  if (!value) throw new Error("a binding needs a BindingProvider");
  return value;
}

/** The pointer a binding reads: the row's, then the binding's, with the visitor's choice filled in. */
function expandPath(path: string, ctx: { company: string; scenario: string }): string {
  return path.replace(/\{company\}/g, ctx.company).replace(/\{scenario\}/g, ctx.scenario);
}

/** The value a binding names, read from the file (the whole pointer: row prefix plus path). */
export function readBinding(ctx: BindingContextValue, binding: Binding, row = ""): unknown {
  return resolvePointer(ctx.files[binding.source], expandPath(row + binding.path, ctx), {
    nullBelowNull: binding.unavailable !== undefined,
  });
}

const TONES = {
  "-1": { tone: "ahead", className: "text-green-700" },
  "0": { tone: "level", className: "" },
  "1": { tone: "short", className: "text-red-700" },
} as const;

export function Bound({ binding, row = "", className }: { binding: Binding; row?: string; className?: string }) {
  const ctx = useBindingContext();
  const path = expandPath(row + binding.path, ctx);
  const attrs = {
    "data-binding": binding.id,
    "data-source": binding.source,
    "data-path": path,
    "data-format": binding.format,
    "data-company": ctx.company,
    "data-scenario": ctx.scenario,
  };
  const value = readBinding(ctx, binding, row);
  if (value === null) {
    const say = binding.unavailable;
    if (!say) throw new Error(`binding ${binding.id} (${path}) is null in the file and says nothing about why`);
    let shown = say.words ?? "unavailable";
    if (say.reason) {
      const reasonPath = expandPath((say.absolute ? "" : row) + say.reason, ctx);
      shown = `unavailable: ${formatValue("text", resolvePointer(ctx.files[binding.source], reasonPath))}`;
    }
    return (
      <span {...attrs} data-unavailable="true" className={className}>
        {shown}
      </span>
    );
  }
  const tone = binding.tint ? TONES[String(signOf(value)) as keyof typeof TONES] : null;
  return (
    <span
      {...attrs}
      {...(tone ? { "data-tone": tone.tone } : {})}
      className={[className, tone?.className].filter(Boolean).join(" ") || undefined}
    >
      {formatValue(binding.format, value)}
    </span>
  );
}
