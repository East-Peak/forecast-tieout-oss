export type ToplineHealthStatus = "healthy" | "warning" | "critical";

export function normalizeToplineHealthStatus(
  rawStatus: string | undefined,
  capacityWarningCount: number,
): ToplineHealthStatus {
  const normalized = rawStatus?.trim().toLowerCase();

  if (
    normalized === "green" ||
    normalized === "ok" ||
    normalized === "aligned" ||
    normalized === "healthy"
  ) {
    return "healthy";
  }

  if (normalized === "yellow" || normalized === "warning") {
    return "warning";
  }

  if (normalized === "red" || normalized === "diverged" || normalized === "critical") {
    return "critical";
  }

  if (capacityWarningCount === 0) {
    return "healthy";
  }

  if (capacityWarningCount <= 2) {
    return "warning";
  }

  return "critical";
}
