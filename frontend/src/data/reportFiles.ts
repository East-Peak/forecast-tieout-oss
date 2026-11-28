import type { ReportIndex, ScenarioComparison } from "../generated/appFiles";
import type { TieoutReport } from "../generated/report";
import type { LanesLoaders } from "../lanes/types";
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

/** The swimlane grid's files, fetched when the grid opens (the owners' of a segment when it is expanded, the records and the basis when a cell is). */
export const fileLanesLoaders: LanesLoaders = {
  lanes: (path) => getJson(path),
  owners: (path) => getJson(path),
  basis: (path) => getJson(path),
  records: (path) => getJson(path),
};
