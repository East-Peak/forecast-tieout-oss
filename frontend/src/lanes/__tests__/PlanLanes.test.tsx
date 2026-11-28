import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import App from "../../App";
import { BindingProvider } from "../../binding/Bound";
import { caseOf } from "../../screens/__tests__/screenChecks";
import { usdShort } from "../../screens/__tests__/independent";
import * as files from "../../screens/__tests__/files";
import type { Loaders } from "../../session/ReportSession";
import { LanesProvider } from "../LanesContext";
import LanesSection from "../LanesSection";
import type { LanesAny, LanesLoaders } from "../types";
import { diskLoaders, lanesOf } from "./disk";

afterEach(cleanup);

const fromDisk: Loaders = {
  index: () => Promise.resolve(files.index()),
  report: (path) => {
    const [company, file] = path.split("/");
    return Promise.resolve(files.report(company, file.replace(".json", "")));
  },
  comparison: (path) => Promise.resolve(files.comparison(path.split("/")[0])),
};

const bookings = (company: string, scenario: string) => lanesOf(company, scenario).periods[0].rows[0].cells.bookings.forecast;

describe("the Plan screen's grid follows the company and scenario in the page", () => {
  it("is on Plan in place of the chain table, and picking another scenario reloads the lanes of that scenario", async () => {
    render(
      <MemoryRouter initialEntries={["/plan?company=sapling-industries&scenario=as-signed"]}>
        <App loaders={fromDisk} lanes={diskLoaders} desktop={false} />
      </MemoryRouter>,
    );
    const grid = await screen.findByTestId("lanes-grid", undefined, { timeout: 30_000 });
    expect(screen.queryByTestId("chain")).toBeNull();
    const total = () => grid.ownerDocument.querySelector("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.forecast']")!;
    expect(total().getAttribute("data-scenario")).toBe("as-signed");
    expect(total().textContent).not.toBe("");

    fireEvent.change(document.querySelector("#scenario-selector")!, { target: { value: "demo-plan" } });
    // wait on content that proves the new scenario: the grid's own figures carry the scenario they were drawn for
    await waitFor(() => expect(total().getAttribute("data-scenario")).toBe("demo-plan"));
    expect(bookings("sapling-industries", "demo-plan")).not.toBe(bookings("sapling-industries", "as-signed"));
    expect(total().getAttribute("data-path")).toBe("/periods/0/rows/0/cells/bookings/forecast");
  });

  it("an answer for a company the visitor has left is dropped", async () => {
    const pending = new Map<string, (doc: LanesAny) => void>();
    const slow: LanesLoaders = { ...diskLoaders, lanes: (path) => new Promise((resolve) => pending.set(path, resolve)) };
    const view = (company: string) => {
      const c = caseOf(company, "as-signed");
      return (
        <BindingProvider company={company} scenario="as-signed" files={c}>
          <LanesProvider loaders={slow}>
            <LanesSection />
          </LanesProvider>
        </BindingProvider>
      );
    };
    const { rerender } = render(view("sapling-industries"));
    await waitFor(() => expect(pending.has("sapling-industries/lanes-as-signed.json")).toBe(true));
    rerender(view("sprout-labs"));
    await waitFor(() => expect(pending.has("sprout-labs/lanes-as-signed.json")).toBe(true));
    pending.get("sprout-labs/lanes-as-signed.json")!(lanesOf("sprout-labs", "as-signed"));
    await screen.findByTestId("lanes-grid");
    pending.get("sapling-industries/lanes-as-signed.json")!(lanesOf("sapling-industries", "as-signed"));
    await new Promise((r) => setTimeout(r, 50));
    const figure = document.querySelector("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.actual']")!;
    expect(figure.getAttribute("data-company")).toBe("sprout-labs");
    expect(document.querySelectorAll("[data-testid='lanes-grid']")).toHaveLength(1);
  });
});

describe("your plan", () => {
  it("with no plan applied yet shows no as-signed forecast in its place, and no note that the lanes ignore the edits (the lanes of an Apply are in YourPlanLanes.test)", async () => {
    const c = caseOf("sapling-industries", "as-signed");
    render(
      <BindingProvider company="sapling-industries" scenario="your-plan" files={c}>
        <LanesProvider loaders={diskLoaders}>
          <LanesSection />
        </LanesProvider>
      </BindingProvider>,
    );
    await screen.findByTestId("lanes-grid");
    expect(screen.queryByTestId("your-plan-note")).toBeNull();
    expect(screen.getByTestId("lanes-pending")).toBeTruthy();
    expect(document.querySelector("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.forecast']")).toBeNull();
    // the actual is the as-signed lanes': it does not depend on the plan
    const actual = document.querySelector("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.actual']")!;
    expect(actual.getAttribute("data-scenario")).toBe("your-plan");
    expect(actual.textContent).toBe(usdShort(lanesOf("sapling-industries", "as-signed").periods[0].rows[0].cells.bookings.actual!));
  });

  it("says nothing of it for a named scenario", async () => {
    const c = caseOf("sapling-industries", "demo-plan");
    render(
      <BindingProvider company="sapling-industries" scenario="demo-plan" files={c}>
        <LanesProvider loaders={diskLoaders}>
          <LanesSection />
        </LanesProvider>
      </BindingProvider>,
    );
    await screen.findByTestId("lanes-grid");
    expect(screen.queryByTestId("your-plan-note")).toBeNull();
  });
});

describe("a file that cannot be read", () => {
  it("says so where the grid would be, and the rest of the page is untouched", async () => {
    const c = caseOf("sapling-industries", "as-signed");
    const broken: LanesLoaders = { ...diskLoaders, lanes: () => Promise.reject(new Error("HTTP 404")) };
    render(
      <BindingProvider company="sapling-industries" scenario="as-signed" files={c}>
        <LanesProvider loaders={broken}>
          <LanesSection />
        </LanesProvider>
      </BindingProvider>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("HTTP 404");
    expect(screen.queryByTestId("lanes-grid")).toBeNull();
  });

  it("an owners file that is the wrong segment's is refused in the row, and the grid stays", async () => {
    const c = caseOf("sapling-industries", "as-signed");
    const wrong: LanesLoaders = { ...diskLoaders, owners: () => diskLoaders.owners("sapling-industries/lanes-owners-as-signed-commercial.json") };
    render(
      <BindingProvider company="sapling-industries" scenario="as-signed" files={c}>
        <LanesProvider loaders={wrong}>
          <LanesSection />
        </LanesProvider>
      </BindingProvider>,
    );
    await screen.findByTestId("lanes-grid");
    fireEvent.click(screen.getByTestId("expand-segment/enterprise"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/commercial owners.*not the enterprise owners/);
    expect(screen.getByTestId("lanes-grid")).toBeInTheDocument();
  });
});
