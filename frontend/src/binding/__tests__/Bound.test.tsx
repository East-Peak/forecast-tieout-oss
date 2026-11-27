import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ReportIndex, ScenarioComparison } from "../../generated/appFiles";
import type { TieoutReport } from "../../generated/report";
import { Bound, BindingProvider, bind, useBindingContext } from "../Bound";
import { UnboundPath } from "../pointer";

const report = {
  gap: {
    fiscal_year: {
      expected: "6119924.84",
      gap: "-1880075.16",
      shortfall: "100.00",
      zero: "0.00",
      target: null,
      why: "no target in this window",
    },
  },
  inputs: { as_of: "2026-08-31", fiscal_year: "FY26" },
  history: { facts: { months_of_history: 31 } },
  coverage: { c80: 0.8333 },
  roster: { ramped: "93.60", heads: 99, ratio: "1.31", cents: "13.98", ok: true, bad: false, file: "x/as-signed.md" },
} as unknown as TieoutReport;
const index = { companies: [{ id: "x", description: "A company: $10M plan" }] } as unknown as ReportIndex;
const comparison = {
  rows: [{ scenario: "as-signed", fiscal_year_gap_change: null }, { scenario: "demo-plan", fiscal_year_gap_change: "-36261.69" }],
} as unknown as ScenarioComparison;

function show(node: React.ReactNode, choose?: (company: string, scenario: string) => void) {
  return render(
    <BindingProvider company="x" scenario="demo-plan" files={{ report, index, comparison }} choose={choose}>
      {node}
    </BindingProvider>,
  );
}

describe("Bound", () => {
  it("shows the file's value in its named format and says where it came from", () => {
    show(<Bound binding={bind({ id: "expected", path: "/gap/fiscal_year/expected", unit: "usd", format: "usd-short" })} />);
    const el = screen.getByText("$6.1M");
    expect(el).toHaveAttribute("data-binding", "expected");
    expect(el).toHaveAttribute("data-source", "report");
    expect(el).toHaveAttribute("data-path", "/gap/fiscal_year/expected");
    expect(el).toHaveAttribute("data-format", "usd-short");
    expect(el).toHaveAttribute("data-company", "x");
    expect(el).toHaveAttribute("data-scenario", "demo-plan");
  });

  it("reads each of the three files", () => {
    show(
      <>
        <Bound binding={bind({ id: "desc", source: "index", path: "/companies/0/description", unit: "text", format: "text" })} />
        <Bound binding={bind({ id: "chg", source: "comparison", path: "/rows/1/fiscal_year_gap_change", unit: "usd", format: "usd-full" })} />
      </>,
    );
    expect(screen.getByText("A company: $10M plan")).toBeInTheDocument();
    expect(screen.getByText("-$36,262")).toBeInTheDocument();
  });

  it("formats percent, count, date and text", () => {
    show(
      <>
        <Bound binding={bind({ id: "c", path: "/coverage/c80", unit: "fraction", format: "percent1" })} />
        <Bound binding={bind({ id: "n", path: "/history/facts/months_of_history", unit: "count", format: "count" })} />
        <Bound binding={bind({ id: "d", path: "/inputs/as_of", unit: "date", format: "date" })} />
        <Bound binding={bind({ id: "t", path: "/inputs/fiscal_year", unit: "text", format: "text" })} />
      </>,
    );
    for (const text of ["83.3%", "31", "Aug 31, 2026", "FY26"]) expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("a row binding reads from a row of a collection", () => {
    show(<Bound binding={bind({ id: "e", path: "/expected", unit: "usd", format: "usd-full" })} row="/gap/fiscal_year" />);
    expect(screen.getByText("$6,119,925")).toHaveAttribute("data-path", "/gap/fiscal_year/expected");
  });

  it("a null in the file is shown in words with its reason, never as zero", () => {
    show(
      <Bound
        binding={bind({
          id: "target",
          path: "/gap/fiscal_year/target",
          unit: "usd",
          format: "usd-short",
          unavailable: { reason: "/gap/fiscal_year/why" },
        })}
      />,
    );
    const el = screen.getByText(/unavailable/);
    expect(el).toHaveAttribute("data-unavailable", "true");
    expect(el.textContent).toBe("unavailable: no target in this window");
    expect(el.textContent).not.toMatch(/\$0/);
  });

  it("a null can be stated in the file's own words instead of a reason pointer", () => {
    show(
      <Bound
        binding={bind({
          id: "cost",
          path: "/gap/fiscal_year/target",
          unit: "usd",
          format: "usd-short",
          unavailable: { words: "cost not entered" },
        })}
      />,
    );
    expect(screen.getByText("cost not entered")).toHaveAttribute("data-unavailable", "true");
  });

  it("an absolute reason is read from the report root even for a row binding", () => {
    show(
      <Bound
        binding={bind({
          id: "r",
          path: "/target",
          unit: "usd",
          format: "usd-short",
          unavailable: { reason: "/gap/fiscal_year/why", absolute: true },
        })}
        row="/gap/fiscal_year"
      />,
    );
    expect(screen.getByText("unavailable: no target in this window")).toBeInTheDocument();
  });

  it("{company} and {scenario} in a path stand for the visitor's choice", () => {
    show(
      <>
        <Bound
          binding={bind({
            id: "s",
            source: "comparison",
            path: "/rows/{scenario={scenario}}/fiscal_year_gap_change",
            unit: "usd",
            format: "usd-full",
          })}
        />
        <Bound binding={bind({ id: "c", source: "index", path: "/companies/{id={company}}/description", unit: "text", format: "text" })} />
      </>,
    );
    expect(screen.getByText("-$36,262")).toHaveAttribute("data-path", "/rows/{scenario=demo-plan}/fiscal_year_gap_change");
    expect(screen.getByText("A company: $10M plan")).toBeInTheDocument();
  });

  it("tints a shortfall red and being ahead green, and says which in data-tone", () => {
    show(
      <>
        <Bound binding={bind({ id: "short", path: "/gap/fiscal_year/shortfall", unit: "usd", format: "usd-short", tint: "shortfall" })} />
        <Bound binding={bind({ id: "ahead", path: "/gap/fiscal_year/gap", unit: "usd", format: "usd-short", tint: "shortfall" })} />
        <Bound binding={bind({ id: "none", path: "/gap/fiscal_year/zero", unit: "usd", format: "usd-short", tint: "shortfall" })} />
      </>,
    );
    expect(screen.getByText("$100").getAttribute("data-tone")).toBe("short");
    expect(screen.getByText("$100").className).toMatch(/red/);
    expect(screen.getByText("-$1.9M").getAttribute("data-tone")).toBe("ahead");
    expect(screen.getByText("-$1.9M").className).toMatch(/green/);
    expect(screen.getByText("$0").getAttribute("data-tone")).toBe("level");
  });

  it("a null with no stated way to say so is an error, not a blank", () => {
    expect(() =>
      show(<Bound binding={bind({ id: "target", path: "/gap/fiscal_year/target", unit: "usd", format: "usd-short" })} />),
    ).toThrow(/null/);
  });

  it("a path the file does not have is an error", () => {
    expect(() => show(<Bound binding={bind({ id: "x", path: "/gap/nowhere", unit: "usd", format: "usd-short" })} />)).toThrow(UnboundPath);
  });

  it("a value of the wrong kind for its format is an error, not NaN", () => {
    expect(() => show(<Bound binding={bind({ id: "x", path: "/inputs/fiscal_year", unit: "usd", format: "usd-short" })} />)).toThrow(/decimal/);
  });
});

describe("bind", () => {
  it("refuses a format that does not belong to its unit", () => {
    expect(() => bind({ id: "x", path: "/a", unit: "usd", format: "percent1" })).toThrow(/unit/);
    expect(() => bind({ id: "x", path: "/a", unit: "count", format: "usd-full" })).toThrow(/unit/);
  });
  it("defaults to the report", () => {
    expect(bind({ id: "x", path: "/a", unit: "text", format: "text" }).source).toBe("report");
  });
});

describe("quantities, units and flags", () => {
  it("shows a quantity at the report's own places, a multiple and cents", () => {
    show(
      <>
        <Bound binding={bind({ id: "q1", path: "/roster/ramped", unit: "quantity", format: "quantity" })} />
        <Bound binding={bind({ id: "q2", path: "/roster/heads", unit: "quantity", format: "quantity" })} />
        <Bound binding={bind({ id: "q3", path: "/roster/ratio", unit: "quantity", format: "multiple" })} />
        <Bound binding={bind({ id: "q4", path: "/roster/cents", unit: "quantity", format: "cents" })} />
      </>,
    );
    for (const text of ["93.60", "99", "1.31x", "13.98\u00a2"]) expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("says passed or failed for a true or false in the file", () => {
    show(
      <>
        <Bound binding={bind({ id: "ok", path: "/roster/ok", unit: "flag", format: "passed" })} />
        <Bound binding={bind({ id: "bad", path: "/roster/bad", unit: "flag", format: "passed" })} />
      </>,
    );
    expect(screen.getByText("passed")).toHaveAttribute("data-binding", "ok");
    expect(screen.getByText("failed")).toHaveAttribute("data-binding", "bad");
  });

  it("a text binding can be a link to a published file, its address read from the file", () => {
    show(<Bound binding={bind({ id: "md", path: "/roster/file", unit: "text", format: "text" })} linkBase="/data/reports/" />);
    const link = screen.getByRole("link", { name: "x/as-signed.md" });
    expect(link).toHaveAttribute("href", "/data/reports/x/as-signed.md");
    expect(link).toHaveAttribute("data-binding", "md");
    expect(link).toHaveAttribute("data-path", "/roster/file");
  });

  it("the provider can pass on the visitor's way to choose another scenario", () => {
    const seen: string[] = [];
    function Chooser() {
      const { choose } = useBindingContext();
      return <button onClick={() => choose?.("x", "hires-only")}>go</button>;
    }
    show(<Chooser />, (company, scenario) => seen.push(`${company}/${scenario}`));
    screen.getByText("go").click();
    expect(seen).toEqual(["x/hires-only"]);
  });
});
