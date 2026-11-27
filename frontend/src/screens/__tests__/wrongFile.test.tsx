import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import App from "../../App";
import type { Loaders } from "../../session/ReportSession";
import * as files from "./files";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const SCREENS = ["forecast", "capacity", "pipeline", "plan", "trust"] as const;
const ASKED = { company: "sapling-industries", scenario: "demo-plan" };

/** The disk's files, except that the file asked for is replaced by another (the identity asked for stays in the URL and the index). */
function serving(wrong: ReturnType<typeof files.report>): Loaders {
  return {
    index: () => Promise.resolve(files.index()),
    report: (path) => {
      const [company, file] = path.split("/");
      const scenario = file.replace(".json", "");
      return Promise.resolve(company === ASKED.company && scenario === ASKED.scenario ? wrong : files.report(company, scenario));
    },
    comparison: (path) => Promise.resolve(files.comparison(path.split("/")[0])),
  };
}

describe("a wrong file served under the identity asked for is refused on every screen", () => {
  const cases = [
    ["another scenario's report", () => files.report(ASKED.company, "as-signed")],
    ["another company's report", () => files.report("sprout-labs", ASKED.scenario)],
    ["another company's as-signed report", () => files.report("mighty-oak-holdings", "as-signed")],
  ] as const;

  for (const screenName of SCREENS) {
    for (const [what, wrong] of cases) {
      it(`${screenName}: ${what}`, async () => {
        render(
          <MemoryRouter initialEntries={[`/${screenName}?company=${ASKED.company}&scenario=${ASKED.scenario}`]}>
            <App loaders={serving(wrong())} />
          </MemoryRouter>,
        );
        await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/is the report for/));
        expect(document.querySelectorAll("main [data-binding]").length).toBe(0);
        expect(screen.getByRole("alert").textContent).toContain(`${ASKED.company}/${ASKED.scenario}`);
      });
    }
  }

  it("the right file is shown", async () => {
    render(
      <MemoryRouter initialEntries={[`/plan?company=${ASKED.company}&scenario=${ASKED.scenario}`]}>
        <App loaders={serving(files.report(ASKED.company, ASKED.scenario))} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(document.querySelectorAll("main [data-binding]").length).toBeGreaterThan(10));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
