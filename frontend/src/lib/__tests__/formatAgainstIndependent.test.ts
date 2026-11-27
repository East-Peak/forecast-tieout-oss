import { describe, expect, it } from "vitest";
import * as files from "../../screens/__tests__/files";
import * as independent from "../../screens/__tests__/independent";
import { formatValue } from "../format";

/** Every money string in every committed report file: the formatter and the test's own implementation agree. */
function moneyStrings(node: unknown, out: string[] = []): string[] {
  if (typeof node === "string" && /^-?\d+\.\d{2}$/.test(node)) out.push(node);
  else if (Array.isArray(node)) node.forEach((n) => moneyStrings(n, out));
  else if (node && typeof node === "object") Object.values(node).forEach((n) => moneyStrings(n, out));
  return out;
}

describe("the formatter agrees with an independent implementation on the report's own numbers", () => {
  const values = [
    ...new Set(
      files.COMPANIES.flatMap((company) =>
        files.SCENARIOS.flatMap((scenario) => moneyStrings(files.report(company, scenario))),
      ),
    ),
  ];

  it("reads a good sample of figures", () => {
    expect(values.length).toBeGreaterThan(1000);
  });

  it("usd-short", () => {
    const wrong = values.filter((v) => formatValue("usd-short", v) !== independent.usdShort(v));
    expect(wrong.slice(0, 5)).toEqual([]);
  });

  it("usd-full", () => {
    const wrong = values.filter((v) => formatValue("usd-full", v) !== independent.usdFull(v));
    expect(wrong.slice(0, 5)).toEqual([]);
  });

  it("percent1 on the back-test coverages", () => {
    for (const company of files.COMPANIES) {
      for (const cell of files.report(company, "as-signed").forecasts.fitted_ranges.cells) {
        for (const c of [cell.coverage80, cell.coverage95]) {
          if (c !== null) expect(formatValue("percent1", c)).toBe(independent.percent1(c));
        }
      }
    }
  });
});
