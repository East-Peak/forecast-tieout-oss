import { useEffect, useRef, useState, type ReactNode } from "react";
import type { RateProvenance } from "../../types/snapshot";

export interface RateProvenancePopoverProps {
  /** Short human label for the rate being described (e.g. "MQL → S0"). */
  label: string;
  rate: RateProvenance;
  children: ReactNode;
}

export function RateProvenancePopover({
  label,
  rate,
  children,
}: RateProvenancePopoverProps) {
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const handleClick = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        !triggerRef.current?.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", handleKey);
    document.addEventListener("mousedown", handleClick);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("mousedown", handleClick);
    };
  }, [open]);

  const nDisplay =
    rate.n === null || rate.n === undefined ? "—" : rate.n.toLocaleString();

  return (
    <span className="relative inline-block">
      <button
        ref={triggerRef}
        type="button"
        className="underline decoration-dotted decoration-slate-400 underline-offset-2 hover:text-blue-700"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((s) => !s)}
      >
        {children}
      </button>
      {open && (
        <div
          ref={popoverRef}
          role="dialog"
          className="absolute left-0 top-full z-20 mt-1 w-72 rounded-md border border-slate-200 bg-white p-3 text-xs shadow-lg"
        >
          <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
            {label}
          </div>
          <div className="text-sm font-semibold text-slate-800 mb-2">
            {(rate.value * 100).toFixed(2)}%
          </div>
          <dl className="space-y-1 text-slate-600">
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">Source</dt>
              <dd className="text-right">{rate.source}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">Sample</dt>
              <dd className="text-right">n = {nDisplay}</dd>
            </div>
            {rate.lookback_days !== undefined && (
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Window</dt>
                <dd className="text-right">{rate.lookback_days}d lookback</dd>
              </div>
            )}
            {rate.date_range && (
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Range</dt>
                <dd className="text-right">
                  {rate.date_range.start} → {rate.date_range.end}
                </dd>
              </div>
            )}
            {rate.calibrated_at && (
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Calibrated</dt>
                <dd className="text-right">calibrated {rate.calibrated_at}</dd>
              </div>
            )}
          </dl>
          <div className="mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-600 leading-snug">
            {rate.methodology}
          </div>
        </div>
      )}
    </span>
  );
}
