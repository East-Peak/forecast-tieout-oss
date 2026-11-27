import { useId, useState } from "react";
import type { ReactNode } from "react";

interface Props {
  title: string;
  hint?: string;
  /** open when first shown (the reader can still close it) */
  initiallyOpen?: boolean;
  children: ReactNode;
}

/** A section the reader opens: a button that shows or hides its content. */
export function Disclosure({ title, hint, initiallyOpen = false, children }: Props) {
  const [open, setOpen] = useState(initiallyOpen);
  const panel = useId();
  return (
    <div className="rounded-ft border border-slate-200 bg-white shadow-ft">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left"
      >
        <span>
          <span className="block text-sm font-semibold text-ft-brand">{title}</span>
          {hint ? <span className="block text-xs text-slate-500">{hint}</span> : null}
        </span>
        <span aria-hidden="true" className="text-slate-400">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open ? (
        <div id={panel} className="border-t border-slate-100 px-5 py-4">
          {children}
        </div>
      ) : null}
    </div>
  );
}
