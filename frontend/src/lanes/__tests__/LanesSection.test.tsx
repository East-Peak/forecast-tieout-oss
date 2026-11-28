import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { checkBindings, unboundDigits } from "../../binding/__tests__/harness";
import { caseOf } from "../../screens/__tests__/screenChecks";
import * as files from "../../screens/__tests__/files";
import { LANES_BINDINGS } from "../bindings";
import { LanesProvider } from "../LanesContext";
import LanesSection from "../LanesSection";
import type { ColumnKey, LanesLoaders } from "../types";
import { diskLoaders } from "./disk";
import { build, displayedRows, filesOf, idOf, segmentSlugs } from "./expectations";
import type { State } from "./expectations";

afterEach(cleanup);

const SECTION_LIST = LANES_BINDINGS;
const COLUMN_KEYS: ColumnKey[] = ["open", "created", "created_arr", "win_rate", "cycle", "won", "avg_won_arr", "bookings"];

async function mount(company: string, scenario: string, loaders: LanesLoaders = diskLoaders) {
  const c = caseOf(company, scenario);
  const view = render(
    <BindingProvider company={company} scenario={scenario} files={c}>
      <LanesProvider loaders={loaders}>
        <LanesSection />
      </LanesProvider>
    </BindingProvider>,
  );
  await screen.findByTestId("lanes-grid");
  return view.container;
}

/** The page against the independent expectations of a state, and no digit anywhere outside a bound element. */
function failures(container: HTMLElement, state: State): string[] {
  const f = filesOf(state.company, state.scenario);
  const { expected, absent } = build(f, state);
  return [
    ...checkBindings(container, expected, absent, SECTION_LIST, state),
    ...unboundDigits(container, []).map((t) => `digits outside a bound element: ${t}`),
  ];
}

async function expand(container: HTMLElement, slugs: readonly string[]) {
  for (const slug of slugs) {
    const button = container.querySelector<HTMLElement>(`[data-testid='expand-segment/${slug}']`)!;
    fireEvent.click(button);
  }
  for (const slug of slugs) await waitFor(() => expect(container.querySelector(`[data-testid^='row-segment/${slug}/owner/']`)).not.toBeNull());
}

async function openPanel(container: HTMLElement, row: string, column: ColumnKey, withRecords: boolean) {
  fireEvent.click(container.querySelector<HTMLElement>(`[data-testid='cell-${row}-${column}']`)!);
  await waitFor(() => expect(container.querySelector("[data-testid='cell-panel']")).not.toBeNull());
  if (withRecords) await waitFor(() => expect(container.querySelector("[data-testid='records'][data-state='ready']")).not.toBeNull());
}

const base = (company: string, scenario: string): State => ({ company, scenario, period: 0, expanded: [] });

describe("the grid, collapsed, for every company and scenario", () => {
  it.each(files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const)))("%s / %s", async (company, scenario) => {
    const container = await mount(company, scenario);
    expect(failures(container, base(company, scenario))).toEqual([]);
  });
});

describe("a segment opened to its owners, a quarter, and the panel of each column", () => {
  it.each(files.COMPANIES)("%s: every segment opened, every owner row reads the files", async (company) => {
    const container = await mount(company, "as-signed");
    const slugs = segmentSlugs(filesOf(company, "as-signed").lanes);
    await expand(container, slugs);
    expect(failures(container, { ...base(company, "as-signed"), expanded: slugs })).toEqual([]);
  }, 60_000);

  // one test for each company and column, so that no single test is long: the total's panel, then the first owner's
  it.each(files.COMPANIES.flatMap((company) => COLUMN_KEYS.map((column) => [company, column] as const)))("%s: the panel of %s, for the total and for an owner", async (company, column) => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const slug = segmentSlugs(f.lanes)[0];
    await expand(container, [slug]);
    const state: State = { ...base(company, "as-signed"), expanded: [slug] };
    const owner = displayedRows(f, state).find((r) => r.source === "owners" && r.row.kind === "owner")!;
    for (const row of ["total", idOf(owner)]) {
      await openPanel(container, row, column, true);
      expect(failures(container, { ...state, panel: { row, column, records: true } }).join("\n"), `${row} ${column}`).toBe("");
      fireEvent.keyDown(screen.getByTestId("cell-panel"), { key: "Escape" });
      await waitFor(() => expect(container.querySelector("[data-testid='cell-panel']")).toBeNull());
    }
  }, 60_000);

  it.each(files.COMPANIES)("%s: a quarter's grid, with its owners, reads that quarter", async (company) => {
    const container = await mount(company, "demo-plan");
    const f = filesOf(company, "demo-plan");
    const quarter = f.lanes.periods.findIndex((p) => p.standing === "in progress" && p.kind === "quarter");
    fireEvent.click(screen.getByTestId(`period-${f.lanes.periods[quarter].key}`));
    const slugs = segmentSlugs(f.lanes).slice(0, 1);
    await expand(container, slugs);
    expect(failures(container, { ...base(company, "demo-plan"), period: quarter, expanded: slugs })).toEqual([]);
  });

  it("the disclosure of how the goals are made says the file's caveats and the schedule beside the targets", async () => {
    const container = await mount("sapling-industries", "as-signed");
    fireEvent.click(screen.getByRole("button", { name: /how the goals are made/i }));
    await waitFor(() => expect(container.querySelector("[data-binding='basis.schedule.bookings']")).not.toBeNull());
    expect(failures(container, { ...base("sapling-industries", "as-signed"), basisOpen: true })).toEqual([]);
  });
});

describe("the committed list and the independent expectations name the same bindings", () => {
  it("every binding on the list can appear, and no expectation names one that is not on it", () => {
    const named = new Set<string>();
    for (const company of files.COMPANIES) {
      for (const scenario of files.SCENARIOS) {
        const f = filesOf(company, scenario);
        const slugs = segmentSlugs(f.lanes);
        for (let period = 0; period < f.lanes.periods.length; period++) {
          const state: State = { ...base(company, scenario), period, expanded: slugs, basisOpen: true };
          build(f, state).expected.forEach((e) => named.add(e.id));
          for (const r of displayedRows(f, state)) {
            for (const column of COLUMN_KEYS) build(f, { ...state, panel: { row: idOf(r), column, records: true } }, { panelOnly: true }).expected.forEach((e) => named.add(e.id));
          }
        }
      }
    }
    const listed = new Set(SECTION_LIST.map((b) => b.id));
    // no committed file is unavailable, and every deal's segment is a lane of the file: both are drawn from the list when they occur
    const alsoNamed = new Set(["lanes.unavailable", "record.segment"]);
    expect([...named, ...alsoNamed].sort()).toEqual([...listed].sort());
  }, 120_000);

  it("within the list, every id names one place", () => {
    const ids = SECTION_LIST.map((b) => b.id);
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([]);
  });
});

describe("the checks fail when the grid is wrong (mutations)", () => {
  const scenario = "as-signed";
  const company = "sapling-industries";

  it("a swapped path is caught", async () => {
    const binding = SECTION_LIST.find((b) => b.id === "lanes.bookings.actual") as { path: string };
    const was = binding.path;
    binding.path = "/forecast";
    try {
      const container = await mount(company, scenario);
      expect(failures(container, base(company, scenario)).some((f) => f.startsWith("lanes.bookings.actual"))).toBe(true);
    } finally {
      binding.path = was;
    }
  });

  it("another company's file is caught", async () => {
    const wrong: LanesLoaders = { ...diskLoaders, lanes: () => diskLoaders.lanes("sprout-labs/lanes-as-signed.json") };
    const c = caseOf(company, scenario);
    render(
      <BindingProvider company={company} scenario={scenario} files={c}>
        <LanesProvider loaders={wrong}>
          <LanesSection />
        </LanesProvider>
      </BindingProvider>,
    );
    // the section refuses a file that names another company, and draws no grid
    expect((await screen.findByRole("alert")).textContent).toMatch(/sprout-labs/);
    expect(screen.queryByTestId("lanes-grid")).toBeNull();
  });

  it("a flipped sign is caught", async () => {
    const flipping: LanesLoaders = {
      ...diskLoaders,
      lanes: async (path) => {
        const doc = structuredClone(await diskLoaders.lanes(path)) as { periods: Array<{ rows: Array<{ cells: { bookings: { forecast: string } } }> }> };
        doc.periods[0].rows[0].cells.bookings.forecast = `-${doc.periods[0].rows[0].cells.bookings.forecast}`;
        return doc as never;
      },
    };
    const container = await mount(company, scenario, flipping);
    expect(failures(container, base(company, scenario)).some((f) => f.startsWith("lanes.bookings.forecast"))).toBe(true);
  });

  it("tampered provenance is caught: the path, the source, the format, the scenario and the company", async () => {
    const container = await mount(company, scenario);
    expect(failures(container, base(company, scenario))).toEqual([]);
    const el = container.querySelector("[data-binding='lanes.created.actual']")!;
    for (const [attribute, value] of [["data-path", "/wrong"], ["data-source", "owners"], ["data-format", "usd-full"], ["data-scenario", "nope"], ["data-company", "other"]] as const) {
      const was = el.getAttribute(attribute)!;
      el.setAttribute(attribute, value);
      expect(failures(container, base(company, scenario)).some((f) => f.includes(attribute)), attribute).toBe(true);
      el.setAttribute(attribute, was);
    }
  });

  it("a digit outside any bound element, and a bound element not on the list, are caught", async () => {
    const container = await mount(company, scenario);
    const stray = document.createElement("p");
    stray.textContent = "Up 12% on last year";
    container.appendChild(stray);
    expect(failures(container, base(company, scenario))).toContain("digits outside a bound element: Up 12% on last year");
    stray.remove();
    const extra = document.createElement("span");
    extra.setAttribute("data-binding", "sneaky");
    container.appendChild(extra);
    expect(failures(container, base(company, scenario)).some((f) => f.startsWith("sneaky"))).toBe(true);
  });
});

describe("the grid's own behavior", () => {
  const company = "sapling-industries";

  it("draws the eight columns in the file's order, with the total first, then the segments by the file's order", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const heads = [...container.querySelectorAll("[data-testid='lanes-grid'] thead [data-col]")].map((th) => th.getAttribute("data-col"));
    expect(heads).toEqual(f.lanes.columns.map((c) => c.key));
    const rows = [...container.querySelectorAll("[data-testid='lanes-grid'] tbody tr")].map((tr) => tr.getAttribute("data-testid"));
    expect(rows).toEqual(f.lanes.periods[0].rows.map((r) => `row-${r.path.join("/")}`));
  });

  it("colors a cell from the file's status alone: behind is red, on track is green, none has no color", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const want = { behind: "red", on_track: "green", none: "none" } as const;
    for (const r of displayedRows(f, base(company, "as-signed"))) {
      for (const column of COLUMN_KEYS) {
        const cell = container.querySelector(`[data-testid='cell-${idOf(r)}-${column}']`)!;
        expect(cell.getAttribute("data-color"), `${idOf(r)} ${column}`).toBe(want[r.row.cells[column].status]);
      }
    }
  });

  it("a cell with no color says why, in the file's own words, to a hover and a keyboard", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const cell = container.querySelector("[data-testid='cell-total-open']")!;
    const tip = cell.querySelector("[role='tooltip']")!;
    expect(tip.textContent).toBe(f.lanes.reasons.vacuous);
    expect(cell.getAttribute("aria-describedby")).toBe(tip.id);
  });

  it("an owner's rate, cycle and size show the actual only", async () => {
    const container = await mount(company, "as-signed");
    await expand(container, ["enterprise"]);
    const f = filesOf(company, "as-signed");
    const owner = displayedRows(f, { ...base(company, "as-signed"), expanded: ["enterprise"] }).find((r) => r.source === "owners" && r.row.kind === "owner")!;
    for (const column of ["win_rate", "cycle", "avg_won_arr"] as const) {
      const cell = container.querySelector(`[data-testid='cell-${idOf(owner)}-${column}']`)!;
      expect(cell.querySelector(`[data-binding='owners.${column}.actual']`)).not.toBeNull();
      expect(cell.querySelector(`[data-binding='owners.${column}.forecast']`)).toBeNull();
      expect(cell.querySelector(`[data-binding='owners.${column}.goal']`)).toBeNull();
    }
  });

  it("a gap in the file reads unavailable, never zero", async () => {
    // a quarter of some company in which a lane has no wins, so no cycle and no average size
    const found = files.COMPANIES.flatMap((c) => {
      const f = filesOf(c, "as-signed");
      return f.lanes.periods.flatMap((p, period) => (p.rows.some((r) => COLUMN_KEYS.some((k) => r.cells[k].actual === null)) ? [{ c, period }] : []));
    })[0];
    expect(found).toBeDefined();
    const container = await mount(found.c, "as-signed");
    const f = filesOf(found.c, "as-signed");
    fireEvent.click(screen.getByTestId(`period-${f.lanes.periods[found.period].key}`));
    const state = { ...base(found.c, "as-signed"), period: found.period };
    const nulls = displayedRows(f, state).flatMap((r) => COLUMN_KEYS.filter((c) => r.row.cells[c].actual === null).map((c) => `cell-${idOf(r)}-${c}`));
    expect(nulls.length).toBeGreaterThan(0);
    for (const id of nulls) expect(container.querySelector(`[data-testid='${id}'] [data-binding$='.actual']`)!.textContent).toBe("unavailable");
  });

  it("marks the goal inside the 80% range on the total's bookings, and nowhere else", async () => {
    const container = await mount(company, "as-signed");
    const marks = [...container.querySelectorAll("[data-testid='range-marker']")].map((m) => m.parentElement!.getAttribute("data-testid"));
    expect(marks).toEqual(["cell-total-bookings"]);
  });

  it("a bar is solid to the actual and lighter to the forecast, on a track that ends at the goal: the file's own figures, laid out by the browser", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const cell = f.lanes.periods[0].rows[0].cells.created;
    const bars = [...container.querySelectorAll("[data-testid='cell-total-created'] progress")] as HTMLProgressElement[];
    expect(bars.map((b) => b.getAttribute("value"))).toEqual([cell.forecast, cell.actual]);
    expect(bars.map((b) => b.getAttribute("max"))).toEqual([cell.goal, cell.goal]);
  });

  it("rate, cycle and size compare three points on one strip, in the order of their values, goal marked", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    for (const column of ["win_rate", "cycle", "avg_won_arr"] as const) {
      const cell = f.lanes.periods[0].rows[0].cells[column];
      const strip = container.querySelector(`[data-testid='cell-total-${column}'] [data-testid='strip']`)!;
      const x = (name: string) => Number(strip.querySelector(`[data-mark='${name}']`)!.getAttribute("data-at"));
      const want = { actual: Number(cell.actual), forecast: Number(cell.forecast), goal: Number(cell.goal) };
      const order = (o: Record<string, number>) => Object.keys(o).sort((a, b) => o[a] - o[b]).join(",");
      expect(order({ actual: x("actual"), forecast: x("forecast"), goal: x("goal") }), column).toBe(order(want));
    }
  });

  it("opening a cell shows a panel beside the grid, not over it, and Escape closes it with the focus back on the cell", async () => {
    const container = await mount(company, "as-signed");
    const cell = container.querySelector<HTMLElement>("[data-testid='cell-segment/enterprise-bookings']")!;
    cell.focus();
    fireEvent.click(cell);
    const panel = await screen.findByTestId("cell-panel");
    expect(panel.closest("[data-testid='lanes-body']")).not.toBeNull();
    expect(panel.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(panel, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("cell-panel")).toBeNull());
    expect(document.activeElement).toBe(cell);
  });

  it("the records behind a cell are listed from the records file, and the count is the file's list", async () => {
    const container = await mount(company, "as-signed");
    await openPanel(container, "total", "created", true);
    const f = filesOf(company, "as-signed");
    const ids = f.records.rows[0].periods.FY26!.created;
    expect(within(screen.getByTestId("records")).getAllByTestId("record-row")).toHaveLength(ids.length);
    expect(container.querySelector("[data-testid='records-count']")!.textContent).toContain(String(ids.length));
  });

  it("modeled future contributions are labeled contribution rows, not deals", async () => {
    const container = await mount(company, "as-signed");
    await openPanel(container, "total", "bookings", true);
    const split = screen.getByTestId("contributions");
    expect(split.textContent).toMatch(/modeled/i);
    expect(within(screen.getByTestId("records")).queryByText(/modeled/i)).toBeNull();
  });

  it("the period switch shows the fiscal year and each quarter, and the grid follows it", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const keys = [...container.querySelectorAll("[data-testid^='period-']")].map((b) => b.getAttribute("data-testid"));
    expect(keys).toEqual(f.lanes.periods.map((p) => `period-${p.key}`));
    fireEvent.click(screen.getByTestId("period-Q2FY26"));
    expect(container.querySelector("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.actual']")!.getAttribute("data-path")).toBe("/periods/2/rows/0/cells/bookings/actual");
  });

  it("says plainly that upstream goals are derived benchmarks, in the file's words", async () => {
    const container = await mount(company, "as-signed");
    const f = filesOf(company, "as-signed");
    const line = container.querySelector("[data-testid='benchmark-note']")!.textContent!;
    expect(f.lanes.caveats[0].startsWith(line)).toBe(true);
    expect(line).toMatch(/derived benchmarks, not a reconciled operating plan/);
  });

  it("says that quota and segment are today's values once owners are in view, and that an owner goal is an allocated goal", async () => {
    const container = await mount(company, "as-signed");
    expect(container.querySelector("[data-testid='owner-note']")).toBeNull();
    await expand(container, ["enterprise"]);
    const f = filesOf(company, "as-signed");
    const text = container.querySelector("[data-testid='owner-note']")!.textContent!;
    expect(text).toMatch(/allocated goal/);
    expect(text).toMatch(/today's values/);
    expect(f.owners.enterprise.caveats[0]).toMatch(/allocated goal/);
    expect(f.owners.enterprise.caveats[0]).toMatch(/today's values/);
  });
});
