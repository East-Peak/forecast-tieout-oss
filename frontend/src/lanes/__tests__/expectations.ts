/**
 * Test-only. What the grid, its panel and its records must show, written separately from the components: each
 * expected text comes from the file's own value through the independent formatters (screens/__tests__/independent.ts),
 * and the rules for what is drawn (an owner's rate shows its actual only; a gap reads "unavailable"; no goal reads
 * "no goal") are stated here again from the swimlane spec, not read from the code.
 */
import type { Absent, Expectation } from "../../binding/__tests__/harness";
import * as fmt from "../../screens/__tests__/independent";
import { COLUMNS, STRIP_COLUMNS } from "../bindings";
import type { BasisFile, Cell, ColumnKey, LanesFile, OwnersFile, RecordsFile, Row } from "../types";
import { basisOf, lanesOf, ownersOf, recordsOf } from "./disk";

const ACTUAL: Record<ColumnKey, (raw: string) => string> = {
  open: fmt.whole,
  created: fmt.whole,
  created_arr: fmt.usdShort,
  win_rate: fmt.percent1,
  cycle: fmt.days,
  won: fmt.whole,
  avg_won_arr: fmt.usdShort,
  bookings: fmt.usdShort,
};
const PLANNED: Record<ColumnKey, (raw: string) => string> = { ...ACTUAL, won: fmt.decimal1 };

export interface State {
  company: string;
  scenario: string;
  period: number;
  /** segments opened to their owners, in the order the file lists them */
  expanded: readonly string[];
  /** the cell whose panel is open: the row (its path in the file, joined by "/") and the column */
  panel?: { row: string; column: ColumnKey; records?: boolean };
  /** the disclosure of how the goals are made is open */
  basisOpen?: boolean;
}

export interface Files {
  lanes: LanesFile;
  owners: Record<string, OwnersFile>;
  basis: BasisFile;
  records: RecordsFile;
}

/** The segments of a lanes file, in its order. */
export const segmentSlugs = (lanes: LanesFile): string[] => lanes.periods[0].rows.flatMap((r) => (r.kind === "segment" ? [r.path[1]!] : []));

const cache = new Map<string, Files>();

/** A company's scenario as the files hold it (read once: the files do not change while the tests run). */
export function filesOf(company: string, scenario: string): Files {
  const key = `${company}/${scenario}`;
  let files = cache.get(key);
  if (!files) {
    const lanes = lanesOf(company, scenario);
    files = { lanes, owners: Object.fromEntries(segmentSlugs(lanes).map((s) => [s, ownersOf(company, scenario, s)])), basis: basisOf(company), records: recordsOf(company) };
    cache.set(key, files);
  }
  return files;
}

class Collector {
  private byId = new Map<string, { texts: string[]; rows: string[] }>();
  add(id: string, text: string, row = ""): void {
    const entry = this.byId.get(id) ?? { texts: [], rows: [] };
    entry.texts.push(text);
    entry.rows.push(row);
    this.byId.set(id, entry);
  }
  get expectations(): Expectation[] {
    return [...this.byId].map(([id, { texts, rows }]) => ({ id, texts, rows }));
  }
}

/** An actual-only cell: an owner's rate, cycle or average size, which has no forecast and no goal to compare. */
const actualOnly = (cell: Cell) => cell.forecast === null && cell.goal === null;

const shownActual = (column: ColumnKey, cell: Cell) => (cell.actual === null ? "unavailable" : ACTUAL[column](cell.actual));
const shownForecast = (column: ColumnKey, cell: Cell) => (cell.forecast === null ? "unavailable" : PLANNED[column](cell.forecast));
const shownGoal = (column: ColumnKey, cell: Cell) => (cell.goal === null ? "no goal" : PLANNED[column](cell.goal));

interface RowRef {
  source: "lanes" | "owners";
  /** the period's index in the file the row is read from */
  period: number;
  index: number;
  row: Row;
  slug?: string;
}

/** The rows on the page, top to bottom: the total, then each segment with its owners under it when it is open. */
export function displayedRows(f: Files, state: State): RowRef[] {
  const key = f.lanes.periods[state.period].key;
  const out: RowRef[] = [];
  f.lanes.periods[state.period].rows.forEach((row, index) => {
    out.push({ source: "lanes", period: state.period, index, row });
    const slug = row.path[1];
    if (row.kind === "segment" && slug !== undefined && state.expanded.includes(slug)) {
      const owners = f.owners[slug];
      const p = owners.periods.findIndex((x) => x.key === key);
      owners.periods[p].rows.forEach((o, i) => out.push({ source: "owners", period: p, index: i, row: o, slug }));
    }
  });
  return out;
}

const rowPointer = (r: RowRef) => `/periods/${r.period}/rows/${r.index}`;
export const idOf = (r: RowRef) => r.row.path.join("/");

/** `panelOnly`: only what the open panel adds (the sweep that names every binding builds the grid once, then each panel). */
export function build(f: Files, state: State, options: { panelOnly?: boolean } = {}): { expected: Expectation[]; absent: Absent[] } {
  const c = new Collector();
  const lanes = f.lanes;
  const period = lanes.periods[state.period];

  const rows = displayedRows(f, state);
  if (!options.panelOnly) {
    // the frame
    c.add("lanes.plan-basis.label", lanes.plan_basis.label);
    c.add("lanes.as-of", fmt.date(lanes.as_of));
    lanes.periods.forEach((p, i) => c.add("lanes.period.key", p.key, `/periods/${i}`));
    c.add("lanes.period.start", fmt.date(period.start), `/periods/${state.period}`);
    c.add("lanes.period.end", fmt.date(period.end), `/periods/${state.period}`);
    c.add("lanes.period.standing", period.standing, `/periods/${state.period}`);
    if (state.basisOpen) {
      lanes.caveats.forEach((text, i) => c.add(["lanes.caveat.benchmarks", "lanes.caveat.win-rate", "lanes.caveat.pooled"][i], text));
      f.basis.schedule.forEach((q, i) => {
        c.add("basis.schedule.quarter", q.quarter, `/schedule/${i}`);
        c.add("basis.schedule.bookings", fmt.usdShort(q.bookings), `/schedule/${i}`);
        c.add("basis.schedule.target", fmt.usdShort(q.target), `/schedule/${i}`);
      });
    }

    // the head: eight columns, in the file's order
    for (const column of lanes.columns) {
      c.add("lanes.column.title", column.title, `/columns/{key=${column.key}}`);
      c.add("lanes.column.unit", column.unit, `/columns/{key=${column.key}}`);
    }

    // the rows
    for (const r of rows) {
      const base = rowPointer(r);
      c.add(`${r.source}.row.label`, r.row.label, base);
      for (const column of COLUMNS) {
        const cell = r.row.cells[column];
        const at = `${base}/cells/${column}`;
        const p = (name: string) => `${r.source}.${column}.${name}`;
        c.add(p("actual"), shownActual(column, cell), at);
        if (!actualOnly(cell)) {
          c.add(p("forecast"), shownForecast(column, cell), at);
          // a goal of zero is said "no goal" in words, not shown as a zero figure
          if (cell.none_because !== "no_goal") c.add(p("goal"), shownGoal(column, cell), at);
        }
        if (cell.ratio !== null && cell.goal !== null) c.add(p("ratio"), fmt.percent1(cell.ratio), at);
        if (cell.status === "none" && cell.none_because !== null) {
          const reasons = r.source === "lanes" ? lanes.reasons : f.owners[r.slug!].reasons;
          c.add(`${r.source}.reason`, reasons[cell.none_because as keyof typeof reasons], `/reasons/${cell.none_because}`);
        }
        if (cell.goal_inside_range80 === true && cell.range80) {
          c.add(p("range.low"), fmt.usdShort(cell.range80[0]), at);
          c.add(p("range.high"), fmt.usdShort(cell.range80[1]), at);
        }
      }
    }
  }

  if (state.panel) panel(c, f, state, rows);
  return { expected: c.expectations, absent: [] };
}

/** The sets of deals behind a column's actual, as the records file's `sets` name them, and the groups the panel lists. */
const GROUPS: Record<ColumnKey, Array<{ set: string }>> = {
  open: [{ set: "open" }],
  created: [{ set: "created" }],
  created_arr: [{ set: "created" }],
  win_rate: [{ set: "cohort" }],
  cycle: [{ set: "won_carried_in" }, { set: "won_created_in_period" }],
  won: [{ set: "won_carried_in" }, { set: "won_created_in_period" }],
  avg_won_arr: [{ set: "won_carried_in" }, { set: "won_created_in_period" }],
  bookings: [{ set: "won_carried_in" }, { set: "won_created_in_period" }],
};

function panel(c: Collector, f: Files, state: State, rows: RowRef[]): void {
  const target = state.panel!;
  const r = rows.find((x) => idOf(x) === target.row)!;
  const column = target.column;
  const cell = r.row.cells[column];
  const base = rowPointer(r);
  const at = `${base}/cells/${column}`;
  const period = f.lanes.periods[state.period];
  const p = (name: string) => `${r.source}.${column}.panel.${name}`;
  const head = f.lanes.columns.find((x) => x.key === column)!;

  c.add("lanes.panel.column.title", head.title, `/columns/{key=${column}}`);
  c.add("lanes.panel.column.unit", head.unit, `/columns/{key=${column}}`);
  if (!actualOnly(cell)) c.add("lanes.panel.column.goal-label", head.goal_label, `/columns/{key=${column}}`);
  c.add(`${r.source}.panel.row.label`, r.row.label, base);
  c.add("lanes.panel.period.key", period.key, `/periods/${state.period}`);
  c.add("lanes.panel.period.start", fmt.date(period.start), `/periods/${state.period}`);
  c.add("lanes.panel.period.end", fmt.date(period.end), `/periods/${state.period}`);
  c.add("lanes.panel.period.standing", period.standing, `/periods/${state.period}`);
  c.add("lanes.panel.as-of", fmt.date(f.lanes.as_of));
  c.add("lanes.panel.plan-basis.label", f.lanes.plan_basis.label);

  c.add(p("actual"), shownActual(column, cell), at);
  if (!actualOnly(cell)) {
    c.add(p("forecast"), shownForecast(column, cell), at);
    if (cell.none_because !== "no_goal") c.add(p("goal"), shownGoal(column, cell), at);
  }
  if (cell.ratio !== null && cell.goal !== null) c.add(p("ratio"), fmt.percent1(cell.ratio), at);
  if (cell.status === "none" && cell.none_because !== null) {
    const reasons = r.source === "lanes" ? f.lanes.reasons : f.owners[r.slug!].reasons;
    c.add(`${r.source}.panel.reason`, reasons[cell.none_because as keyof typeof reasons], `/reasons/${cell.none_because}`);
  }
  if (STRIP_COLUMNS.includes(column) && cell.parts) {
    const numerator = column === "avg_won_arr" ? fmt.usdShort : fmt.whole;
    for (const which of ["actual", "forecast", "goal"] as const) {
      const part = cell.parts[which];
      if (!part) continue;
      c.add(p(`${which}.numerator`), numerator(part.numerator), `${at}/parts/${which}`);
      c.add(p(`${which}.denominator`), column === "win_rate" || which === "actual" ? fmt.whole(part.denominator) : fmt.decimal1(part.denominator), `${at}/parts/${which}`);
    }
  }
  if (cell.split) {
    c.add(p("split.actual.carried"), ACTUAL[column](cell.split.actual.carried_in), at);
    c.add(p("split.actual.created"), ACTUAL[column](cell.split.actual.created_in_period), at);
    c.add(p("split.forecast.carried"), PLANNED[column](cell.split.forecast.carried_in), at);
    c.add(p("split.forecast.created"), PLANNED[column](cell.split.forecast.created_in_period), at);
  }
  if (cell.goal_inside_range80 === true && cell.range80) {
    c.add(p("range.low"), fmt.usdShort(cell.range80[0]), at);
    c.add(p("range.high"), fmt.usdShort(cell.range80[1]), at);
  }
  if (!actualOnly(cell)) c.add(`${r.source}.panel.row.allocation`, r.row.allocation, base);
  if (r.row.kind === "owner" && !actualOnly(cell)) {
    const owner = f.basis.owners.find((o) => o.id === r.row.path[3]);
    if (owner) {
      const own = `/owners/{id=${owner.id}}`;
      c.add("basis.owner.quota", owner.quota === null ? "no quota" : fmt.usdFull(owner.quota), own);
      c.add("basis.owner.days", fmt.whole(String(owner.days)), own);
      c.add("basis.owner.weight", fmt.usdFull(owner.weight), own);
      c.add("basis.owner.share", fmt.percent1(owner.share), own);
      c.add("basis.owner.caveat", f.basis.owner_caveat);
    }
  }
  if (target.records) records(c, f, state, r, column);
}

function records(c: Collector, f: Files, state: State, r: RowRef, column: ColumnKey): void {
  const period = f.lanes.periods[state.period];
  const ri = f.records.rows.findIndex((x) => x.path.join("/") === (r.row.path as string[]).join("/"));
  if (ri < 0) return; // planned hires and programs hold no deals of their own: the panel says no records are listed
  const sets = f.records.rows[ri].periods[period.key]!;
  const segmentLabels = new Map(f.lanes.periods[0].rows.filter((x) => x.kind === "segment").map((x) => [x.path[1], x.label] as const));
  const listed = GROUPS[column].flatMap(({ set }) => {
    const ids = sets[set as keyof typeof sets];
    return ids ? [{ set, ids }] : [];
  });
  if (listed.length > 0) c.add("record.caveat", f.records.caveat);
  // the count beside the actual comes first, group by group; the tables follow
  for (const { set, ids } of listed) c.add("record.count", fmt.count(ids.length), `/rows/${ri}/periods/${period.key}/${set}`);
  for (const { ids } of listed) {
    for (const id of ids) {
      const d = f.records.records[id]!;
      const row = `/records/${id}`;
      c.add("record.id", d.id, row);
      c.add("record.name", d.name, row);
      const segmentIndex = f.lanes.periods[0].rows.findIndex((x) => x.kind === "segment" && x.path[1] === d.segment);
      if (segmentLabels.has(d.segment)) c.add("record.segment-label", segmentLabels.get(d.segment)!, `/periods/0/rows/${segmentIndex}`);
      else c.add("record.segment", d.segment, row);
      c.add("record.owner", d.owner_name, row);
      c.add("record.created", fmt.date(d.created), row);
      c.add("record.close", d.close === null ? "no date" : fmt.date(d.close), row);
      c.add("record.status", d.status, row);
      const first = column === "created" || column === "created_arr";
      const money = first ? d.arr_first : d.arr;
      c.add(first ? "record.arr-first" : "record.arr", money === null ? "unavailable" : fmt.usdShort(money), row);
    }
  }
}
