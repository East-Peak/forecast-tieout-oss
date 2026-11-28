import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { LanesGrid } from "../LanesScreen";
import type { LanesData } from "../types";

const data = JSON.parse(readFileSync(resolve(__dirname, "../../../public/prototype/lanes_ui.json"), "utf8")) as LanesData;
const FY = data.periods.FY26.rows;
const enterprise = FY.find((r) => r.id === "segment:enterprise")!;
const enterpriseOwners = FY.filter((r) => r.parent_id === enterprise.id);

afterEach(cleanup);

const rowIds = () => Array.from(document.querySelectorAll("tbody tr")).map((tr) => tr.getAttribute("data-testid"));
const headers = () => Array.from(document.querySelectorAll("thead th[data-col]")).map((th) => th.getAttribute("data-col"));
const open = () => render(<LanesGrid data={data} />);

describe("the lanes grid", () => {
  it("draws Total and the three segments with the eight columns, for both periods", () => {
    open();
    for (const label of ["Fiscal year", "Q3"]) {
      fireEvent.click(screen.getByRole("button", { name: label }));
      expect(rowIds()).toEqual(["row-total", "row-segment:enterprise", "row-segment:mid_market", "row-segment:commercial"]);
      expect(headers()).toEqual(data.columns.map((c) => c.key));
      expect(headers()).toHaveLength(8);
    }
  });

  it("hides the three processing columns with the switch and brings them back", () => {
    open();
    const toggle = screen.getByRole("switch", { name: "Processing metrics" });
    fireEvent.click(toggle);
    expect(headers()).toEqual(["opening", "created", "created_arr", "won", "bookings"]);
    expect(screen.queryByTestId("cell-total-win_rate")).toBeNull();
    fireEvent.click(toggle);
    expect(headers()).toHaveLength(8);
  });

  it("shows a segment's owners when it is expanded, and folds them away again", () => {
    open();
    expect(enterpriseOwners.length).toBeGreaterThan(3);
    fireEvent.click(screen.getByRole("button", { name: "Expand Enterprise" }));
    expect(rowIds()).toHaveLength(4 + enterpriseOwners.length);
    expect(document.querySelectorAll("tr[data-role='owner']")).toHaveLength(enterpriseOwners.length);
    fireEvent.click(screen.getByRole("button", { name: "Collapse Enterprise" }));
    expect(rowIds()).toHaveLength(4);
  });

  it("drills into a segment through its menu and rolls up again from the chip", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Bookings, Enterprise" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Drill down" }));
    expect(rowIds()).toEqual(["row-segment:enterprise", ...enterpriseOwners.map((o) => `row-${o.id}`)]);
    expect(screen.getAllByTestId("chip").map((c) => c.textContent)).toEqual(["Segment: Enterprise×", "Owner"]);
    fireEvent.click(screen.getByRole("button", { name: "Roll up Enterprise" }));
    expect(rowIds()).toHaveLength(4);
    expect(screen.getAllByTestId("chip").map((c) => c.textContent)).toEqual(["Segment"]);
  });

  it("excludes a row and restores it from the hidden link", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Won, Commercial" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Exclude" }));
    expect(rowIds()).not.toContain("row-segment:commercial");
    fireEvent.click(screen.getByTestId("hidden-link"));
    expect(rowIds()).toContain("row-segment:commercial");
    expect(screen.queryByTestId("hidden-link")).toBeNull();
  });

  it("opens a panel whose records are as many as the Created cell's actual", () => {
    open();
    fireEvent.click(screen.getByTestId("cell-segment:enterprise-created"));
    const panel = screen.getByTestId("cell-panel");
    const actual = enterprise.cells.created.actual!;
    expect(within(panel).getAllByTestId("record-row")).toHaveLength(Number(actual));
    expect(within(panel).getByTestId("records-count").textContent).toBe(`(${actual})`);
    fireEvent.change(within(panel).getByLabelText("Search records"), { target: { value: "SAP-00925" } });
    expect(within(panel).getAllByTestId("record-row")).toHaveLength(1);
  });

  it("shows the split for Won, and points other columns to the records under Created and Won", () => {
    open();
    fireEvent.click(screen.getByTestId("cell-total-won"));
    expect(within(screen.getByTestId("cell-panel")).getByTestId("split")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("cell-total-cycle"));
    expect(screen.getByTestId("records-elsewhere").textContent).toBe("Records are listed under Created and Won.");
    expect(screen.queryByTestId("split")).toBeNull();
  });

  it("shows no color on an owner's win rate, cycle or average won ARR, though the file has one", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "Expand Enterprise" }));
    const colored = enterpriseOwners.filter((o) => ["win_rate", "cycle", "avg_won_arr"].some((c) => o.cells[c].color !== "none"));
    expect(colored.length).toBeGreaterThan(0);
    for (const owner of enterpriseOwners) {
      for (const column of ["win_rate", "cycle", "avg_won_arr"]) {
        const cell = screen.getByTestId(`cell-${owner.id}-${column}`);
        expect(cell.getAttribute("data-color")).toBe("none");
        expect(within(cell).queryByTestId("pct")).toBeNull();
      }
    }
  });

  it("shows no color anywhere on an owner with no plan allocation", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "Expand Enterprise" }));
    const later = enterpriseOwners.filter((o) => !o.allocated);
    expect(later.length).toBeGreaterThan(0);
    for (const owner of later) {
      for (const column of data.columns) {
        expect(screen.getByTestId(`cell-${owner.id}-${column.key}`).getAttribute("data-color")).toBe("none");
      }
    }
  });
});
