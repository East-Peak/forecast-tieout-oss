/**
 * Test-only. The small kit every screen's independently written expectations are built with: what the
 * screen must show once, in several places, per row of a collection, or (for a variant) not at all.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { B } from "../forecast/bindings";
import * as fmt from "./independent";

export const orWords = (value: string | null, shown: (v: string) => string, words = "unavailable") =>
  value === null ? words : shown(value);

export function kit() {
  const expected: Expectation[] = [];
  const absent: Absent[] = [];
  /** `times`: how many places the screen deliberately shows the same bound value */
  const one = (id: string, text: string, times = 1) => expected.push({ id, texts: Array<string>(times).fill(text) });
  const many = (id: string, texts: string[], rows?: string[]) => {
    if (texts.length === 0) absent.push({ id });
    else expected.push({ id, texts, rows });
  };
  const when = (condition: boolean, id: string, text: () => string, times = 1) => (condition ? one(id, text(), times) : absent.push({ id }));
  return { expected, absent, one, many, when };
}

/**
 * The better-than-baselines verdict card, written independently of the screen: the verdict, its reason
 * in words, and (when there is a verdict) a row per verdict horizon with the model's error, each baseline's
 * error and which is lower. Shared by the Forecast and Trust expectations, which both show the card.
 */
export function betterVerdictExpectations(
  r: TieoutReport,
  put: {
    one: (id: string, text: string) => void;
    many: (id: string, texts: string[], rows?: string[]) => void;
  },
): void {
  const v = r.verdicts.forecast_better_than_baselines;
  const rows = v.comparisons.map((_, i) => `/verdicts/forecast_better_than_baselines/comparisons/${i}`);
  put.one(B.betterVerdict.id, v.verdict);
  put.one(B.betterReason.id, v.in_words);
  put.many(B.cmpMonths.id, v.comparisons.map((c) => fmt.quantity(c.horizon_months)), rows);
  put.many(B.cmpModel.id, v.comparisons.map((c) => fmt.usdShort(c.model_error)), rows);
  put.many(B.cmpStage.id, v.comparisons.map((c) => fmt.usdShort(c.against["stage-weighted pipeline"].baseline_error)), rows);
  put.many(B.cmpStageOutcome.id, v.comparisons.map((c) => c.against["stage-weighted pipeline"].outcome), rows);
  put.many(B.cmpRunRate.id, v.comparisons.map((c) => fmt.usdShort(c.against["trailing run-rate"].baseline_error)), rows);
  put.many(B.cmpRunRateOutcome.id, v.comparisons.map((c) => c.against["trailing run-rate"].outcome), rows);
}
