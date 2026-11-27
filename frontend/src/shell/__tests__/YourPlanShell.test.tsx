import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import App from "../../App";
import { EditorFailure } from "../../editor/client";
import type { EditorStatus } from "../../editor/client";
import type { ApplyOutcome, Facts, PlanDoc } from "../../editor/protocol";
import type { Editor } from "../../editor/store";
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

const DEMO: PlanDoc = { hires: [{ segment: "mid_market", start: "2026-10", count: 2 }], programs: [{ name: "Referrals", pipeline: 6000000, start: "2026-10" }] };

/** What the worker would send for the demo plan: the committed report, renamed as the core's editor entry names it. */
function computed(company: string): ApplyOutcome {
  const report = structuredClone(files.report(company, "demo-plan"));
  report.inputs.identity.scenario = "your-plan";
  (report.plan as { file: string }).file = "your-plan";
  const row = { ...files.comparison(company).rows.find((r) => r.scenario === "demo-plan")!, scenario: "your-plan", label: "Your plan" };
  return { kind: "report", report, comparison: row };
}

class FakeEditor implements Editor {
  status: EditorStatus = { phase: "idle" };
  opened: string[] = [];
  applied: PlanDoc[] = [];
  failNext: EditorFailure | null = null;
  private listeners = new Set<() => void>();
  subscribe = (l: () => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };
  say(status: EditorStatus) {
    this.status = status;
    this.listeners.forEach((l) => l());
  }
  open(company: string): Promise<Facts> {
    this.opened.push(company);
    return Promise.resolve({ company, segments: [{ value: "mid_market", label: "Mid Market" }], months: ["2026-09", "2026-10"], max_dollars: "99999999", demo_plan: DEMO });
  }
  apply(company: string, plan: PlanDoc): Promise<ApplyOutcome> {
    this.applied.push(plan);
    if (this.failNext) {
      const failure = this.failNext;
      this.failNext = null;
      return Promise.reject(failure);
    }
    return Promise.resolve(computed(company));
  }
}

function open(url: string, editor: FakeEditor, desktop: boolean) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <App loaders={fromDisk} editor={editor} desktop={desktop} />
    </MemoryRouter>,
  );
}

describe("on a desktop screen", () => {
  it("offers the four named scenarios as choices and Edit plan beside them, and nothing starts until it is chosen", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    const summary = await screen.findByTestId("worksheet-summary");
    const named = within(within(summary).getByRole("group", { name: "Scenario" }));
    expect(named.getAllByRole("button").map((b) => b.textContent)).toEqual(["As signed", "Demo plan", "Hires only", "Program only"]);
    const edit = within(summary).getByRole("button", { name: "Edit plan" });
    expect(edit).toHaveAttribute("aria-pressed", "false");
    expect(editor.opened).toEqual([]);
    expect(screen.queryByTestId("your-plan-mark")).toBeNull();
    expect(screen.queryByTestId("plan-form")).toBeNull();
  });

  it("the as-signed line offers the same choice in a sentence, and it opens the form in place under the summary", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    const notice = await screen.findByTestId("no-plan");
    expect(notice).toHaveTextContent("No plan is in force");
    expect(notice).toHaveTextContent("Build a plan to see what it changes, or pick a scenario above.");
    expect(editor.opened).toEqual([]);
    fireEvent.click(within(notice).getByRole("button", { name: "Build a plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(editor.opened).toEqual(["sprout-labs"]);
    const summary = screen.getByTestId("worksheet-summary");
    expect(summary.compareDocumentPosition(screen.getByTestId("plan-form")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("moves focus to the form's heading and scrolls it into view when the form opens", async () => {
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    };
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=your-plan", editor, true);
    const form = await screen.findByTestId("plan-form");
    const heading = within(form).getByRole("heading", { name: "Your plan" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(scrolled.some((el) => el.contains(form) || form.contains(el) || el === form.parentElement)).toBe(true);
  });

  it.each(["Forecast", "Capacity", "Pipeline", "Trust"])("%s ends with a link to the editor that opens it on the Plan screen, and starts nothing before it is clicked", async (name) => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    await screen.findByTestId("worksheet-summary");
    fireEvent.click(within(screen.getByRole("navigation", { name: "Screens" })).getByRole("link", { name }));
    await waitFor(() => expect(document.querySelector("main h2")?.textContent).toBe(name));
    const line = await screen.findByTestId("build-your-own");
    expect(line).toHaveTextContent("Want to try your own hires and programs? Build your own plan.");
    expect(editor.opened).toEqual([]);
    fireEvent.click(within(line).getByRole("link", { name: "Build your own plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(document.querySelector("main h2")?.textContent).toBe("Plan");
    expect(editor.opened).toEqual(["sprout-labs"]);
  });

  it("shows what the editor is doing while it loads, then the plan screen with its form, marked as the visitor's own", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    fireEvent.click(await screen.findByRole("button", { name: "Edit plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Edit plan" })).toHaveAttribute("aria-pressed", "true");
    expect(editor.opened).toEqual(["sprout-labs"]);
    expect(editor.applied).toEqual([DEMO]);
    expect(screen.getByTestId("your-plan-mark")).toHaveTextContent("Your plan, computed in your browser; ranges unvalidated");
    expect(document.querySelector("[data-binding='worksheet.summary.remaining-gap']")?.getAttribute("data-scenario")).toBe("your-plan");
    expect(screen.getAllByTestId("compare-row").map((r) => r.querySelector("[data-binding]")?.textContent)).toContain("Your plan");
  });

  it("says what the worker reports while the first load is under way", async () => {
    const editor = new FakeEditor();
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    const open_ = editor.open.bind(editor);
    editor.open = async (company) => {
      editor.say({ phase: "starting", company, progress: "Loading the numerical libraries" });
      await held;
      return open_(company);
    };
    open("/plan?company=sprout-labs&scenario=your-plan", editor, true);
    expect(await screen.findByTestId("session-status")).toHaveTextContent("Loading the numerical libraries");
    await act(async () => release());
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
  });

  it("marks every screen, and the Trust screen offers no file for a report that never was one", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=your-plan", editor, true);
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    for (const name of ["Forecast", "Capacity", "Pipeline", "Trust", "Plan"]) {
      fireEvent.click(within(screen.getByRole("navigation", { name: "Screens" })).getByRole("link", { name }));
      await waitFor(() => expect(document.querySelector("main h2")?.textContent).toBe(name));
      expect(screen.getByTestId("your-plan-mark")).toBeInTheDocument();
    }
    fireEvent.click(within(screen.getByRole("navigation", { name: "Screens" })).getByRole("link", { name: "Trust" }));
    await waitFor(() => expect(document.querySelector("main h2")?.textContent).toBe("Trust"));
    expect(document.querySelector("main a[href*='your-plan']")).toBeNull();
    expect(screen.getByTestId("your-plan-not-a-file")).toBeInTheDocument();
  });

  it("keeps the form as the visitor left it across screens, and only one worker request is made", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=your-plan", editor, true);
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    fireEvent.change(within(screen.getAllByTestId("hire-row")[0]).getByLabelText("How many"), { target: { value: "7" } });
    fireEvent.click(within(screen.getByRole("navigation", { name: "Screens" })).getByRole("link", { name: "Forecast" }));
    await waitFor(() => expect(document.querySelector("main h2")?.textContent).toBe("Forecast"));
    fireEvent.click(within(screen.getByRole("navigation", { name: "Screens" })).getByRole("link", { name: "Plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(within(screen.getAllByTestId("hire-row")[0]).getByLabelText("How many")).toHaveValue(7);
    expect(editor.applied).toHaveLength(1);
  });

  it("Apply replaces the figures on screen with no new load", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=your-plan", editor, true);
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    const before = document.querySelector("[data-binding='worksheet.summary.remaining-gap']");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(editor.applied).toHaveLength(2));
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled());
    expect(screen.queryByTestId("session-status")).toBeNull();
    expect(document.querySelector("[data-binding='worksheet.summary.remaining-gap']")).not.toBeNull();
    expect(before).not.toBeNull();
  });

  it("a first load that fails is an error with a way to try again", async () => {
    const editor = new FakeEditor();
    editor.failNext = new EditorFailure("timeout", "no answer within the time allowed");
    open("/plan?company=sprout-labs&scenario=your-plan", editor, true);
    const status = await screen.findByTestId("session-status");
    await waitFor(() => expect(status).toHaveTextContent("no answer within the time allowed"));
    fireEvent.click(within(screen.getByTestId("session-status")).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
  });
});

describe("the tornado opens the editor in place", () => {
  it("Add to plan on an action opens the form with that item appended, and applies nothing more", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    const row = await waitFor(() => {
      const el = document.querySelector("[data-testid='worksheet-action-row'][data-kind='hire']");
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    expect(editor.opened).toEqual([]);
    fireEvent.click(within(row).getByRole("button", { name: "Add to plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(screen.getAllByTestId("hire-row")).toHaveLength(2);
    expect(screen.getAllByTestId("program-row")).toHaveLength(1);
    expect(screen.getByTestId("plan-unapplied")).toBeInTheDocument();
    expect(editor.applied).toEqual([DEMO]);
  });

  it("the program action appends a program, and clicking a driver's row opens the editor as it is", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    const program = await waitFor(() => {
      const el = document.querySelector("[data-testid='worksheet-action-row'][data-kind='program']");
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    fireEvent.click(within(program).getByRole("button", { name: "Add to plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(screen.getAllByTestId("program-row")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "As signed" }));
    await waitFor(() => expect(screen.queryByTestId("plan-form")).toBeNull());
    fireEvent.click(document.querySelector("[data-testid='driver-row']")!);
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(screen.getAllByTestId("program-row")).toHaveLength(2);
  });

  it("opening a driver's quarters does not open the editor", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    const toggle = await waitFor(() => {
      const el = document.querySelector("[data-testid='driver-row'] button[aria-expanded]");
      if (!el) throw new Error("not yet");
      return el as HTMLElement;
    });
    fireEvent.click(toggle);
    expect(screen.getByTestId("driver-detail")).toHaveTextContent("assumption to discuss");
    expect(editor.opened).toEqual([]);
  });
});

describe("on a phone", () => {
  it("has no Edit plan, says editing needs a larger screen, and never touches the editor", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, false);
    const summary = await screen.findByTestId("worksheet-summary");
    expect(within(summary).queryByRole("button", { name: "Edit plan" })).toBeNull();
    expect(within(summary).getByText(/Editing your own plan needs a larger screen\./)).toBeInTheDocument();
    expect(screen.getByTestId("no-plan")).not.toHaveTextContent("Build a plan");
    expect(screen.queryByRole("button", { name: /build a plan|edit plan|build your own plan|add to plan/i })).toBeNull();
    for (const name of ["Forecast", "Capacity", "Pipeline", "Trust"]) {
      fireEvent.click(within(screen.getByRole("navigation", { name: "Screens" })).getByRole("link", { name }));
      await waitFor(() => expect(document.querySelector("main h2")?.textContent).toBe(name));
      expect(screen.queryByRole("link", { name: "Build your own plan" })).toBeNull();
    }
    expect(editor.opened).toEqual([]);
  });
});
