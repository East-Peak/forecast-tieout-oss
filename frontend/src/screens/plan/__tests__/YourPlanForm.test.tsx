import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ApplyOutcome, Facts, PlanDoc } from "../../../editor/protocol";
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
  async apply(_company: string, plan: PlanDoc): Promise<ApplyOutcome> {
    this.sent.push(plan);
    if (this.gate) await this.gate;
    const next = this.next ?? { kind: "report" as const, report: { tag: "r" } as never, comparison: { scenario: "your-plan" } as never };
    if (next instanceof Error) throw next;
    return next;
  }
}

async function mounted() {
  const editor = new FakeEditor();
  const store = new YourPlanStore(editor);
  await store.load("acme");
  editor.sent.length = 0;
  render(
    <YourPlanProvider store={store} desktop>
      <YourPlanForm company="acme" />
    </YourPlanProvider>,
  );
  return { editor, store };
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
