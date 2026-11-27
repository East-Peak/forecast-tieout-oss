import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BindingProvider } from "../../binding/Bound";
import { checkBindings, checkChart, unboundDigits } from "../../binding/__tests__/harness";
import type { CapturedChart, Expectation } from "../../binding/__tests__/harness";
import type { TieoutReport } from "../../generated/report";
import { WORKSHEET_BINDINGS } from "../plan/worksheetBindings";
import { LISTED_BINDINGS } from "../plan/bindings";
import PlanScreen from "../plan/PlanScreen";
import * as files from "./files";
import { REST_WINDOW, TWELVE_WINDOW, tornado } from "./worksheetExpectations";

const captured = vi.hoisted(() => [] as unknown[]);
vi.mock("recharts", async (importOriginal) => {
  const { withCapture } = await import("./rechartsCapture");
  return withCapture(await importOriginal<typeof import("recharts")>(), captured);
});

beforeEach(() => {
  captured.length = 0;
});
afterEach(cleanup);

type Window = typeof REST_WINDOW | typeof TWELVE_WINDOW;
const sheetOf = (r: TieoutReport) => {
  if ("unavailable" in r.worksheet) throw new Error("no worksheet");
  return r.worksheet;
};

/** What each small chart must have been given for a window, from typed accessors (not from the screen's declared paths). */
function expectedCharts(r: TieoutReport, window: Window): Array<{ name: string; data: unknown; keys: string[] }> {
  const ws = sheetOf(r);
  const num = (s: string | null) => (s === null ? null : Number(s));
  return [
    ...ws.drivers.flatMap((d, i) =>
      d.historical === null
        ? []
        : [{ name: `driver ${d.driver}`, keys: ["low", "high"], data: [{ period: String(i), low: num(d.historical.low.change[window]), high: num(d.historical.high.change[window]) }] }],
    ),
    ...ws.actions.rows.flatMap((a, i) =>
      a.bookings_gained.value === null ? [] : [{ name: `action ${a.kind}`, keys: ["gain"], data: [{ period: String(i), gain: num(a.bookings_gained.value[window]) }] }],
    ),
  ];
}

/** The charts drawn with bars, once each (the last drawing of each), in page order. */
function drawn(): CapturedChart[] {
  const all = (captured as CapturedChart[]).filter((c) => c.series.some((s) => ["low", "high", "gain"].includes(s.dataKey)));
  const last = new Map<string, CapturedChart>();
  for (const c of all) last.set(`${c.series.map((s) => s.dataKey).join()}|${(c.data as Array<{ period: string }>)[0]?.period}`, c);
  return [...last.values()];
}

function mount(company: string, scenario: string, report = files.report(company, scenario)) {
  captured.length = 0;
  return render(
    <BindingProvider company={company} scenario={scenario} files={{ report, index: files.index(), comparison: files.comparison(company) }}>
      <PlanScreen />
    </BindingProvider>,
  );
}

function failuresOf(got: CapturedChart[], r: TieoutReport, window: Window): string[] {
  const want = expectedCharts(r, window);
  if (got.length !== want.length) return [`${got.length} charts drawn, expected ${want.length}`];
  return want.flatMap((w, i) =>
    checkChart(w.name, got[i], { data: w.data, xKey: "period", series: w.keys.map((dataKey) => ({ type: "Bar", dataKey })), referenceX: ["0"] }),
  );
}

const CASES = files.COMPANIES.flatMap((company) => files.SCENARIOS.map((scenario) => [company, scenario] as const));

describe("the tornado's charts: the data and series each is given, in both windows", () => {
  it.each(CASES)("%s / %s, this fiscal year", (company, scenario) => {
    mount(company, scenario);
    expect(failuresOf(drawn(), files.report(company, scenario), REST_WINDOW)).toEqual([]);
  });

  it.each(CASES)("%s / %s, the next twelve months", (company, scenario) => {
    const { container } = mount(company, scenario);
    captured.length = 0;
    fireEvent.click(container.querySelector("[data-window-choice='next twelve months']")!);
    expect(failuresOf(drawn(), files.report(company, scenario), TWELVE_WINDOW)).toEqual([]);
  });

  it("a driver whose history failed its gate has no bars, and says why where the bars would be", () => {
    const report = structuredClone(files.report("sapling-industries", "as-signed"));
    const ws = sheetOf(report);
    ws.drivers[1].historical = null;
    ws.drivers[1].historical_unavailable_because = "only four quarters of this driver are complete";
    const { container } = mount("sapling-industries", "as-signed", report);
    expect(failuresOf(drawn(), report, REST_WINDOW)).toEqual([]);
    expect(drawn().filter((c) => c.series.length === 2)).toHaveLength(3);
    expect(container.querySelector("[data-testid='history-unavailable']")!.textContent).toBe("only four quarters of this driver are complete");
    expect(unboundDigits(container, [])).toEqual([]);
  });

  it("an action the history does not support has no bar, and says so in words", () => {
    const { container } = mount("mighty-oak-holdings", "as-signed");
    const row = container.querySelector("[data-testid='worksheet-action-row'][data-kind='hire']")!;
    expect(row.textContent).toContain("unsupported by this history");
    expect(row.querySelector("[data-testid='bar-cell']")).toBeNull();
    expect(drawn().filter((c) => c.series[0].dataKey === "gain")).toHaveLength(1);
  });
});

describe("the tornado's window switch selects; it does not calculate", () => {
  it("opens on this fiscal year, and each window's figures are the report's own for that window", () => {
    const c = { report: files.report("sapling-industries", "demo-plan"), index: files.index(), comparison: files.comparison("sapling-industries") };
    const { container } = mount("sapling-industries", "demo-plan", c.report);
    expect(container.querySelector("[data-testid='tornado']")!.getAttribute("data-window")).toBe(REST_WINDOW);
    expect(container.querySelector("[data-window-choice='rest of fiscal year']")!.getAttribute("aria-pressed")).toBe("true");
    const checkWindow = (window: Window) => {
      const expected: Expectation[] = [];
      const put = { one: () => undefined, many: (id: string, texts: string[], rows?: string[]) => void (texts.length > 0 && expected.push({ id, texts, rows })), when: () => undefined, expected, absent: [] };
      tornado(sheetOf(c.report), put, window);
      const wanted = expected.filter((e) => /change|gain/.test(e.id));
      expect(wanted.length).toBeGreaterThan(2);
      return checkBindings(container, wanted, [], [...LISTED_BINDINGS, ...WORKSHEET_BINDINGS], { company: "sapling-industries", scenario: "demo-plan" });
    };
    expect(checkWindow(REST_WINDOW)).toEqual([]);
    fireEvent.click(container.querySelector("[data-window-choice='next twelve months']")!);
    expect(container.querySelector("[data-testid='tornado']")!.getAttribute("data-window")).toBe(TWELVE_WINDOW);
    expect(checkWindow(TWELVE_WINDOW)).toEqual([]);
    // the figures of the window not shown are not on the page
    expect(container.querySelector("[data-binding='driver.low.change.rest']")).toBeNull();
    fireEvent.click(container.querySelector("[data-window-choice='rest of fiscal year']")!);
    expect(checkWindow(REST_WINDOW)).toEqual([]);
    expect(container.querySelector("[data-binding='driver.low.change.next12']")).toBeNull();
  });
});

describe("the tornado's chart checks fail when a chart is wrong (mutations)", () => {
  const base = () => files.report("sapling-industries", "as-signed");
  const draw = (report = base()) => {
    mount("sapling-industries", "as-signed", report);
    return drawn();
  };

  it("pass when nothing is changed", () => {
    expect(failuresOf(draw(), base(), REST_WINDOW)).toEqual([]);
  });

  it("a series drawn from another key is caught", () => {
    const got = draw();
    got[0].series.find((s) => s.dataKey === "high")!.dataKey = "low";
    expect(failuresOf(got, base(), REST_WINDOW).some((f) => f.includes("series"))).toBe(true);
  });

  it("the low and high bars swapped are caught", () => {
    const got = draw();
    const row = (got[0].data as Array<Record<string, number>>)[0];
    [row.low, row.high] = [row.high, row.low];
    expect(failuresOf(got, base(), REST_WINDOW).some((f) => f.includes("data given"))).toBe(true);
  });

  it("the other window's bars where this one's belong are caught", () => {
    expect(failuresOf(draw(), base(), TWELVE_WINDOW).some((f) => f.includes("data given"))).toBe(true);
  });

  it("a flipped sign in the file is caught", () => {
    const report = structuredClone(base());
    const high = sheetOf(report).drivers[0].historical!.high;
    high.change["rest of fiscal year"] = `-${high.change["rest of fiscal year"]}` as never;
    expect(failuresOf(draw(report), base(), REST_WINDOW).length).toBeGreaterThan(0);
  });

  it("another company's file is caught", () => {
    expect(failuresOf(draw(files.report("sprout-labs", "as-signed")), base(), REST_WINDOW).length).toBeGreaterThan(0);
  });

  it("another scenario's file is caught (its bars are measured around another plan)", () => {
    expect(failuresOf(draw(files.report("sapling-industries", "demo-plan")), base(), REST_WINDOW).length).toBeGreaterThan(0);
  });

  it("data transformed on its way into the chart is caught", () => {
    const got = draw();
    const row = (got[1].data as Array<Record<string, number>>)[0];
    row.high = row.high * 1.1; // test-side corruption
    expect(failuresOf(got, base(), REST_WINDOW).some((f) => f.includes("data given"))).toBe(true);
  });
});
