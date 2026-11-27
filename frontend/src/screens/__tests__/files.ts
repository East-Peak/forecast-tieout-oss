/** Test-only: the committed report files, read from disk, exactly as the app fetches them. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";

const ROOT = resolve(__dirname, "../../../public/data/reports");
const read = <T>(path: string): T => JSON.parse(readFileSync(resolve(ROOT, path), "utf8")) as T;

export const COMPANIES = ["sprout-labs", "sapling-industries", "mighty-oak-holdings"] as const;
export const SCENARIOS = ["as-signed", "demo-plan", "hires-only", "programme-only"] as const;

export const index = (): ReportIndex => read<ReportIndex>("index.json");
export const comparison = (company: string): ScenarioComparison => read<ScenarioComparison>(`${company}/comparison.json`);
export const report = (company: string, scenario: string): TieoutReport => read<TieoutReport>(`${company}/${scenario}.json`);
export const fixture = (name: string): TieoutReport =>
  JSON.parse(readFileSync(resolve(__dirname, "fixtures", name), "utf8")) as TieoutReport;
