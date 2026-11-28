import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BindingProvider } from "../../../binding/Bound";
import { checkBindings, unboundDigits } from "../../../binding/__tests__/harness";
import type { ApplyOutcome, Facts, PlanDoc } from "../../../editor/protocol";
import type { TieoutReport } from "../../../generated/report";
import { withYourPlan } from "../../../editor/yourPlan";
import * as files from "../../__tests__/files";
import * as fmt from "../../__tests__/independent";
import { DRIVER_ACTION_BINDINGS } from "../driverActionBindings";
import { YourPlanProvider } from "../../../editor/YourPlanContext";
import { YourPlanStore } from "../../../editor/store";
import type { Editor } from "../../../editor/store";
import { YourPlanForm } from "../YourPlanForm";

const DEMO: PlanDoc = {
  hires: [{ segment: "mid_market", start: "2026-10", count: 2 }],
  programs: [{ name: "Partner referrals", pipeline: 6000000, start: "2026-10", ramp_months: 3 }],
};
const MONTHS = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07", "2027-08"];
const FACTS: Facts = {
  company: "acme",
  segments: [
    { value: "commercial", label: "Commercial" },
    { value: "mid_market", label: "Mid Market" },
  ],
  months: MONTHS,
  max_dollars: "80000000",
  demo_plan: DEMO,
};

class FakeEditor implements Editor {
  status = { phase: "idle" as const };
  sent: PlanDoc[] = [];
  next: ApplyOutcome | Error | null = null;
  gate: Promise<void> | null = null;
  subscribe = () => () => {};
  open = () => Promise.resolve(FACTS);
  lanes = () => new Promise<never>(() => {}); // the lanes are not what this form is about: never answered
  async apply(_company: string, plan: PlanDoc): Promise<ApplyOutcome> {
    this.sent.push(plan);
    if (this.gate) await this.gate;
    const next = this.next ?? { kind: "report" as const, report: { tag: "r" } as never, comparison: { scenario: "your-plan" } as never, revision: 1 };
    if (next instanceof Error) throw next;
    return next;
  }
}

// The core's own output for a plan with a win-rate action (engine/scripts/generate_editor_fixture.py): the report the form's figures are read from.
const FIXTURE = resolve(__dirname, "../../__tests__/fixtures/your-plan-actions");
const ACTIONS_REPORT = JSON.parse(readFileSync(resolve(FIXTURE, "report.json"), "utf8")) as TieoutReport;
const ACTIONS_PLAN = JSON.parse(readFileSync(resolve(FIXTURE, "plan.json"), "utf8")) as PlanDoc;
// ... and for one with an action on each driver, the win rate and the size sharing Enterprise
const DRIVERS_FIXTURE = resolve(__dirname, "../../__tests__/fixtures/your-plan-three-drivers");
const DRIVERS_REPORT = JSON.parse(readFileSync(resolve(DRIVERS_FIXTURE, "report.json"), "utf8")) as TieoutReport;
const DRIVERS_PLAN = JSON.parse(readFileSync(resolve(DRIVERS_FIXTURE, "plan.json"), "utf8")) as PlanDoc;
const SEGMENTS = [
  { value: "commercial", label: "Commercial" },
  { value: "enterprise", label: "Enterprise" },
  { value: "mid_market", label: "Mid Market" },
];

/** The form on a company whose demo plan is `demo` (applied first, so the report shown is the fixture's), in a page that reads the fixture's report. */
async function mounted(demo: PlanDoc = DEMO, segments = FACTS.segments, report: TieoutReport = ACTIONS_REPORT) {
  const editor = new FakeEditor();
  editor.open = () => Promise.resolve({ ...FACTS, segments, demo_plan: demo });
  const store = new YourPlanStore(editor);
  await store.load("acme");
  editor.sent.length = 0;
  const context = { company: "acme", scenario: "your-plan", files: { report, index: withYourPlan(files.index()), comparison: files.comparison("sapling-industries") } };
  const page = () => (
    <BindingProvider {...context}>
      <YourPlanProvider store={store} desktop>
        <YourPlanForm company="acme" />
      </YourPlanProvider>
    </BindingProvider>
  );
  const view = render(page());
  return { editor, store, view, context };
}

afterEach(cleanup);

const hireRows = () => screen.getAllByTestId("hire-row");
const programRows = () => screen.getAllByTestId("program-row");

describe("the form starts from the demo plan's items", () => {
  it("shows each hire and program with its fields filled in, and the choices the core named", async () => {
    await mounted();
    const hire = within(hireRows()[0]);
    expect(hire.getByLabelText("Segment")).toHaveValue("mid_market");
    expect(hire.getByLabelText("How many")).toHaveValue(2);
    expect(hire.getByLabelText("Starts")).toHaveValue("2026-10");
    const segments = Array.from((hire.getByLabelText("Segment") as HTMLSelectElement).options).map((o) => o.text);
    expect(segments).toEqual(["Commercial", "Mid Market"]);
    const program = within(programRows()[0]);
    expect(program.getByLabelText("Program name")).toHaveValue("Partner referrals");
    expect(program.getByLabelText("Created pipeline")).toHaveValue(6000000);
    expect(program.getByLabelText("Ramp in months (optional)")).toHaveValue(3);
    expect(program.getByLabelText("Cost (optional)")).toHaveValue(null);
  });

  it("names its months in words, so no digit stands outside a bound figure", async () => {
    await mounted();
    const months = Array.from((within(hireRows()[0]).getByLabelText("Starts") as HTMLSelectElement).options).map((o) => o.text);
    expect(months).toEqual([
      "September",
      "October",
      "November",
      "December",
      "January, next year",
      "February, next year",
      "March, next year",
      "April, next year",
      "May, next year",
      "June, next year",
      "July, next year",
      "August, next year",
    ]);
    expect(document.body.textContent).not.toMatch(/\d/);
  });

  it("bounds what a field accepts: 0 to 20 hires, dollars from 0 to ten times the year's target, a month of the twelve", async () => {
    await mounted();
    const count = within(hireRows()[0]).getByLabelText("How many");
    expect(count).toHaveAttribute("min", "0");
    expect(count).toHaveAttribute("max", "20");
    for (const label of ["Created pipeline", "Cost (optional)"]) {
      const field = within(programRows()[0]).getByLabelText(label);
      expect(field).toHaveAttribute("min", "0");
      expect(field).toHaveAttribute("max", "80000000");
    }
  });
});

describe("editing", () => {
  it("changes the draft only, and computes nothing until Apply", async () => {
    const { editor, store } = await mounted();
    fireEvent.change(within(hireRows()[0]).getByLabelText("How many"), { target: { value: "5" } });
    fireEvent.change(within(hireRows()[0]).getByLabelText("Segment"), { target: { value: "commercial" } });
    fireEvent.change(within(programRows()[0]).getByLabelText("Created pipeline"), { target: { value: "1500000" } });
    fireEvent.change(within(programRows()[0]).getByLabelText("Cost (optional)"), { target: { value: "250000" } });
    expect(editor.sent).toEqual([]);
    expect(store.snapshot.drafts.acme.hires[0]).toEqual({ segment: "commercial", start: "2026-10", count: 5 });
    expect(store.snapshot.drafts.acme.programs[0]).toMatchObject({ pipeline: 1500000, cost: 250000, ramp_months: 3 });
  });

  it("leaves an emptied optional field out of the plan", async () => {
    const { store } = await mounted();
    fireEvent.change(within(programRows()[0]).getByLabelText("Ramp in months (optional)"), { target: { value: "" } });
    expect("ramp_months" in store.snapshot.drafts.acme.programs[0]).toBe(false);
  });

  it("adds and removes items, up to eight in all", async () => {
    const { store } = await mounted();
    fireEvent.click(screen.getByRole("button", { name: "Remove hire" }));
    expect(store.snapshot.drafts.acme.hires).toEqual([]);
    for (let n = 0; n < 8; n++) if (!screen.getByRole("button", { name: "Add a hire" }).hasAttribute("disabled")) fireEvent.click(screen.getByRole("button", { name: "Add a hire" }));
    expect(store.snapshot.drafts.acme.hires).toHaveLength(7);
    expect(screen.getByRole("button", { name: "Add a program" })).toBeDisabled();
    fireEvent.click(screen.getAllByRole("button", { name: "Remove program" })[0]);
    expect(screen.getByRole("button", { name: "Add a program" })).toBeEnabled();
  });
});

describe("Apply", () => {
  it("sends the form as it stands, once, and says it is computing meanwhile", async () => {
    const { editor } = await mounted();
    let release!: () => void;
    editor.gate = new Promise((r) => (release = r));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Computing in your browser…" })).toBeDisabled());
    expect(editor.sent).toEqual([DEMO]);
    release();
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled());
  });

  it("shows the core's words beside the item it refused", async () => {
    const { editor } = await mounted();
    editor.next = { kind: "invalid", errors: [{ section: "programs", index: 1, position: 0, message: "programs[1]: pipeline must be more than 0" }] };
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    const beside = await within(programRows()[0]).findByRole("alert");
    expect(beside).toHaveTextContent("pipeline must be more than 0");
    expect(within(hireRows()[0]).queryByRole("alert")).toBeNull();
  });

  it("shows a message that names no item above the form", async () => {
    const { editor } = await mounted();
    editor.next = { kind: "invalid", errors: [{ section: null, index: null, position: null, message: "your plan: hires and programs must each be a list of items" }] };
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByTestId("plan-form-errors")).toHaveTextContent("must each be a list");
  });

  it("shows a report that failed its checks as a failure, and says it was not shown", async () => {
    const { editor } = await mounted();
    editor.next = { kind: "refused", problems: ["/plan/items: wrong"] };
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    const alert = await screen.findByTestId("plan-refused");
    expect(alert).toHaveTextContent("not shown");
    expect(alert).toHaveTextContent("/plan/items: wrong");
  });

  it("shows a timeout with a way to try again, and trying again sends the plan again", async () => {
    const { editor } = await mounted();
    const { EditorFailure } = await import("../../../editor/client");
    editor.next = new EditorFailure("timeout", "no answer within the time allowed");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    const failure = await screen.findByTestId("plan-failure");
    expect(failure).toHaveTextContent("no answer within the time allowed");
    editor.next = null;
    fireEvent.click(within(failure).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByTestId("plan-failure")).toBeNull());
    expect(editor.sent).toHaveLength(2);
  });

  it("says when the form holds changes that were not applied", async () => {
    await mounted();
    expect(screen.queryByTestId("plan-unapplied")).toBeNull();
    fireEvent.change(within(hireRows()[0]).getByLabelText("How many"), { target: { value: "4" } });
    expect(screen.getByTestId("plan-unapplied")).toBeInTheDocument();
  });
});


const actionRows = () => screen.getAllByTestId("action-row");

describe("actions: the list and the form, beside hires and programs", () => {
  it("shows none for a plan that holds none, and says in the core's words what an action changes", async () => {
    await mounted();
    expect(screen.queryAllByTestId("action-row")).toEqual([]);
    expect(screen.getByRole("button", { name: "Add an action" })).toBeEnabled();
    // what an action is, in the core's sentence: read from the section the report carries even when it holds no action
    const line = screen.getByTestId("actions-line");
    expect(line).toHaveTextContent("An action changes the win rate of pipeline created from its start month on.");
    expect(line).toHaveTextContent("Deals already open keep their odds.");
    expect(line).toHaveTextContent("A segment's target is an entered change on the pooled baseline, not a measured segment rate.");
    expect(line.querySelector("[data-binding='driver-actions.form.line']")?.getAttribute("data-path")).toBe("/driver_actions/line");
  });

  it("shows an action with its name, slice, start, ramp and target, the target as the percent a person types", async () => {
    await mounted(ACTIONS_PLAN, SEGMENTS);
    const row = within(actionRows()[0]);
    expect(row.getByLabelText("Action name")).toHaveValue("Enterprise win-rate push");
    expect(row.getByLabelText("Slice")).toHaveValue("enterprise");
    expect(Array.from((row.getByLabelText("Slice") as HTMLSelectElement).options).map((o) => o.text)).toEqual(["Company", "Commercial", "Enterprise", "Mid Market"]);
    expect(row.getByLabelText("Starts")).toHaveValue("2026-10");
    expect(row.getByLabelText("Ramp in months (zero is immediate)")).toHaveValue(2);
    expect(row.getByLabelText("Target win rate (percent)")).toHaveValue("26");
  });

  it("bounds the ramp from zero to the core's sixty months, and takes the start from the months a plan may start in", async () => {
    await mounted(ACTIONS_PLAN, SEGMENTS);
    const ramp = within(actionRows()[0]).getByLabelText("Ramp in months (zero is immediate)");
    expect(ramp).toHaveAttribute("min", "0");
    expect(ramp).toHaveAttribute("max", "60");
    const starts = Array.from((within(actionRows()[0]).getByLabelText("Starts") as HTMLSelectElement).options).map((o) => o.value);
    expect(starts).toEqual(MONTHS);
  });

  it("adds an action on the company at the pooled baseline, in the first month, with no ramp; nothing is computed until Apply", async () => {
    const { store, editor } = await mounted(DEMO, SEGMENTS);
    fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    expect(store.snapshot.drafts.acme.actions).toEqual([{ id: "action-0", name: "Company win-rate action", driver: "win_rate", slice: "company", start: "2026-09", ramp_months: 0, target: "0.2193" }]);
    expect(within(actionRows()[0]).getByLabelText("Target win rate (percent)")).toHaveValue("21.93");
    expect(editor.sent).toEqual([]);
  });

  it("changes the draft only: a percent typed is sent as the probability, with the point moved and nothing calculated", async () => {
    const { store, editor } = await mounted(ACTIONS_PLAN, SEGMENTS);
    const row = within(actionRows()[0]);
    fireEvent.change(row.getByLabelText("Target win rate (percent)"), { target: { value: "23.5" } });
    fireEvent.change(row.getByLabelText("Ramp in months (zero is immediate)"), { target: { value: "4" } });
    fireEvent.change(row.getByLabelText("Slice"), { target: { value: "commercial" } });
    fireEvent.change(row.getByLabelText("Starts"), { target: { value: "2026-12" } });
    fireEvent.change(row.getByLabelText("Action name"), { target: { value: "Commercial push" } });
    expect(store.snapshot.drafts.acme.actions?.[0]).toEqual({ id: "enterprise-win-rate", name: "Commercial push", driver: "win_rate", slice: "commercial", start: "2026-12", ramp_months: 4, target: "0.235" });
    expect(editor.sent).toEqual([]);
  });

  it("keeps a percent half-typed as typed (a trailing point stays), and the plan holds its probability", async () => {
    const { store } = await mounted(ACTIONS_PLAN, SEGMENTS);
    const field = within(actionRows()[0]).getByLabelText("Target win rate (percent)");
    fireEvent.change(field, { target: { value: "23." } });
    expect(field).toHaveValue("23.");
    expect(store.snapshot.drafts.acme.actions?.[0].target).toBe("0.23");
  });

  it("removes an action, and stops offering another once every segment has one on each driver", async () => {
    const { store } = await mounted(ACTIONS_PLAN, SEGMENTS);
    for (let n = 2; n <= 9; n++) {
      fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
      expect(store.snapshot.drafts.acme.actions).toHaveLength(n);
    }
    expect(screen.getByRole("button", { name: "Add an action" })).toBeDisabled();
    fireEvent.click(screen.getAllByRole("button", { name: "Remove action" })[0]);
    expect(store.snapshot.drafts.acme.actions).toHaveLength(8);
    expect(screen.getByRole("button", { name: "Add an action" })).toBeEnabled();
  });

  it("a plan whose last action is removed is the plan it was before: no empty list, so nothing reads as changed", async () => {
    const { store } = await mounted(ACTIONS_PLAN, SEGMENTS);
    fireEvent.click(screen.getByRole("button", { name: "Remove action" }));
    expect("actions" in store.snapshot.drafts.acme).toBe(false);
    expect(store.snapshot.drafts.acme).toEqual({ hires: ACTIONS_PLAN.hires, programs: ACTIONS_PLAN.programs });
    cleanup();
    const plain = await mounted(DEMO, SEGMENTS);
    fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove action" }));
    expect(screen.queryByTestId("plan-unapplied")).toBeNull();
    expect(plain.store.snapshot.drafts.acme).toEqual(DEMO);
  });

  it("is sent with Apply, in the plan's own shape", async () => {
    const { editor } = await mounted(ACTIONS_PLAN, SEGMENTS);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(editor.sent).toHaveLength(1));
    expect(editor.sent[0]).toEqual(ACTIONS_PLAN);
  });
});

describe("actions: the evidence beside the target", () => {
  const CORE = ACTIONS_REPORT.driver_actions as Extract<TieoutReport["driver_actions"], { joint_gain: unknown }>;
  const elements = (id: string) => Array.from(document.querySelectorAll<HTMLElement>(`[data-binding='${id}']`));

  it("shows the pooled baseline and the worksheet's low and high settings, as the report gives them, with their provenance", async () => {
    const { context } = await mounted(ACTIONS_PLAN, SEGMENTS);
    const driver = (ACTIONS_REPORT.worksheet as { drivers: Array<{ driver: string; current: { value: string }; historical: { low: { setting: string }; high: { setting: string } } }> }).drivers.find((d) => d.driver === "win_rate")!;
    const failures = checkBindings(
      document.body,
      [
        { id: "driver-actions.form.baseline", texts: [fmt.percent1(driver.current.value)] },
        { id: "driver-actions.form.low", texts: [fmt.percent1(driver.historical.low.setting)] },
        { id: "driver-actions.form.high", texts: [fmt.percent1(driver.historical.high.setting)] },
      ],
      [],
      DRIVER_ACTION_BINDINGS,
      context,
      ["driver-actions.item.", "driver-actions.form.line"],
    );
    expect(failures).toEqual([]);
  });

  it("shows, for an action as applied, the core's change in points and resulting rate, and its label when the target is outside the settings", async () => {
    const { context } = await mounted(ACTIONS_PLAN, SEGMENTS);
    const evidence = CORE.items[0].evidence as Extract<(typeof CORE.items)[0]["evidence"], { change_points: string }>;
    const row = "/driver_actions/items/0";
    expect(
      checkBindings(
        document.body,
        [
          { id: "driver-actions.item.change-points", texts: [fmt.decimal2(evidence.change_points)], rows: [row] },
          { id: "driver-actions.item.resulting", texts: [fmt.percent1(evidence.resulting_rate)], rows: [row] },
          { id: "driver-actions.item.label", texts: [evidence.label], rows: [row] },
        ],
        [],
        DRIVER_ACTION_BINDINGS,
        context,
        ["driver-actions.form."],
      ),
    ).toEqual([]);
    expect(evidence.label).toBe("outside the worksheet's historical settings");
    expect(document.body.textContent).not.toMatch(/beyond what/i);
    expect(unboundDigits(document.body)).toEqual([]);
  });

  it("shows no label for a target inside the settings, and none for a plan whose report has no figure for the action yet", async () => {
    await mounted(ACTIONS_PLAN, SEGMENTS);
    expect(elements("driver-actions.item.label")).toHaveLength(1);
    cleanup();
    const inside = structuredClone(ACTIONS_REPORT);
    const section = inside.driver_actions as typeof CORE;
    section.items[0].evidence.position = "inside" as never;
    section.items[0].evidence.label = "within the worksheet's historical settings" as never;
    const editor = new FakeEditor();
    editor.open = () => Promise.resolve({ ...FACTS, segments: SEGMENTS, demo_plan: ACTIONS_PLAN });
    const store = new YourPlanStore(editor);
    await store.load("acme");
    render(
      <BindingProvider company="acme" scenario="your-plan" files={{ report: inside, index: withYourPlan(files.index()), comparison: files.comparison("sapling-industries") }}>
        <YourPlanProvider store={store} desktop>
          <YourPlanForm company="acme" />
        </YourPlanProvider>
      </BindingProvider>,
    );
    expect(elements("driver-actions.item.label")).toHaveLength(0);
    expect(elements("driver-actions.item.change-points")).toHaveLength(1);
  });

  it("shows the core's figures only for the action as it was applied: a changed target says they come after Apply, and does not compute them", async () => {
    await mounted(ACTIONS_PLAN, SEGMENTS);
    expect(elements("driver-actions.item.change-points")).toHaveLength(1);
    fireEvent.change(within(actionRows()[0]).getByLabelText("Target win rate (percent)"), { target: { value: "30" } });
    expect(elements("driver-actions.item.change-points")).toHaveLength(0);
    expect(elements("driver-actions.item.resulting")).toHaveLength(0);
    expect(elements("driver-actions.form.baseline")).toHaveLength(1);
    expect(within(actionRows()[0]).getByTestId("action-pending")).toHaveTextContent(/change in points and the resulting rate/i);
  });

  it("a new action says the same: the baseline now, the core's figures after Apply", async () => {
    await mounted(DEMO, SEGMENTS);
    fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    expect(elements("driver-actions.form.baseline")).toHaveLength(1);
    expect(elements("driver-actions.item.change-points")).toHaveLength(0);
    expect(screen.getByTestId("action-pending")).toBeInTheDocument();
  });
});

describe("actions: the core's words beside the item it refused", () => {
  it.each([
    "Overlaps 'Enterprise win-rate push': both change the win rate for Enterprise, so the change would be counted twice.",
    "Starts in August 2026, which is not after the as-of date, August 31, 2026.",
    "The ramp must be a whole number of months, from 0 to 60.",
    "The target win rate must be between 0% and 100%, not 150%.",
  ])("%s", async (message) => {
    const { editor } = await mounted(ACTIONS_PLAN, SEGMENTS);
    fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    editor.next = { kind: "invalid", errors: [{ section: "actions", index: 2, position: 1, message }] };
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    const beside = await within(actionRows()[1]).findByRole("alert");
    expect(beside).toHaveTextContent(message);
    expect(within(actionRows()[0]).queryByRole("alert")).toBeNull();
  });

  it("a refusal that names no item (the basis cannot be built) stands above the buttons, in the core's words", async () => {
    const { editor } = await mounted(ACTIONS_PLAN, SEGMENTS);
    editor.next = { kind: "invalid", errors: [{ section: null, index: null, position: null, message: "your plan: actions cannot be valued for this company: the price basis is unavailable" }] };
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByTestId("plan-form-errors")).toHaveTextContent("actions cannot be valued for this company");
  });
});

describe("actions: a draft asked for from the worksheet or the grid", () => {
  it("says, while it is not applied, that its value will differ from the tornado's figure and why", async () => {
    const { store } = await mounted(DEMO, SEGMENTS);
    act(() => store.draftAction("acme", { slice: "company", target: "0.2220", origin: "tornado" }));
    const note = await screen.findByTestId("action-origin");
    expect(note).toHaveTextContent(/will differ from the bar's figure/);
    expect(note).toHaveTextContent(/immediate company-wide change from the as-of date/);
    expect(within(actionRows()[0]).getByLabelText("Target win rate (percent)")).toHaveValue("22.2");
  });

  it("a draft from a grid cell says its target starts at the pooled baseline and the cell's number is not the driver", async () => {
    const { store } = await mounted(DEMO, SEGMENTS);
    act(() => store.draftAction("acme", { slice: "enterprise", target: "0.2193", origin: "grid" }));
    const note = await screen.findByTestId("action-origin");
    expect(note).toHaveTextContent(/pooled baseline/);
    expect(note).toHaveTextContent(/dated cohort rate/);
    expect(within(actionRows()[0]).getByLabelText("Slice")).toHaveValue("enterprise");
  });

  it("brings the draft into view and focuses its name", async () => {
    const { store } = await mounted(DEMO, SEGMENTS);
    act(() => store.draftAction("acme", { slice: "enterprise", target: "0.2193", origin: "grid" }));
    await waitFor(() => expect(within(actionRows()[0]).getByLabelText("Action name")).toHaveFocus());
  });

  it("the note goes once the action is applied", async () => {
    const { store } = await mounted(DEMO, SEGMENTS);
    act(() => store.draftAction("acme", { slice: "company", target: "0.2220", origin: "tornado" }));
    await screen.findByTestId("action-origin");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(screen.queryByTestId("action-origin")).toBeNull());
  });
});

describe("the form's intro and the line under its Actions heading", () => {
  it("names actions among what Apply computes, and the line is the core's, not a definition of the driver", async () => {
    await mounted();
    expect(screen.getByText(/Change the hires, programs and actions, then Apply\./)).toBeInTheDocument();
    expect(screen.getByTestId("actions-line")).not.toHaveTextContent(/share of deals created/);
  });
});


describe("actions on the other drivers: the driver, the target in its terms, and the evidence", () => {
  const CORE = DRIVERS_REPORT.driver_actions as Extract<TieoutReport["driver_actions"], { joint_gain: unknown }>;
  const sheet = (DRIVERS_REPORT.worksheet as { drivers: Array<{ driver: string; unit_label: string; current: { value: string }; historical: { low: { setting: string }; high: { setting: string } } }> }).drivers;
  const row = (driver: string) => sheet.find((d) => d.driver === driver)!;
  const elements = (id: string) => Array.from(document.querySelectorAll<HTMLElement>(`[data-binding='${id}']`));
  const mount3 = () => mounted(DRIVERS_PLAN, SEGMENTS, DRIVERS_REPORT);

  it("offers the three drivers in each row, and shows the target in the driver's own terms", async () => {
    await mount3();
    const rows = actionRows().map((r) => within(r));
    expect(rows).toHaveLength(3);
    for (const r of rows) expect(Array.from((r.getByLabelText("Changes") as HTMLSelectElement).options).map((o) => o.text)).toEqual(["Win rate", "Won ARR per win", "Creation productivity"]);
    expect(rows.map((r) => (r.getByLabelText("Changes") as HTMLSelectElement).value)).toEqual(["win_rate", "won_arr", "productivity"]);
    expect(rows[0].getByLabelText("Target win rate (percent)")).toHaveValue("26");
    expect(rows[1].getByLabelText("Target won ARR per win (dollars)")).toHaveValue("450000");
    expect(rows[2].getByLabelText("Target creation productivity (deals)")).toHaveValue("2.6");
  });

  it("takes a dollar or a deal target as typed, and sends it as typed", async () => {
    const { store, editor } = await mount3();
    fireEvent.change(within(actionRows()[1]).getByLabelText("Target won ARR per win (dollars)"), { target: { value: "460000.5" } });
    fireEvent.change(within(actionRows()[2]).getByLabelText("Target creation productivity (deals)"), { target: { value: "2." } });
    expect(store.snapshot.drafts.acme.actions?.[1].target).toBe("460000.5");
    expect(store.snapshot.drafts.acme.actions?.[2].target).toBe("2.");
    expect(editor.sent).toEqual([]);
  });

  it("shows each driver's pooled baseline, low and high from its own worksheet row, and the unit the report gives", async () => {
    const { context } = await mount3();
    const expected = [
      { id: "driver-actions.form.baseline", texts: [fmt.percent1(row("win_rate").current.value)] },
      { id: "driver-actions.form.low", texts: [fmt.percent1(row("win_rate").historical.low.setting)] },
      { id: "driver-actions.form.high", texts: [fmt.percent1(row("win_rate").historical.high.setting)] },
      { id: "driver-actions.form.won_arr.baseline", texts: [fmt.usdShort(row("won_arr").current.value)] },
      { id: "driver-actions.form.won_arr.low", texts: [fmt.usdShort(row("won_arr").historical.low.setting)] },
      { id: "driver-actions.form.won_arr.high", texts: [fmt.usdShort(row("won_arr").historical.high.setting)] },
      { id: "driver-actions.form.won_arr.unit", texts: [row("won_arr").unit_label] },
      { id: "driver-actions.form.productivity.baseline", texts: [fmt.decimal2(row("productivity").current.value)] },
      { id: "driver-actions.form.productivity.low", texts: [fmt.decimal2(row("productivity").historical.low.setting)] },
      { id: "driver-actions.form.productivity.high", texts: [fmt.decimal2(row("productivity").historical.high.setting)] },
      { id: "driver-actions.form.productivity.unit", texts: [row("productivity").unit_label] },
    ];
    expect(checkBindings(document.body, expected, [], DRIVER_ACTION_BINDINGS, context, ["driver-actions.item.", "driver-actions.form.line"])).toEqual([]);
    expect(row("won_arr").unit_label).toBe("dollars of ARR per won deal");
    expect(row("productivity").unit_label).toBe("created deals per ramped AE-month");
  });

  it("shows, for an action as applied, the core's percent on the baseline and the resulting value, and its label only outside the settings", async () => {
    const { context } = await mount3();
    const [size, creation] = [CORE.items[1], CORE.items[2]];
    const e1 = size.evidence as { change_percent: string; resulting: string; label: string; position: string };
    const e2 = creation.evidence as { change_percent: string; resulting: string; label: string; position: string };
    expect(e1.position).toBe("inside");
    expect(e2.position).toBe("above");
    const failures = checkBindings(
      document.body,
      [
        { id: "driver-actions.item.change-percent", texts: [fmt.decimal2(e1.change_percent), fmt.decimal2(e2.change_percent)], rows: ["/driver_actions/items/1", "/driver_actions/items/2"] },
        { id: "driver-actions.item.resulting.won_arr", texts: [fmt.usdShort(e1.resulting)], rows: ["/driver_actions/items/1"] },
        { id: "driver-actions.item.resulting.productivity", texts: [fmt.decimal2(e2.resulting)], rows: ["/driver_actions/items/2"] },
        { id: "driver-actions.item.label", texts: [(CORE.items[0].evidence as { label: string }).label, e2.label], rows: ["/driver_actions/items/0", "/driver_actions/items/2"] },
      ],
      [],
      DRIVER_ACTION_BINDINGS,
      context,
      ["driver-actions.form."],
    );
    expect(failures).toEqual([]);
    expect(unboundDigits(document.body)).toEqual([]);
  });

  it("says the core's line for a plan that acts on more than the win rate", async () => {
    await mount3();
    const line = screen.getByTestId("actions-line");
    expect(line).toHaveTextContent(CORE.line);
    expect(line).toHaveTextContent(/the size of a win, or how many deals people create/);
  });

  it("moves a row to another driver with the target at that driver's baseline, and renames it only if it still had its own default name", async () => {
    const { store } = await mounted(DEMO, SEGMENTS, DRIVERS_REPORT);
    fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    fireEvent.change(screen.getByLabelText("Changes"), { target: { value: "won_arr" } });
    expect(store.snapshot.drafts.acme.actions).toEqual([{ id: "action-0", name: "Company deal-size action", driver: "won_arr", slice: "company", start: "2026-09", ramp_months: 0, target: "413835.73" }]);
    fireEvent.change(screen.getByLabelText("Action name"), { target: { value: "Bigger deals" } });
    fireEvent.change(screen.getByLabelText("Changes"), { target: { value: "productivity" } });
    expect(store.snapshot.drafts.acme.actions?.[0]).toMatchObject({ name: "Bigger deals", driver: "productivity", target: "2.0662" });
    expect(screen.getByLabelText("Target creation productivity (deals)")).toHaveValue("2.0662");
  });

  it("adds the next action on the driver with room: the win rate by slice, then the size, then creation", async () => {
    const { store } = await mounted(DEMO, SEGMENTS, DRIVERS_REPORT);
    for (let n = 0; n < 3; n++) fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    expect(store.snapshot.drafts.acme.actions?.map((a) => [a.driver, a.slice])).toEqual([
      ["win_rate", "company"],
      ["win_rate", "commercial"],
      ["win_rate", "enterprise"],
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Add an action" }));
    expect(store.snapshot.drafts.acme.actions?.[3]).toMatchObject({ driver: "won_arr", slice: "company" });
  });

  it("shows the core's words beside a size or creation action it refused", async () => {
    const { editor } = await mount3();
    const message = "The target won ARR per win must be zero or more dollars, not -$5.";
    editor.next = { kind: "invalid", errors: [{ section: "actions", index: 2, position: 1, message }] };
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await within(actionRows()[1]).findByRole("alert")).toHaveTextContent(message);
  });

  it("names the driver in the note on a draft from a bar or a cell", async () => {
    const { store } = await mounted(DEMO, SEGMENTS, DRIVERS_REPORT);
    act(() => store.draftAction("acme", { slice: "company", driver: "won_arr", target: "605308.57", origin: "tornado" }));
    expect(await screen.findByTestId("action-origin")).toHaveTextContent(/Started from the deal-size bar\. Its value will differ from the bar's figure/);
    act(() => store.draftAction("acme", { slice: "enterprise", driver: "productivity", target: "2.0662", origin: "grid" }));
    await waitFor(() => expect(screen.getAllByTestId("action-origin")).toHaveLength(2));
    const notes = screen.getAllByTestId("action-origin").map((n) => n.textContent);
    expect(notes[1]).toMatch(/deals created in the period/);
    expect(notes[1]).toMatch(/pooled baseline/);
    expect(elements("driver-actions.item.change-percent")).toHaveLength(0);
  });

  it("shows no figure of the core's for an action whose report entry is for another driver (the report is the last Apply's, the plan this one's): the pending line stands, and nothing is read from the wrong shape", async () => {
    const changed: PlanDoc = { ...ACTIONS_PLAN, actions: [{ ...ACTIONS_PLAN.actions![0], driver: "won_arr", target: "450000" }] };
    await mounted(changed, SEGMENTS);
    expect(document.querySelectorAll("[data-binding='driver-actions.item.change-percent']")).toHaveLength(0);
    expect(document.querySelectorAll("[data-binding='driver-actions.item.change-points']")).toHaveLength(0);
    expect(screen.getByTestId("action-pending")).toBeInTheDocument();
  });
});
