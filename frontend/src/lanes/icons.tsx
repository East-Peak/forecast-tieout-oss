/** Two small marks for a cell's footer: a gauge for the forecast, a target for the goal. */
export function GaugeIcon() {
  return (
    <svg viewBox="0 0 12 12" className="h-3 w-3 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
      <path d="M1.5 9.5a4.5 4.5 0 1 1 9 0" strokeLinecap="round" />
      <path d="M6 9 8.2 5.2" strokeLinecap="round" />
      <circle cx="6" cy="9" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function TargetIcon() {
  return (
    <svg viewBox="0 0 12 12" className="h-3 w-3 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
      <circle cx="6" cy="6" r="4.4" />
      <circle cx="6" cy="6" r="1.7" />
    </svg>
  );
}
