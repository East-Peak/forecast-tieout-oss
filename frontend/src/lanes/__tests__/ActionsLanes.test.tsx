import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
import { percent1 } from "../../screens/__tests__/independent";
import { caseOf } from "../../screens/__tests__/screenChecks";
import { LANES_BINDINGS } from "../bindings";
import { LanesProvider } from "../LanesContext";
import LanesSection from "../LanesSection";
import type { LanesFile, OwnersFile } from "../types";
import { diskLoaders } from "./disk";
import { build, filesOf } from "./expectations";
import type { Files } from "./expectations";

afterEach(cleanup);

const COMPANY = "sapling-industries";
const FIXTURE = resolve(__dirname, "../../screens/__tests__/fixtures/your-plan-actions");
const fixture = <T,>(name: string): T => JSON.parse(readFileSync(resolve(FIXTURE, name), "utf8")) as T;

/** The plan with a win-rate action on Enterprise, as a native run of the core wrote it: the report and the grid. */
const REPORT = fixture<TieoutReport>("report.json");
const PLAN = fixture<PlanDoc>("plan.json");
const LANES = fixture<LanesFile>("lanes.json");
const OWNERS: Record<string, OwnersFile> = { enterprise: fixture<OwnersFile>("owners-enterprise.json"), commercial: fixture<OwnersFile>("owners-commercial.json") };
const SEGMENTS = [
  { value: "commercial", label: "Commercial" },
  { value: "enterprise", label: "Enterprise" },
  { value: "mid_market", label: "Mid Market" },
];

class FakeEditor implements Editor {
  status: EditorStatus = { phase: "idle" };
  asked: Array<(o: LanesOutcome) => void> = [];
  subscribe = () => () => {};
  open = (): Promise<Facts> => Promise.resolve({ company: COMPANY, segments: SEGMENTS, months: ["2026-09", "2026-10"], max_dollars: "1", demo_plan: PLAN });
  apply = (): Promise<ApplyOutcome> => Promise.resolve({ kind: "report", report: REPORT, comparison: { scenario: "your-plan" } as never, revision: 1 });
  lanes = () => new Promise<LanesOutcome>((resolve) => this.asked.push(resolve));
}

/** The grid for your plan, its lanes answered, in a page that has the editor (or not). `choose` is what the shell gives the grid to open the editor. */
async function ready(options: { editor?: boolean; desktop?: boolean; report?: TieoutReport; lanes?: LanesFile } = {}) {
  const editor = new FakeEditor();
  const store = new YourPlanStore(editor);
  await store.load(COMPANY);
  const choose = vi.fn();
  const shown = options.report ?? REPORT;
  // a page with no editor shows a committed scenario, whose grid is a file
  const scenario = options.editor === false ? "as-signed" : "your-plan";
  const c = { ...caseOf(COMPANY, "as-signed"), scenario, report: shown };
  const grid = (
    <BindingProvider company={COMPANY} scenario={scenario} files={c} choose={choose}>
      <LanesProvider loaders={diskLoaders}>
        <LanesSection />
      </LanesProvider>
    </BindingProvider>
  );
  const view = render(options.editor === false ? grid : <YourPlanProvider store={store} desktop={options.desktop ?? true}>{grid}</YourPlanProvider>);
  await screen.findByTestId("lanes-grid");
  if (options.editor !== false) await act(async () => editor.asked[0]({ kind: "lanes", lanes: options.lanes ?? LANES, owners: OWNERS }));
  await waitFor(() => expect(screen.queryByTestId("lanes-pending")).toBeNull());
  return { store, choose, view };
}

const cell = (row: string, column: string) => document.querySelector<HTMLButtonElement>(`[data-testid='cell-${row}-${column}']`)!;
const open = async (row: string, column: string) => {
  fireEvent.click(cell(row, column));
  return screen.findByTestId("cell-panel");
};
const forecast = (row: string) => cell(row, "win_rate").querySelector("[data-binding='lanes.win_rate.forecast']")?.textContent;
const rateOf = (path: string[]) => LANES.periods[0].rows.find((r) => r.path.join("/") === path.join("/"))!.cells.win_rate.forecast!;

describe("a plan with a win-rate action: the grid reads the core's file", () => {
  it("shows each lane's win-rate forecast as the file holds it: the action's segment moves, another does not", async () => {
    await ready();
    expect(forecast("segment/enterprise")).toBe(percent1(rateOf(["segment", "enterprise"])));
    expect(forecast("segment/mid_market")).toBe(percent1(rateOf(["segment", "mid_market"])));
    expect(forecast("segment/enterprise")).not.toBe(forecast("segment/mid_market"));
    expect(forecast("segment/mid_market")).toBe(percent1(REPORT.worksheet && "drivers" in REPORT.worksheet ? REPORT.worksheet.drivers.find((d) => d.driver === "win_rate")!.current.value! : ""));
  });

  it("is the native run's file, figure for figure and with each figure's provenance, the disclosure of the goals open, and no digit outside a bound element", async () => {
    const { view } = await ready();
    fireEvent.click(screen.getByRole("button", { name: /How the goals are made/ }));
    const f: Files = { ...filesOf(COMPANY, "as-signed"), lanes: LANES, owners: OWNERS };
    const { expected, absent } = build(f, { company: COMPANY, scenario: "your-plan", period: 0, expanded: [], basisOpen: true });
    expect(expected.some((e) => e.id === "lanes.caveat.actions")).toBe(true);
    expect(checkBindings(view.container, expected, absent, LANES_BINDINGS, { company: COMPANY, scenario: "your-plan" })).toEqual([]);
    expect(unboundDigits(view.container, [])).toEqual([]);
  });

  it("the win-rate panel adds the core's caveat for actions to what the column means, and no other column's panel does", async () => {
    await ready();
    const panel = await open("segment/enterprise", "win_rate");
    const caveat = within(panel).getByTestId("panel-actions-caveat");
    expect(caveat).toHaveTextContent(LANES.caveats[3]);
    expect(caveat.querySelector("[data-binding='lanes.panel.caveat.actions']")?.getAttribute("data-path")).toBe("/caveats/3");
    fireEvent.click(within(panel).getByRole("button", { name: "Close panel" }));
    const other = await open("segment/enterprise", "bookings");
    expect(within(other).queryByTestId("panel-actions-caveat")).toBeNull();
  });

  it("a plan without actions has no such caveat in the panel", async () => {
    const plain = structuredClone(LANES);
    plain.caveats = plain.caveats.slice(0, 3) as never;
    await ready({ lanes: plain });
    const panel = await open("segment/enterprise", "win_rate");
    expect(within(panel).queryByTestId("panel-actions-caveat")).toBeNull();
  });
});

describe("Plan an action here", () => {
  it("is offered on a win-rate cell of the company and of a segment, with the slice as context, and says the cell's number is not the target", async () => {
    await ready();
    for (const [row, slice] of [["total", "company"], ["segment/enterprise", "enterprise"]] as const) {
      const panel = await open(row, "win_rate");
      const entry = within(panel).getByTestId("plan-action");
      expect(within(entry).getByRole("button", { name: "Plan an action here" })).toBeEnabled();
      expect(entry).toHaveTextContent(/dated cohort rate/);
      expect(entry).toHaveTextContent(/pooled baseline/);
      expect(entry.getAttribute("data-slice")).toBe(slice);
      fireEvent.click(within(panel).getByRole("button", { name: "Close panel" }));
    }
  });

  it("opens a draft with the slice prefilled and the target at the pooled baseline, not the cell's own number, and applies nothing", async () => {
    const { store, choose } = await ready();
    const plan = JSON.stringify(store.snapshot.applied[COMPANY].plan);
    const panel = await open("segment/mid_market", "win_rate");
    const cellNumber = LANES.periods[0].rows.find((r) => r.path[1] === "mid_market")!.cells.win_rate.actual!;
    fireEvent.click(within(panel).getByRole("button", { name: "Plan an action here" }));
    expect(choose).toHaveBeenCalledWith(COMPANY, "your-plan");
    const added = store.snapshot.drafts[COMPANY].actions!.find((a) => a.slice === "mid_market")!;
    expect(added).toMatchObject({ slice: "mid_market", start: "2026-09", ramp_months: 0, driver: "win_rate" });
    expect(added.target).toBe("0.2193");
    expect(added.target).not.toBe(cellNumber);
    expect(store.snapshot.origins[COMPANY][added.id]).toBe("grid");
    expect(JSON.stringify(store.snapshot.applied[COMPANY].plan)).toBe(plan);
    expect(screen.queryByTestId("cell-panel"), "the panel gets out of the form's way").toBeNull();
  });

  it("on the company row the slice is the company", async () => {
    const { store } = await ready();
    const panel = await open("total", "win_rate");
    fireEvent.click(within(panel).getByRole("button", { name: "Plan an action here" }));
    expect(store.snapshot.drafts[COMPANY].actions!.some((a) => a.slice === "company")).toBe(true);
  });

  it("is not offered on another column, or on an owner row", async () => {
    await ready();
    for (const column of ["bookings", "created", "cycle", "avg_won_arr"]) {
      const panel = await open("segment/enterprise", column);
      expect(within(panel).queryByTestId("plan-action"), column).toBeNull();
      fireEvent.click(within(panel).getByRole("button", { name: "Close panel" }));
    }
    fireEvent.click(screen.getByTestId("expand-segment/enterprise"));
    const owner = await screen.findByTestId("cell-segment/enterprise/owner/AE-010-win_rate");
    fireEvent.click(owner);
    const panel = await screen.findByTestId("cell-panel");
    expect(within(panel).queryByTestId("plan-action")).toBeNull();
  });

  it("is not offered where the editor is not (a screen too small for it, or a page with none)", async () => {
    await ready({ desktop: false });
    expect(within(await open("total", "win_rate")).queryByTestId("plan-action")).toBeNull();
    cleanup();
    await ready({ editor: false });
    expect(within(await open("total", "win_rate")).queryByTestId("plan-action")).toBeNull();
  });
});
