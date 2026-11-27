import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { TieoutReport } from "../generated/report";
import type { Loaders } from "../session/ReportSession";

const BASE = `${import.meta.env.BASE_URL}data/reports/`;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(BASE + path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

/** The three files the app reads, all written by the core's generator and checked into the repo. */
export const fileLoaders: Loaders = {
  index: () => getJson<ReportIndex>("index.json"),
  report: (path) => getJson<TieoutReport>(path),
  comparison: (path) => getJson<ScenarioComparison>(path),
};
