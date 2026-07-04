type DataBasisBadgeTone = "actualProjected" | "projected";

export interface DataBasisBadgeConfig {
  label: "Actual + Projected" | "Projected";
  tone: DataBasisBadgeTone;
}

export function getDataBasisBadge(actualValue: number | null | undefined): DataBasisBadgeConfig {
  if (typeof actualValue === "number" && actualValue > 0) {
    return { label: "Actual + Projected", tone: "actualProjected" };
  }
  return { label: "Projected", tone: "projected" };
}
