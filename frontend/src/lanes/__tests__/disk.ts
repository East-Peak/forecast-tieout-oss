/** Test-only: the committed lanes files, read from disk exactly as the app fetches them (paths as the index gives them). */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReportIndex } from "../../generated/appFiles";
import type { BasisFile, LanesAny, LanesFile, LanesLoaders, OwnersFile, RecordsFile } from "../types";

const ROOT = resolve(__dirname, "../../../public/data/reports");
const read = <T>(path: string): T => JSON.parse(readFileSync(resolve(ROOT, path), "utf8")) as T;

export const diskLoaders: LanesLoaders = {
  lanes: (path) => Promise.resolve(read<LanesAny>(path)),
  owners: (path) => Promise.resolve(read<OwnersFile>(path)),
  basis: (path) => Promise.resolve(read<BasisFile>(path)),
  records: (path) => Promise.resolve(read<RecordsFile>(path)),
};

export const lanesOf = (company: string, scenario: string): LanesFile => read<LanesFile>(`${company}/lanes-${scenario}.json`);
/** A segment's owners, at the path the index gives for it (a segment's key is its name in the lanes file, not a file name). */
export const ownersOf = (company: string, scenario: string, segment: string): OwnersFile => {
  const index = read<ReportIndex>("index.json");
  const path = index.companies.find((c) => c.id === company)!.scenarios.find((s) => s.id === scenario)!.lanes_owners![segment]!;
  return read<OwnersFile>(path);
};
export const basisOf = (company: string): BasisFile => read<BasisFile>(`${company}/lanes-basis.json`);
export const recordsOf = (company: string): RecordsFile => read<RecordsFile>(`${company}/lanes-records.json`);
