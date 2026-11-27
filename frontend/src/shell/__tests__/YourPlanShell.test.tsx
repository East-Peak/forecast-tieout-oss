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
  it("offers Your plan beside the four named scenarios, and nothing starts until it is chosen", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    const picker = await screen.findByTestId("scenario-picker");
    expect(within(picker).getAllByRole("button").map((b) => b.textContent)).toEqual(["As signed", "Demo plan", "Hires only", "Program only", "Your plan"]);
    expect(editor.opened).toEqual([]);
    expect(screen.queryByTestId("your-plan-mark")).toBeNull();
    expect(screen.queryByTestId("plan-form")).toBeNull();
  });

  it("shows what the editor is doing while it loads, then the plan screen with its form, marked as the visitor's own", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, true);
    fireEvent.click(await screen.findByRole("button", { name: "Your plan" }));
    await waitFor(() => expect(screen.getByTestId("plan-form")).toBeInTheDocument());
    expect(editor.opened).toEqual(["sprout-labs"]);
    expect(editor.applied).toEqual([DEMO]);
    expect(screen.getByTestId("your-plan-mark")).toHaveTextContent("Your plan, computed in your browser; ranges unvalidated");
    expect(document.querySelector("[data-binding='plan.gap']")?.getAttribute("data-scenario")).toBe("your-plan");
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
    const before = document.querySelector("[data-binding='plan.gap']");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(editor.applied).toHaveLength(2));
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled());
    expect(screen.queryByTestId("session-status")).toBeNull();
    expect(document.querySelector("[data-binding='plan.gap']")).not.toBeNull();
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

describe("on a phone", () => {
  it("has no Your plan, says editing needs a larger screen, and never touches the editor", async () => {
    const editor = new FakeEditor();
    open("/plan?company=sprout-labs&scenario=as-signed", editor, false);
    const picker = await screen.findByTestId("scenario-picker");
    expect(within(picker).queryByRole("button", { name: "Your plan" })).toBeNull();
    expect(within(picker).getByText("Editing your own plan needs a larger screen.")).toBeInTheDocument();
    expect(editor.opened).toEqual([]);
  });
});
