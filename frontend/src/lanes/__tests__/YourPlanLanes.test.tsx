import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { checkBindings, unboundDigits } from "../../binding/__tests__/harness";
import type { EditorStatus } from "../../editor/client";
import type { ApplyOutcome, Facts, LanesOutcome, PlanDoc } from "../../editor/protocol";
import { YourPlanStore } from "../../editor/store";
import type { Editor } from "../../editor/store";
import { YourPlanProvider } from "../../editor/YourPlanContext";
import type { TieoutReport } from "../../generated/report";
import * as files from "../../screens/__tests__/files";
import { usdShort } from "../../screens/__tests__/independent";
import { caseOf } from "../../screens/__tests__/screenChecks";
import { LANES_BINDINGS } from "../bindings";
import { LanesProvider } from "../LanesContext";
import LanesSection from "../LanesSection";
import type { LanesFile, LanesLoaders, OwnersFile } from "../types";
import { diskLoaders, lanesOf } from "./disk";
import { build, filesOf } from "./expectations";
import type { Files } from "./expectations";

afterEach(cleanup);

const COMPANY = "sapling-industries";
const FIXTURE = resolve(__dirname, "../../screens/__tests__/fixtures/your-plan");
const fixture = <T,>(name: string): T => JSON.parse(readFileSync(resolve(FIXTURE, name), "utf8")) as T;

/** The edited plan as a native run of the core wrote it: its report, its lanes, the owners of the two segments it adds hires to. */
const REPORT = fixture<TieoutReport>("report.json");
const EDITED: LanesFile = fixture<LanesFile>("lanes.json");
const OWNERS: Record<string, OwnersFile> = { enterprise: fixture<OwnersFile>("owners-enterprise.json"), commercial: fixture<OwnersFile>("owners-commercial.json") };
const SIGNED = lanesOf(COMPANY, "as-signed");
const bookings = (lanes: LanesFile, p = 0) => lanes.periods[p].rows[0].cells.bookings;

const PLAN: PlanDoc = { hires: [], programs: [] };
const FACTS: Facts = { company: COMPANY, segments: [], months: [], max_dollars: "1", demo_plan: PLAN };

/** A stand-in for the plan editor whose lanes are answered when the test says. */
class FakeEditor implements Editor {
  status: EditorStatus = { phase: "idle" };
  revision = 0;
  reports: TieoutReport[] = [REPORT];
  applied: string[] = [];
  asked: Array<{ company: string; revision: number; resolve: (o: LanesOutcome) => void }> = [];
  subscribe = () => () => {};
  open = () => Promise.resolve(FACTS);
  apply(company: string): Promise<ApplyOutcome> {
    this.applied.push(company);
    const report = this.reports.shift() ?? REPORT;
    return Promise.resolve({ kind: "report", report, comparison: { scenario: "your-plan" } as never, revision: ++this.revision });
  }
  lanes(company: string, revision: number) {
    return new Promise<LanesOutcome>((resolve) => this.asked.push({ company, revision, resolve }));
  }
}

const READY: LanesOutcome = { kind: "lanes", lanes: EDITED, owners: OWNERS };

/** The grid for "your plan" of the company whose report `shown` is on screen, the store's lanes read as the page would. */
async function mount(options: { store?: YourPlanStore; shown?: TieoutReport; company?: string; loaders?: LanesLoaders } = {}) {
  const editor = new FakeEditor();
  const store = options.store ?? new YourPlanStore(editor);
  if (!options.store) await store.load(COMPANY);
  const company = options.company ?? COMPANY;
  const shown = options.shown ?? store.snapshot.applied[COMPANY]?.report ?? REPORT;
  const view = render(tree(store, company, shown, options.loaders));
  return { editor, store, view, again: (report: TieoutReport) => view.rerender(tree(store, company, report, options.loaders)) };
}

function tree(store: YourPlanStore, company: string, shown: TieoutReport, loaders: LanesLoaders = diskLoaders) {
  const c = { ...caseOf(company, "as-signed"), scenario: "your-plan", report: shown };
  return (
    <YourPlanProvider store={store} desktop>
      <BindingProvider company={company} scenario="your-plan" files={c}>
        <LanesProvider loaders={loaders}>
          <LanesSection />
        </LanesProvider>
      </BindingProvider>
    </YourPlanProvider>
  );
}

const forecastOf = (id: string, rowId: string, col: string) => document.querySelector(`[data-testid='cell-${rowId}-${col}'] [data-binding='lanes.${id}.forecast']`);
const answer = async (editor: FakeEditor, outcome: LanesOutcome = READY, which = editor.asked.length - 1) => {
  await act(async () => editor.asked[which].resolve(outcome));
};

describe("while the lanes of your plan are being computed", () => {
  it("shows the actuals and the goals, never the as-signed forecast, with a quiet pending mark where each forecast would be", async () => {
    await mount();
    await screen.findByTestId("lanes-grid");
    // actuals and goals are the as-signed lanes' (they do not depend on the plan)
    const cell = (col: string) => document.querySelector(`[data-testid='cell-total-${col}']`)!;
    const text = (col: string, what: string) => cell(col).querySelector(`[data-binding='lanes.${col}.${what}']`)?.textContent;
    expect(text("bookings", "actual")).toBe(usdShort(bookings(SIGNED).actual!));
    expect(text("bookings", "goal")).toBe(usdShort(bookings(SIGNED).goal!));
    // no forecast figure, bar, strip, percent or color is drawn from the as-signed lanes
    expect(forecastOf("bookings", "total", "bookings")).toBeNull();
    expect(document.querySelectorAll("[data-binding$='.forecast'], [data-binding$='.ratio'], [data-testid='bar'], [data-testid='strip']")).toHaveLength(0);
    expect(document.querySelectorAll("[data-testid='forecast-pending']").length).toBeGreaterThan(0);
    expect(cell("bookings").getAttribute("data-color")).toBe("none");
    expect(screen.getByTestId("lanes-pending").textContent).toMatch(/Updating the forecasts for your plan/);
    expect(screen.queryByTestId("your-plan-note")).toBeNull();
  });

  it("cannot open a cell's panel, which would show a forecast", async () => {
    await mount();
    await screen.findByTestId("lanes-grid");
    const button = document.querySelector<HTMLButtonElement>("[data-testid='cell-total-bookings']")!;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(screen.queryByTestId("cell-panel")).toBeNull();
  });

  it("is also the state of lanes that belong to a report other than the one on screen", async () => {
    const editor = new FakeEditor();
    const store = new YourPlanStore(editor);
    await store.load(COMPANY);
    await answer(editor);
    expect(store.snapshot.applied[COMPANY].lanes.status).toBe("ready");
    // the page has not yet caught up with the newest Apply: it still shows an older report
    const older = structuredClone(REPORT);
    await mount({ store, shown: older });
    await screen.findByTestId("lanes-grid");
    expect(screen.getByTestId("lanes-pending")).toBeTruthy();
    expect(forecastOf("bookings", "total", "bookings")).toBeNull();
  });

  it("is also the state of a company whose own plan has not been applied", async () => {
    const { store } = await mount({ company: "sprout-labs" });
    expect(store.snapshot.applied["sprout-labs"]).toBeUndefined();
    await screen.findByTestId("lanes-grid");
    expect(screen.getByTestId("lanes-pending")).toBeTruthy();
    expect(forecastOf("bookings", "total", "bookings")).toBeNull();
  });
});

async function ready(options: Parameters<typeof mount>[0] = {}) {
  const m = await mount(options);
  await screen.findByTestId("lanes-grid");
  await answer(m.editor);
  await waitFor(() => expect(screen.queryByTestId("lanes-pending")).toBeNull());
  return m;
}

describe("once the lanes of your plan arrive", () => {
  it("shows the edited plan's company forecast, a goal as signed, and no note that the lanes ignore the edits", async () => {
    await ready();
    const total = forecastOf("bookings", "total", "bookings")!;
    expect(total.textContent).toBe(usdShort(bookings(EDITED).forecast!));
    expect(total.textContent).not.toBe(usdShort(bookings(SIGNED).forecast!));
    expect(total.getAttribute("data-scenario")).toBe("your-plan");
    const goal = document.querySelector("[data-testid='cell-total-bookings'] [data-binding='lanes.bookings.goal']")!;
    expect(goal.textContent).toBe(usdShort(bookings(SIGNED).goal!));
    expect(screen.queryByTestId("your-plan-note")).toBeNull();
    expect(document.querySelectorAll("[data-testid='forecast-pending']")).toHaveLength(0);
  });

  it("is the native run's file, figure for figure and with each figure's provenance, and no digit stands outside a bound element", async () => {
    const { view } = await ready();
    const f: Files = { ...filesOf(COMPANY, "as-signed"), lanes: EDITED, owners: OWNERS };
    const { expected, absent } = build(f, { company: COMPANY, scenario: "your-plan", period: 0, expanded: [] });
    expect(checkBindings(view.container, expected, absent, LANES_BINDINGS, { company: COMPANY, scenario: "your-plan" })).toEqual([]);
    expect(unboundDigits(view.container, [])).toEqual([]);
  });

  it("opens a segment to the edited plan's owners from the worker's answer, the planned hires' bucket among them, and fetches no owners file", async () => {
    const owners = vi.fn(diskLoaders.owners);
    const { view } = await ready({ loaders: { ...diskLoaders, owners } });
    fireEvent.click(screen.getByTestId("expand-segment/enterprise"));
    await waitFor(() => expect(view.container.querySelector("[data-testid^='row-segment/enterprise/owner/']")).not.toBeNull());
    expect(owners).not.toHaveBeenCalled();
    expect(view.container.querySelector("[data-testid='row-segment/enterprise/owner/planned-hires']")).not.toBeNull();
    const f: Files = { ...filesOf(COMPANY, "as-signed"), lanes: EDITED, owners: OWNERS };
    const { expected, absent } = build(f, { company: COMPANY, scenario: "your-plan", period: 0, expanded: ["enterprise"] });
    expect(checkBindings(view.container, expected, absent, LANES_BINDINGS, { company: COMPANY, scenario: "your-plan" })).toEqual([]);
  });

  it("opens a cell's panel again, with the edited forecast", async () => {
    await ready();
    fireEvent.click(document.querySelector("[data-testid='cell-total-bookings']")!);
    await screen.findByTestId("cell-panel");
  });
});

/** Lanes of an earlier Apply, with a company forecast no other lanes show: it must never be on screen. */
const A_LANESOF = (): LanesFile => {
  const doc = structuredClone(EDITED);
  doc.periods[0].rows[0].cells.bookings.forecast = "11111111.11" as never;
  return doc;
};

describe("lanes in flight when something newer happens", () => {
  it("Apply A, Apply B, then A's lanes arrive: B's forecasts stay pending until B's own lanes, and A's figure is never on screen", async () => {
    const m = await mount();
    await screen.findByTestId("lanes-grid");
    const reportA = m.store.snapshot.applied[COMPANY].report;
    expect(m.editor.asked).toHaveLength(1); // A's lanes: asked, not answered
    const reportB = structuredClone(REPORT);
    m.editor.reports.push(reportB);
    m.store.setDraft(COMPANY, { hires: [{ segment: "enterprise", start: "2026-10", count: 1 }], programs: [] });
    await act(async () => m.store.apply(COMPANY));
    expect(m.store.snapshot.applied[COMPANY].report).toBe(reportB);
    m.again(reportB);
    expect(m.editor.asked).toHaveLength(2);
    // A's answer arrives now, after B was applied and B is on screen
    await answer(m.editor, { kind: "lanes", lanes: A_LANESOF(), owners: {} }, 0);
    expect(m.store.snapshot.applied[COMPANY].lanes.status).toBe("pending");
    expect(screen.getByTestId("lanes-pending")).toBeTruthy();
    expect(forecastOf("bookings", "total", "bookings")).toBeNull();
    expect(document.body.textContent).not.toContain(usdShort("11111111.11"));
    expect(reportA).not.toBe(reportB);
    await answer(m.editor, READY, 1);
    await waitFor(() => expect(forecastOf("bookings", "total", "bookings")?.textContent).toBe(usdShort(bookings(EDITED).forecast!)));
  });

  it("a company switch while lanes are in flight: the other company's lanes never show this one's, and its own arrive for it alone", async () => {
    const m = await mount();
    await screen.findByTestId("lanes-grid");
    const sapling = m.store.snapshot.applied[COMPANY].report;
    await m.store.load("sprout-labs");
    expect(m.editor.asked.map((c) => c.company)).toEqual([COMPANY, "sprout-labs"]);
    cleanup();
    render(tree(m.store, "sprout-labs", m.store.snapshot.applied["sprout-labs"].report));
    await screen.findByTestId("lanes-grid");
    // sapling's lanes arrive while sprout-labs is shown: sprout-labs stays pending, with no sapling figure
    await answer(m.editor, { kind: "lanes", lanes: A_LANESOF(), owners: {} }, 0);
    expect(m.store.snapshot.applied["sprout-labs"].lanes.status).toBe("pending");
    expect(screen.getByTestId("lanes-pending")).toBeTruthy();
    expect(forecastOf("bookings", "total", "bookings")).toBeNull();
    expect(m.store.snapshot.applied[COMPANY].lanes.status).toBe("ready");
    // back to sapling: its own lanes, never pending
    cleanup();
    render(tree(m.store, COMPANY, sapling));
    await screen.findByTestId("lanes-grid");
    expect(forecastOf("bookings", "total", "bookings")?.textContent).toBe(usdShort("11111111.11"));
    expect(screen.queryByTestId("lanes-pending")).toBeNull();
  });
});

describe("lanes that cannot be shown", () => {
  it("say so where the grid would be, with no as-signed grid in its place", async () => {
    const m = await mount();
    await screen.findByTestId("lanes-grid");
    await answer(m.editor, { kind: "refused", problems: ["the plan basis computed here is not the committed one"] });
    expect((await screen.findByRole("alert")).textContent).toMatch(/lanes for your plan could not be computed.*not the committed one/);
    expect(screen.queryByTestId("lanes-grid")).toBeNull();
  });

  it("an unavailable plan basis is the file's own sentence, as for any scenario", async () => {
    const m = await mount();
    await screen.findByTestId("lanes-grid");
    const unavailable = { schema_version: "1.0.0", company: COMPANY, scenario: "your-plan", unavailable: "no plan basis for this test" } as never;
    await answer(m.editor, { kind: "lanes", lanes: unavailable, owners: {} });
    expect((await screen.findByTestId("lanes-unavailable")).textContent).toBe("no plan basis for this test");
  });

  it("lanes the worker could not compute because it had moved on say so, and the grid does not fall back to the as-signed one", async () => {
    const m = await mount();
    await screen.findByTestId("lanes-grid");
    await answer(m.editor, { kind: "stale" });
    expect((await screen.findByRole("alert")).textContent).toMatch(/apply the plan again/);
    expect(screen.queryByTestId("lanes-grid")).toBeNull();
  });
});

describe("another company", () => {
  it("shows none of this company's lanes: its own plan has none until it is applied", async () => {
    const { store } = await ready();
    cleanup();
    await mount({ store, company: "sprout-labs", shown: store.snapshot.applied[COMPANY].report });
    await screen.findByTestId("lanes-grid");
    expect(screen.getByTestId("lanes-pending")).toBeTruthy();
    expect(document.querySelector("[data-testid='cell-total-bookings']")!.getAttribute("data-color")).toBe("none");
    expect(files.COMPANIES).toContain("sprout-labs");
  });
});
