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

interface RenderAllowlist {
  metrics: Array<MetricTuple & { rationale: string }>;
  charts: Array<Omit<ChartTuple, "values"> & { rationale: string }>;
}

const DATA_ROOT = "http://localhost/data";
const DEGENERATE_VALUE = /^(\$0(?:\.0+)?[KMB]?|--|—|NaN|\$NaN|undefined|null|Infinity|\s*)$/i;

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
    ];

    expect(missingRationales).toEqual([]);
  });
});

describe("all public pages render non-degenerate metrics and non-empty charts", () => {
  it("covers every route for every public persona fixture", () => {
    const allowlist = allowlistJson as RenderAllowlist;
    const metrics: MetricTuple[] = [];
    const charts: ChartTuple[] = [];
    const failures: string[] = [];

    for (const persona of PERSONAS) {
      for (const page of PAGES) {
        const { container } = renderPage(persona, page.path, <page.Component />);
        const pageMetrics = collectMetrics(container, page.label, persona.id);
        const pageCharts = collectCharts(container, page.label, persona.id);
        metrics.push(...pageMetrics);
        charts.push(...pageCharts);

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

        cleanup();
      }
    }

    expect(PERSONAS.length * PAGES.length).toBe(27);
    expect(metrics).toHaveLength(129);
    expect(charts).toHaveLength(27);
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
