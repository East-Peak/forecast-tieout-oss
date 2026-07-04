type VerdictTone = "positive" | "negative" | "neutral";

export interface VerdictTint {
  tone: VerdictTone;
  cellClassName: string;
  metricClassName: string;
}

const VERDICT_TINTS: Record<VerdictTone, VerdictTint> = {
  negative: {
    tone: "negative",
    cellClassName: "bg-red-50 text-red-700",
    metricClassName: "border-red-100 bg-red-50 text-red-700",
  },
  positive: {
    tone: "positive",
    cellClassName: "bg-green-50 text-green-700",
    metricClassName: "border-green-100 bg-green-50 text-green-700",
  },
  neutral: {
    tone: "neutral",
    cellClassName: "bg-slate-50 text-slate-500",
    metricClassName: "border-slate-200 bg-slate-50 text-slate-600",
  },
};

export function getVerdictTint(value: number | null | undefined): VerdictTint {
  if (typeof value !== "number") return VERDICT_TINTS.neutral;
  return value < 0 ? VERDICT_TINTS.negative : VERDICT_TINTS.positive;
}
