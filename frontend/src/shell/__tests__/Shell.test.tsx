import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import App from "../../App";
import { unboundDigits } from "../../binding/__tests__/harness";
import * as files from "../../screens/__tests__/files";
import type { Loaders } from "../../session/ReportSession";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const fromDisk: Loaders = {
  index: () => Promise.resolve(files.index()),
  report: (path) => {
    const [company, file] = path.split("/");
    return Promise.resolve(files.report(company, file.replace(".json", "")));
  },
  comparison: (path) => Promise.resolve(files.comparison(path.split("/")[0])),
};

function open(url: string, loaders: Loaders = fromDisk) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <App loaders={loaders} />
    </MemoryRouter>,
  );
}

describe("the shell", () => {
  it("opens on Forecast for the index's default company, with the five screens in the nav", async () => {
    open("/");
    const nav = screen.getByRole("navigation", { name: "Screens" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Forecast", "Capacity", "Pipeline", "Plan", "Trust"]);
    await waitFor(() => expect(document.querySelector("[data-chart='monthly']")).not.toBeNull());
    expect((document.getElementById("company-selector") as HTMLSelectElement).value).toBe(files.index().default_company);
  });

  it("takes the company and scenario from the URL, and describes the company from index.json", async () => {
    open("/forecast?company=sprout-labs&scenario=hires-only");
    await waitFor(() => expect(screen.getByTestId("company-description")).toBeInTheDocument());
    const sprout = files.index().companies.find((c) => c.id === "sprout-labs")!;
    expect(screen.getByTestId("company-description").textContent).toBe(sprout.description);
    expect((document.getElementById("scenario-selector") as HTMLSelectElement).value).toBe("hires-only");
    expect(document.querySelector("[data-binding='scenario.label']")?.textContent).toBe("Hires only");
  });

  it("every digit in the whole page, header included, is in a bound element", async () => {
    open("/forecast?company=mighty-oak-holdings&scenario=demo-plan");
    await waitFor(() => expect(document.querySelector("[data-chart='monthly']")).not.toBeNull());
    expect(unboundDigits(document.body)).toEqual([]);
  });

  it("switching company loads that company's report and moves the URL", async () => {
    open("/forecast?company=sprout-labs");
    await waitFor(() => expect(document.querySelector("[data-binding='year.target']")?.getAttribute("data-company")).toBe("sprout-labs"));
    fireEvent.change(document.getElementById("company-selector")!, { target: { value: "mighty-oak-holdings" } });
    await waitFor(() => expect(document.querySelector("[data-binding='year.target']")?.getAttribute("data-company")).toBe("mighty-oak-holdings"));
    const target = files.report("mighty-oak-holdings", "as-signed").gap.fiscal_year.target;
    expect(document.querySelector("[data-binding='year.target']")?.getAttribute("data-path")).toBe("/gap/fiscal_year/target");
    expect(target).toBeTruthy();
  });

  it("the four screens not built yet say so, with no numbers", async () => {
    for (const path of ["capacity", "pipeline", "plan", "trust"]) {
      const { unmount } = open(`/${path}?company=sprout-labs&scenario=as-signed`);
      await waitFor(() => expect(screen.getByTestId("not-built")).toBeInTheDocument());
      expect(screen.getByTestId("not-built").textContent).toMatch(/Not built yet/);
      const main = document.querySelector("main")!;
      expect(main.textContent).not.toMatch(/\d/);
      expect(main.querySelectorAll("[data-binding]").length).toBe(0);
      unmount();
    }
  });

  it("an old address leads to Forecast, keeping the company", async () => {
    open("/bookings?company=sprout-labs&scenario=as-signed");
    await waitFor(() => expect(document.querySelector("[data-chart='monthly']")).not.toBeNull());
  });

  it("shows a loading state first, and an error that names the problem when a report fails", async () => {
    const broken: Loaders = { ...fromDisk, report: () => Promise.reject(new Error("sprout-labs/as-signed.json: HTTP 404")) };
    open("/forecast?company=sprout-labs", broken);
    expect(screen.getByTestId("session-status").textContent).toMatch(/Loading/);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/HTTP 404/));
    // the selectors are still there to choose something else
    expect(document.getElementById("company-selector")).not.toBeNull();
  });

  it("an index that cannot be read is an error, not a blank page", async () => {
    open("/forecast", { ...fromDisk, index: () => Promise.reject(new Error("index.json: HTTP 500")) });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/HTTP 500/));
  });
});
