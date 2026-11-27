import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { unboundDigits } from "../../binding/__tests__/harness";
import { Verdicts } from "../forecast/Verdicts";
import * as files from "./files";
import { caseOf, mountScreen } from "./screenChecks";

afterEach(cleanup);

const card = (container: HTMLElement) => container.querySelectorAll("[data-testid='verdict-card']")[1] as HTMLElement;

describe("the card 'Is the fitted forecast better than the baselines?'", () => {
  it("says the verdict and its reason in words, then compares the errors under the screen's own method names", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const container = mountScreen(Verdicts, c, c.company, c.scenario);
    const text = card(container).textContent!;
    expect(container.querySelector("[data-binding='verdict.better']")!.textContent).toBe("no");
    expect(text).toContain("The fitted model's average miss is not smaller than both simple yardsticks three months ahead.");
    for (const heading of ["Fitted model", "Stage-weighted pipeline", "Last twelve months' pace"]) expect(text).toContain(heading);
    expect(text).not.toContain("Trailing run-rate");
    expect(text).not.toContain("trailing run-rate");
    expect(text).not.toContain("1,944,676"); // the report's sentence, with its raw figures, is not printed
    expect(card(container).querySelectorAll("[data-testid='verdict-comparison-row']")).toHaveLength(2);
  });

  it("shows which error is lower for each baseline at each horizon, as the report decided it", () => {
    const c = caseOf("sapling-industries", "as-signed");
    const container = mountScreen(Verdicts, c, c.company, c.scenario);
    const outcomes = [...card(container).querySelectorAll("[data-binding$='.outcome']")].map((e) => e.textContent);
    expect(outcomes).toEqual(
      c.report.verdicts.forecast_better_than_baselines.comparisons.flatMap((x) => [
        x.against["stage-weighted pipeline"].outcome,
        x.against["trailing run-rate"].outcome,
      ]),
    );
    expect(outcomes).toContain("model lower");
    expect(outcomes).toContain("baseline lower");
  });

  it("is laid out like the app's other tables, so on a phone each horizon stacks as labeled lines", () => {
    const c = caseOf("mighty-oak-holdings", "as-signed");
    const container = mountScreen(Verdicts, c, c.company, c.scenario);
    const table = card(container).querySelector("table")!;
    expect(table.className).toContain("block sm:table");
    const row = table.querySelector("[data-testid='verdict-comparison-row']")!;
    expect([...row.querySelectorAll("td")].map((td) => td.getAttribute("data-label"))).toEqual([
      "Months ahead",
      "Fitted model",
      "Stage-weighted pipeline",
      "Last twelve months' pace",
    ]);
  });

  it("a yes reads as yes in green, with every outcome 'model lower'", () => {
    const c = caseOf("sprout-labs", "as-signed");
    const container = mountScreen(Verdicts, c, c.company, c.scenario);
    expect(container.querySelector("[data-binding='verdict.better']")!.textContent).toBe("yes");
    expect(card(container).textContent).toContain("smaller than both simple yardsticks, one month ahead and three months ahead.");
    const outcomes = [...card(container).querySelectorAll("[data-binding$='.outcome']")].map((e) => e.textContent);
    expect(outcomes).toEqual(["model lower", "model lower", "model lower", "model lower"]);
  });

  it.each(["short-history.report.json", "short-history-plan.report.json"])(
    "not enough history reads in words with its reason, and shows no comparison (%s)",
    (name) => {
      const shown = { report: files.fixture(name), index: files.index(), comparison: files.comparison("sprout-labs") };
      const container = mountScreen(Verdicts, shown, "sprout-labs", "as-signed");
      const text = card(container).textContent!;
      expect(container.querySelector("[data-binding='verdict.better']")!.textContent).toBe("not enough history to say");
      expect(text).toContain("The past cannot be scored in dollars without a record of past open deals, so there is nothing to compare.");
      expect(card(container).querySelector("[data-testid='verdict-comparison-row']")).toBeNull();
      expect(card(container).querySelector("table")).toBeNull();
      expect(unboundDigits(container)).toEqual([]);
    },
  );
});
