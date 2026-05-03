import type { ScenarioOption } from "../../types/targetSetter";

export interface ScenarioSelectorProps {
  activeId: string;
  scenarios: ScenarioOption[];
  onSelect: (id: string) => void;
}

export function ScenarioSelector({
  activeId,
  scenarios,
  onSelect,
}: ScenarioSelectorProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {scenarios.map((s) => {
        const active = s.id === activeId;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            aria-pressed={active}
            className={`text-left px-4 py-2 rounded-md border transition-colors ${
              active
                ? "bg-blue-600 border-blue-600 text-white"
                : "bg-white border-slate-200 text-slate-800 hover:border-slate-300"
            }`}
          >
            <div className="text-sm font-semibold uppercase tracking-wide flex items-center gap-1.5">
              {active && <span className="inline-block w-1.5 h-1.5 rounded-full bg-white" />}
              {s.label}
            </div>
            <div className={`text-xs mt-1 ${active ? "text-blue-100" : "text-slate-500"}`}>
              {s.primaryLine}
            </div>
            <div className={`text-xs ${active ? "text-blue-100" : "text-slate-400"}`}>
              {s.secondaryLine}
            </div>
          </button>
        );
      })}
    </div>
  );
}
