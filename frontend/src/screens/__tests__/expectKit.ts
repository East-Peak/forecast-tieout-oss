/**
 * Test-only. The small kit every screen's independently written expectations are built with: what the
 * screen must show once, in several places, per row of a collection, or (for a variant) not at all.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";

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
