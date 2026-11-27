import type { Selection } from "./sessionState";

/** A new key: nothing the old snapshot session stored is read. */
export const STORAGE_KEY = "forecast-tieout:report-session:v1";

export function readStoredSelection(): Selection | null {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (parsed && typeof parsed === "object") {
      const { company, scenario } = parsed as Record<string, unknown>;
      if (typeof company === "string" && typeof scenario === "string") return { company, scenario };
    }
  } catch {
    // storage blocked or content damaged: the session works without it
  }
  return null;
}

export function writeStoredSelection(selection: Selection): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // storage blocked: nothing to remember with
  }
}
