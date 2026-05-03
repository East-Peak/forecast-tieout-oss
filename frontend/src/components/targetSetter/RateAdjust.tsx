import { Text } from "../ui";

type RateKey = "mql_to_s0" | "s0_to_s1" | "s1_to_s2" | "win_rate_created";
type Rates = Record<RateKey, number>;

export interface RateAdjustProps {
  rates: Rates;
  /** Called with a partial update (just the edited field). */
  onChange: (partial: Partial<Rates>) => void;
  /** Show the Reset control when rates can be reverted to baseline (i.e. not Observed). */
  canReset: boolean;
  onReset: () => void;
}

const FIELDS: { key: RateKey; label: string }[] = [
  { key: "mql_to_s0", label: "MQL → S0" },
  { key: "s0_to_s1", label: "S0 → S1" },
  { key: "s1_to_s2", label: "S1 → S2" },
  { key: "win_rate_created", label: "S2 → Won" },
];

export function RateAdjust({ rates, onChange, canReset, onReset }: RateAdjustProps) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <Text className="text-xs uppercase tracking-wide text-slate-500 font-semibold pb-1.5">
        Adjust rates
      </Text>
      {FIELDS.map(({ key, label }) => (
        <div key={key} className="flex flex-col gap-0.5">
          <label className="text-[11px] text-slate-500" htmlFor={`rate-${key}`}>
            {label}
          </label>
          <div className="flex items-center gap-1">
            <input
              id={`rate-${key}`}
              type="number"
              step={0.5}
              min={0}
              max={100}
              value={Number((rates[key] * 100).toFixed(2))}
              onChange={(e) => {
                const pct = parseFloat(e.target.value);
                if (Number.isNaN(pct)) return;
                const clamped = Math.max(0, Math.min(100, pct));
                onChange({ [key]: clamped / 100 } as Partial<Rates>);
              }}
              className="w-20 border border-slate-300 rounded px-2 py-1 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label={`${label} conversion rate, percent`}
            />
            <span className="text-xs text-slate-500">%</span>
          </div>
        </div>
      ))}
      {canReset && (
        <button
          type="button"
          onClick={onReset}
          className="text-xs text-slate-500 underline hover:text-slate-800 pb-1.5"
        >
          Reset
        </button>
      )}
    </div>
  );
}
