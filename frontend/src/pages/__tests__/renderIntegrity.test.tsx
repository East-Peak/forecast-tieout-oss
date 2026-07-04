import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

import allowlistJson from "../../../tests/render-allowlist.json";
import mightyProfileJson from "../../../public/data/profiles/mighty-oak-holdings.json";
import mightyPlanJson from "../../../public/data/profiles/mighty-oak-holdings/plans/mighty-fy26-abm-gap.json";
import mightySnapshotJson from "../../../public/data/profiles/mighty-oak-holdings/snapshot.json";
import saplingProfileJson from "../../../public/data/profiles/sapling-industries.json";
import saplingPlanJson from "../../../public/data/profiles/sapling-industries/plans/sapling-fy26-segment-shift.json";
import saplingSnapshotJson from "../../../public/data/profiles/sapling-industries/snapshot.json";
import sproutProfileJson from "../../../public/data/profiles/sprout-labs.json";
import sproutPlanJson from "../../../public/data/profiles/sprout-labs/plans/sprout-fy26-pmf.json";
import sproutSnapshotJson from "../../../public/data/profiles/sprout-labs/snapshot.json";
import { PlanningSessionProvider } from "../../context/PlanningSessionContext";
import type { PlanningSessionContextValue } from "../../context/PlanningSessionContext";
import { normalizeToplineHealthStatus } from "../../lib/healthStatus";
import { normalizeOrgProfile } from "../../lib/orgProfiles";
import type { OrgProfile, RawOrgProfile } from "../../lib/orgProfiles";
import { normalizePlanPreset } from "../../lib/plans";
import type { PlanPreset, RawPlanPreset } from "../../lib/plans";
import type { Snapshot } from "../../types/snapshot";
import AuditReadiness from "../AuditReadiness";
import BookingsBridge from "../BookingsBridge";
import CapacityHeadcount from "../CapacityHeadcount";
import ExportPack from "../ExportPack";
import FunnelHealth from "../FunnelHealth";
import Methodology from "../Methodology";
import PipelineInventory from "../PipelineInventory";
import ScenarioPlanner from "../ScenarioPlanner";
import TargetSetter from "../TargetSetter";

type PersonaId = "sprout-labs" | "sapling-industries" | "mighty-oak-holdings";

interface PersonaFixture {
  id: PersonaId;
  profile: OrgProfile;
  plan: PlanPreset;
  snapshot: Snapshot;
}

interface MetricTuple {
  page: string;
  persona: PersonaId;
  label: string;
  value: string;
}

interface ChartTuple {
  page: string;
  persona: PersonaId;
  chart: string;
  primarySeries: string;
  values: number[];
}

interface TableIssueTuple {
  page: string;
  persona: PersonaId;
  table: string;
  issue: string;
}

interface TableAllowlistEntry extends Omit<TableIssueTuple, "persona"> {
  persona: PersonaId | "*";
  rationale: string;
}

interface RenderAllowlist {
  metrics: Array<MetricTuple & { rationale: string }>;
  charts: Array<Omit<ChartTuple, "values"> & { rationale: string }>;
  tables: TableAllowlistEntry[];
}

const DATA_ROOT = "http://localhost/data";
const DEGENERATE_VALUE = /^(\$0(?:\.0+)?[KMB]?|--|—|NaN|\$NaN|undefined|null|Infinity|\s*)$/i;
const DEGENERATE_TABLE_CELL =
  /^(?:\$?0(?:\.0+)?(?:[KMB])?|0(?:\.0+)?%|0(?:\.0+)?pp|--|—|NaN|\$NaN|undefined|null|\s*)$/i;
const NUMERIC_TABLE_CELL =
  /^\(?[+-]?\$?\d[\d,]*(?:\.\d+)?(?:[KMB])?(?:%|pp)?\)?$/i;

const PAGES = [
  { path: "/bookings", label: "Bookings Bridge", Component: BookingsBridge, expectedCharts: 2 },
  { path: "/capacity", label: "Capacity & Headcount", Component: CapacityHeadcount, expectedCharts: 2 },
  { path: "/funnel", label: "Funnel Health", Component: FunnelHealth, expectedCharts: 0 },
  { path: "/inventory", label: "Pipeline Inventory", Component: PipelineInventory, expectedCharts: 2 },
  { path: "/audit", label: "Audit", Component: AuditReadiness, expectedCharts: 0 },
  { path: "/export", label: "Export Pack", Component: ExportPack, expectedCharts: 0 },
  { path: "/methodology", label: "Methodology", Component: Methodology, expectedCharts: 0 },
  { path: "/targets", label: "Target Setter", Component: TargetSetter, expectedCharts: 1 },
  { path: "/scenario", label: "Scenario Planner", Component: ScenarioPlanner, expectedCharts: 2 },
] as const;

const SAPLING_HEADLINE_ASSERTIONS = [
  { path: "/bookings", label: "Bookings Bridge", Component: BookingsBridge, expectedText: "$50.4M" },
  { path: "/capacity", label: "Capacity & Headcount", Component: CapacityHeadcount, expectedText: "$22.5M" },
  { path: "/funnel", label: "Funnel Health", Component: FunnelHealth, expectedText: "$8.0M" },
  { path: "/inventory", label: "Pipeline Inventory", Component: PipelineInventory, expectedText: "$115.4M" },
  { path: "/audit", label: "Audit", Component: AuditReadiness, expectedText: "$8.0M" },
  { path: "/export", label: "Export Pack", Component: ExportPack, expectedText: "$60.0M" },
  { path: "/methodology", label: "Methodology", Component: Methodology, expectedText: "$978K" },
  { path: "/targets", label: "Target Setter", Component: TargetSetter, expectedText: "$50.0M plan" },
  { path: "/scenario", label: "Scenario Planner", Component: ScenarioPlanner, expectedText: "$50.4M" },
] as const;

const PERSONAS: PersonaFixture[] = [
  buildPersona("sprout-labs", sproutProfileJson, sproutPlanJson, sproutSnapshotJson),
  buildPersona("sapling-industries", saplingProfileJson, saplingPlanJson, saplingSnapshotJson),
  buildPersona("mighty-oak-holdings", mightyProfileJson, mightyPlanJson, mightySnapshotJson),
];

afterEach(() => {
  cleanup();
});

describe("render integrity allowlist", () => {
  it("requires every allowlist entry to carry a rationale", () => {
    const allowlist = allowlistJson as RenderAllowlist;
    const missingRationales = [
      ...allowlist.metrics
        .filter((entry) => entry.rationale.trim().length === 0)
        .map((entry) => `metric ${entry.page}/${entry.persona}/${entry.label}`),
      ...allowlist.charts
        .filter((entry) => entry.rationale.trim().length === 0)
        .map((entry) => `chart ${entry.page}/${entry.persona}/${entry.chart}`),
      ...allowlist.tables
        .filter((entry) => entry.rationale.trim().length === 0)
        .map((entry) => `table ${entry.page}/${entry.persona}/${entry.table}/${entry.issue}`),
    ];

    expect(missingRationales).toEqual([]);
  });
});

describe("all public pages render non-degenerate metrics and non-empty charts", () => {
  it("covers every route for every public persona fixture", () => {
    const allowlist = allowlistJson as RenderAllowlist;
    const metrics: MetricTuple[] = [];
    const charts: ChartTuple[] = [];
    const tableIssues: TableIssueTuple[] = [];
    let tablesChecked = 0;
    const failures: string[] = [];

    for (const persona of PERSONAS) {
      for (const page of PAGES) {
        const { container } = renderPage(persona, page.path, <page.Component />);
        const pageMetrics = collectMetrics(container, page.label, persona.id);
        const pageCharts = collectCharts(container, page.label, persona.id);
        const pageTableIssues = collectTableIssues(container, page.label, persona.id);
        metrics.push(...pageMetrics);
        charts.push(...pageCharts);
        tableIssues.push(...pageTableIssues);
        tablesChecked += container.querySelectorAll("table").length;

        const missingChartCount = page.expectedCharts - pageCharts.length;
        if (missingChartCount > 0) {
          failures.push(
            `${page.label} / ${persona.id} missing ${missingChartCount} chart integrity container(s)`,
          );
        }

        for (const tuple of pageMetrics) {
          if (!DEGENERATE_VALUE.test(tuple.value)) continue;
          if (isAllowedMetric(allowlist, tuple)) continue;
          failures.push(
            `${tuple.page} / ${tuple.persona} / ${tuple.label} rendered degenerate value "${tuple.value}"`,
          );
        }

        for (const tuple of pageCharts) {
          const numericValues = tuple.values.filter(Number.isFinite);
          const isDegenerate =
            numericValues.length === 0 || numericValues.every((value) => Math.abs(value) < 1e-9);
          if (!isDegenerate) continue;
          if (isAllowedChart(allowlist, tuple)) continue;
          failures.push(
            `${tuple.page} / ${tuple.persona} / ${tuple.chart} primary series ${tuple.primarySeries} is empty/all-zero`,
          );
        }

        for (const tuple of pageTableIssues) {
          if (isAllowedTableIssue(allowlist, tuple)) continue;
          failures.push(
            `${tuple.page} / ${tuple.persona} / ${tuple.table} has degenerate table data: ${tuple.issue}`,
          );
        }

        cleanup();
      }
    }

    expect(PERSONAS.length * PAGES.length).toBe(27);
    expect(metrics).toHaveLength(129);
    expect(charts).toHaveLength(27);
    expect(tablesChecked).toBeGreaterThan(0);
    expect(failures).toEqual([]);
  });

  it("does not render the former fabricated recurring ARR metric", () => {
    for (const persona of PERSONAS) {
      const { container } = renderPage(
        persona,
        "/bookings",
        <BookingsBridge />,
      );
      const labels = collectMetrics(container, "Bookings Bridge", persona.id).map(
        (metric) => metric.label,
      );
      expect(labels).not.toContain("YTD Recurring (~85%)");
      cleanup();
    }
  });

  it("suppresses Funnel Health stream tables when the snapshot lacks contracted data", () => {
    for (const persona of PERSONAS) {
      const { container } = renderPage(persona, "/funnel", <FunnelHealth />);
      const tableLabels = collectTableLabels(container);

      expect(tableLabels).not.toContain("Q1FY26 Conversion Rates by Stream");

      const sourceBreakdown = findTable(container, "Q1FY26 Source Stream Breakdown");
      expect(sourceBreakdown).not.toBeNull();
      expect(tableHeaders(sourceBreakdown!)).not.toContain("Actual Opps");
      expect(tableHeaders(sourceBreakdown!)).not.toContain("Actual Pipeline");
      expect(tableFirstColumn(sourceBreakdown!)).not.toContain("PLG");

      cleanup();
    }
  });

  it("shows known-correct Sapling headline numbers on every public page", () => {
    const sapling = PERSONAS.find((persona) => persona.id === "sapling-industries");
    expect(sapling).toBeDefined();

    for (const page of SAPLING_HEADLINE_ASSERTIONS) {
      const { container } = renderPage(sapling!, page.path, <page.Component />);
      expect(normalizeCell(container.textContent ?? ""), page.label).toContain(page.expectedText);
      cleanup();
    }
  });
});

function buildPersona(
  id: PersonaId,
  rawProfile: RawOrgProfile,
  rawPlan: RawPlanPreset,
  snapshot: Snapshot,
): PersonaFixture {
  return {
    id,
    profile: normalizeOrgProfile(rawProfile, {
      manifestId: id,
      profileUrl: `${DATA_ROOT}/profiles/${id}.json`,
      isDefault: id === "sapling-industries",
      dataRoot: DATA_ROOT,
    }),
    plan: normalizePlanPreset(rawPlan),
    snapshot,
  };
}

function renderPage(persona: PersonaFixture, route: string, element: ReactElement) {
  const context = buildContext(persona);
  return render(
    <MemoryRouter initialEntries={[route]}>
      <PlanningSessionProvider value={context}>{element}</PlanningSessionProvider>
    </MemoryRouter>,
  );
}

function buildContext(persona: PersonaFixture): PlanningSessionContextValue {
  const capacityWarnings =
    persona.snapshot.model_output.bookings_bridge.capacity_warnings ?? [];
  const healthStatusRaw =
    (persona.snapshot.health_status?.overall_status as string | undefined) ??
    (persona.snapshot.health_status?.status as string | undefined);

  return {
    snapshot: persona.snapshot,
    orgProfiles: PERSONAS.map((entry) => entry.profile),
    selectedOrgProfile: persona.profile,
    selectOrgProfile: () => {},
    plans: [persona.plan],
    selectedPlan: persona.plan,
    requestedPlanId: null,
    activeRenderedPlanId: persona.plan.id,
    planSelectionNotice: null,
    planCatalogDiagnostics: [],
    selectPlan: () => {},
    healthStatus: normalizeToplineHealthStatus(healthStatusRaw, capacityWarnings.length),
    snapshotMeta: {
      as_of: persona.snapshot.as_of,
      generated_at: persona.snapshot.generated_at,
      git_sha: persona.snapshot.git_sha,
    },
  };
}

function collectMetrics(
  container: HTMLElement,
  page: string,
  persona: PersonaId,
): MetricTuple[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>('[data-testid="metric-card"]'),
  ).map((node) => {
    const label =
      node.querySelector<HTMLElement>('[data-testid="metric-label"]')
        ?.textContent?.trim() ?? "";
    const value =
      node.querySelector<HTMLElement>('[data-testid="metric-value"]')
        ?.textContent?.trim() ?? "";
    return { page, persona, label, value };
  });
}

function collectCharts(
  container: HTMLElement,
  page: string,
  persona: PersonaId,
): ChartTuple[] {
  return Array.from(container.querySelectorAll<HTMLElement>('[data-testid="chart-container"]')).map(
    (node) => {
      const chart = node.dataset.chartTitle ?? "";
      const primarySeries = node.dataset.primarySeries ?? "";
      const values = parseSeriesValues(node.dataset.primaryValues ?? "[]");
      return { page, persona, chart, primarySeries, values };
    },
  );
}

function collectTableIssues(
  container: HTMLElement,
  page: string,
  persona: PersonaId,
): TableIssueTuple[] {
  return Array.from(container.querySelectorAll<HTMLTableElement>("table")).flatMap(
    (table, tableIndex) => {
      const label = resolveTableLabel(table, tableIndex);
      const rows = Array.from(table.querySelectorAll("tbody tr")).map((row) =>
        Array.from(row.querySelectorAll("td")).map((cell) => normalizeCell(cell.textContent ?? "")),
      );
      const nonEmptyRows = rows.filter((row) => row.some((cell) => cell.length > 0));
      if (nonEmptyRows.length === 0) return [];

      const issues: TableIssueTuple[] = [];
      const dataRows = nonEmptyRows.map((row) => row.slice(1));
      const flattenedDataCells = dataRows.flat();
      if (
        flattenedDataCells.length > 0 &&
        flattenedDataCells.every(isDegenerateTableCell)
      ) {
        issues.push({
          page,
          persona,
          table: label,
          issue: "all data cells are degenerate",
        });
      }

      const headers = Array.from(table.querySelectorAll("thead th")).map((cell) =>
        normalizeCell(cell.textContent ?? ""),
      );
      const columnCount = Math.max(...nonEmptyRows.map((row) => row.length));
      for (let columnIndex = 1; columnIndex < columnCount; columnIndex += 1) {
        const columnCells = nonEmptyRows
          .map((row) => row[columnIndex] ?? "")
          .filter((cell) => cell.length > 0);
        if (columnCells.length === 0) continue;
        if (!columnCells.every(isDegenerateTableCell)) continue;
        if (!columnCells.every(isNumericOrDegenerateTableCell)) continue;

        const siblingCells = nonEmptyRows.flatMap((row) =>
          row.filter((_, index) => index > 0 && index !== columnIndex),
        );
        const siblingHasCarriedData = siblingCells.some(
          (cell) => cell.length > 0 && !isDegenerateTableCell(cell),
        );
        if (!siblingHasCarriedData) continue;

        issues.push({
          page,
          persona,
          table: label,
          issue: `column "${headers[columnIndex] ?? `#${columnIndex + 1}`}" is entirely degenerate while sibling columns carry data`,
        });
      }

      return issues;
    },
  );
}

function collectTableLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll<HTMLTableElement>("table")).map(
    (table, index) => resolveTableLabel(table, index),
  );
}

function findTable(
  container: HTMLElement,
  label: string,
): HTMLTableElement | null {
  return (
    Array.from(container.querySelectorAll<HTMLTableElement>("table")).find(
      (table, index) => resolveTableLabel(table, index) === label,
    ) ?? null
  );
}

function tableHeaders(table: HTMLTableElement): string[] {
  return Array.from(table.querySelectorAll("thead th")).map((cell) =>
    normalizeCell(cell.textContent ?? ""),
  );
}

function tableFirstColumn(table: HTMLTableElement): string[] {
  return Array.from(table.querySelectorAll("tbody tr")).map((row) =>
    normalizeCell(row.querySelector("td")?.textContent ?? ""),
  );
}

function parseSeriesValues(raw: string): number[] {
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed)
      ? parsed.map((value) => (typeof value === "number" ? value : Number.NaN))
      : [];
  } catch {
    return [];
  }
}

function isAllowedMetric(allowlist: RenderAllowlist, tuple: MetricTuple): boolean {
  return allowlist.metrics.some(
    (entry) =>
      entry.page === tuple.page &&
      entry.persona === tuple.persona &&
      entry.label === tuple.label &&
      entry.value === tuple.value,
  );
}

function isAllowedChart(allowlist: RenderAllowlist, tuple: ChartTuple): boolean {
  return allowlist.charts.some(
    (entry) =>
      entry.page === tuple.page &&
      entry.persona === tuple.persona &&
      entry.chart === tuple.chart &&
      entry.primarySeries === tuple.primarySeries,
  );
}

function isAllowedTableIssue(
  allowlist: RenderAllowlist,
  tuple: TableIssueTuple,
): boolean {
  return allowlist.tables.some(
    (entry) =>
      entry.page === tuple.page &&
      (entry.persona === "*" || entry.persona === tuple.persona) &&
      entry.table === tuple.table &&
      entry.issue === tuple.issue,
  );
}

function normalizeCell(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function isDegenerateTableCell(value: string): boolean {
  return DEGENERATE_TABLE_CELL.test(value);
}

function isNumericOrDegenerateTableCell(value: string): boolean {
  return isDegenerateTableCell(value) || NUMERIC_TABLE_CELL.test(value);
}

function resolveTableLabel(table: HTMLTableElement, tableIndex: number): string {
  let current: HTMLElement | null = table.parentElement;
  while (current && current.tagName !== "BODY") {
    const heading = current.querySelector<HTMLElement>("h1, h2, h3, h4");
    const headingText = heading?.textContent?.trim();
    if (headingText) return headingText;
    current = current.parentElement;
  }
  return `table #${tableIndex + 1}`;
}
