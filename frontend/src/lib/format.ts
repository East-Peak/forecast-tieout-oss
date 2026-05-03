export function formatMoney(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function formatMonthLabel(m: string): string {
  // Handle both "2026-02" and "2026-02-01" formats
  const normalized = m.length <= 7 ? m + "-01" : m;
  const d = new Date(normalized + "T00:00:00");
  const month = d.toLocaleDateString("en-US", { month: "short" });
  const year = d.toLocaleDateString("en-US", { year: "2-digit" });
  return `${month} '${year}`;
}

export function formatIsoDate(dateIso: string): string {
  return new Date(`${dateIso}T00:00:00`).toLocaleDateString("en-US");
}
