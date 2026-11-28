/**
 * A win-rate target is typed as a percent and sent to the core as a probability. The point is moved in the text,
 * two places, so a digit typed is a digit sent: nothing is calculated, and nothing is rounded on the way.
 */
const PLAIN = /^(\d*)(?:\.(\d*))?$/;

/** A percent as typed ("26.5") as the probability string the core reads ("0.265"); anything that is not a plain number is passed on as typed, for the core to refuse in its own words. */
export function probabilityOf(typed: string): string {
  const text = typed.trim();
  const found = PLAIN.exec(text);
  if (!found || text === "" || text === ".") return text;
  const whole = (found[1] ?? "").padStart(2, "0");
  const head = whole.slice(0, -2).replace(/^0+/, "") || "0";
  return `${head}.${whole.slice(-2)}${found[2] ?? ""}`;
}

/** A probability ("0.2193", or a number) as the percent the visitor types ("21.93"); a value that is not a plain decimal is shown as it is. */
export function percentText(probability: string | number): string {
  const text = String(probability);
  const found = PLAIN.exec(text);
  if (!found || text === "" || text === ".") return text;
  const digits = (found[2] ?? "").padEnd(2, "0");
  const whole = `${found[1] || "0"}${digits.slice(0, 2)}`.replace(/^0+/, "") || "0";
  const rest = digits.slice(2).replace(/0+$/, "");
  return rest === "" ? whole : `${whole}.${rest}`;
}
