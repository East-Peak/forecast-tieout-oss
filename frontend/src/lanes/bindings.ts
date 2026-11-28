import { bind } from "../binding/Bound";
import type { Binding } from "../binding/Bound";
import type { FormatName } from "../lib/format";
import type { ColumnKey } from "./types";

/**
 * The swimlane grid's committed binding list: every figure and sentence of the grid, its cell panel and its records,
 * with the file, pointer, unit and format it is read through. The grid's cells are read from a row of a period of the
 * lanes file ("lanes": total and segments) or of a segment's owners file ("owners"); the row's own pointer is given
 * where a cell is drawn. The browser formats and draws; it adds, sorts and ranks nothing.
 * The tests assert this list against independently written expectations.
 */
export const COLUMNS: readonly ColumnKey[] = ["open", "created", "created_arr", "win_rate", "cycle", "won", "avg_won_arr", "bookings"];

/** The three columns that compare rates, durations and sizes: a strip of three points, not a bar from zero. */
export const STRIP_COLUMNS: readonly ColumnKey[] = ["win_rate", "cycle", "avg_won_arr"];

export type CellSource = "lanes" | "owners";

/** How each column's actual reads; the forecast and the goal differ only for wins, whose model counts are fractions of a deal. */
const ACTUAL_FORMAT: Record<ColumnKey, FormatName> = {
  open: "whole",
  created: "whole",
  created_arr: "usd-short",
  win_rate: "percent1",
  cycle: "days",
  won: "whole",
  avg_won_arr: "usd-short",
  bookings: "usd-short",
};
const PLANNED_FORMAT: Record<ColumnKey, FormatName> = { ...ACTUAL_FORMAT, won: "decimal1" };

type Unit = Parameters<typeof bind>[0]["unit"];
const UNITS: Partial<Record<FormatName, Unit>> = {
  "usd-short": "usd",
  "usd-full": "usd",
  percent1: "fraction",
  whole: "count",
  decimal1: "quantity",
  days: "days",
};
const unitOf = (format: FormatName): Unit => UNITS[format]!;

const text = (id: string, source: Binding["source"], path: string, extra: Partial<Binding> = {}) => bind({ id, source, path, unit: "text", format: "text", ...extra });
const date = (id: string, source: Binding["source"], path: string, extra: Partial<Binding> = {}) => bind({ id, source, path, unit: "date", format: "date", ...extra });
const figure = (id: string, source: Binding["source"], path: string, format: FormatName, extra: Partial<Binding> = {}) =>
  bind({ id, source, path, unit: unitOf(format), format, ...extra });

const UNAVAILABLE = { words: "unavailable" } as const;
const NO_GOAL = { words: "no goal" } as const;

type Which = "actual" | "forecast" | "goal";

/** The two numbers a rate, a duration or a size is made of, read from `{cell}/parts/{which}`. */
function part(source: CellSource, col: ColumnKey, which: Which) {
  const numerator: Partial<Record<ColumnKey, FormatName>> = { win_rate: "whole", cycle: "whole", avg_won_arr: "usd-short" };
  const denominator: FormatName = col === "win_rate" || which === "actual" ? "whole" : "decimal1";
  return {
    numerator: figure(`${source}.${col}.panel.${which}.numerator`, source, "/numerator", numerator[col] ?? "whole"),
    denominator: figure(`${source}.${col}.panel.${which}.denominator`, source, "/denominator", denominator),
  };
}

/** The columns whose cells carry a percent against the goal, by file: a lane's open stock is never compared, and an owner is judged on volumes alone. */
const VOLUMES: readonly ColumnKey[] = ["created", "created_arr", "won", "bookings"];

/**
 * One column of one row, read from `{row}/cells/{column}` of the lanes or the owners file: the cell, and what its panel adds.
 * A binding is on the list only where the file can hold the figure: an owner's rate has no forecast, goal or percent, only a
 * lane's rate has its three parts, only wins and bookings split into carried-in and created, only the total's bookings has a range.
 */
function column(source: CellSource, col: ColumnKey) {
  const id = (name: string) => `${source}.${col}.${name}`;
  const a = ACTUAL_FORMAT[col];
  const f = PLANNED_FORMAT[col];
  const lane = source === "lanes";
  const planned = lane || !STRIP_COLUMNS.includes(col);
  const compared = lane ? col !== "open" : VOLUMES.includes(col);
  const strip = STRIP_COLUMNS.includes(col);
  const partsOf: Which[] = !strip ? [] : lane && col !== "win_rate" ? ["actual", "forecast", "goal"] : ["actual"];
  const splits = col === "won" || col === "bookings";
  const ranged = lane && col === "bookings";
  return {
    actual: figure(id("actual"), source, "/actual", a, { unavailable: UNAVAILABLE }),
    forecast: planned ? figure(id("forecast"), source, "/forecast", f, { unavailable: UNAVAILABLE }) : undefined,
    goal: planned ? figure(id("goal"), source, "/goal", f, { unavailable: NO_GOAL }) : undefined,
    ratio: compared ? figure(id("ratio"), source, "/ratio", "percent1") : undefined,
    range: ranged ? { low: figure(id("range.low"), source, "/range80/0", "usd-short"), high: figure(id("range.high"), source, "/range80/1", "usd-short") } : undefined,
    panel: {
      actual: figure(id("panel.actual"), source, "/actual", a, { unavailable: UNAVAILABLE }),
      forecast: planned ? figure(id("panel.forecast"), source, "/forecast", f, { unavailable: UNAVAILABLE }) : undefined,
      goal: planned ? figure(id("panel.goal"), source, "/goal", f, { unavailable: NO_GOAL }) : undefined,
      ratio: compared ? figure(id("panel.ratio"), source, "/ratio", "percent1") : undefined,
      parts: strip ? Object.fromEntries(partsOf.map((w) => [w, part(source, col, w)])) as Partial<Record<Which, ReturnType<typeof part>>> : undefined,
      split: splits
        ? {
            actualCarried: figure(id("panel.split.actual.carried"), source, "/split/actual/carried_in", a),
            actualCreated: figure(id("panel.split.actual.created"), source, "/split/actual/created_in_period", a),
            forecastCarried: figure(id("panel.split.forecast.carried"), source, "/split/forecast/carried_in", f),
            forecastCreated: figure(id("panel.split.forecast.created"), source, "/split/forecast/created_in_period", f),
          }
        : undefined,
      range: ranged ? { low: figure(id("panel.range.low"), source, "/range80/0", "usd-short"), high: figure(id("panel.range.high"), source, "/range80/1", "usd-short") } : undefined,
    },
  };
}

function forSource(source: CellSource) {
  const cells = Object.fromEntries(COLUMNS.map((c) => [c, column(source, c)])) as Record<ColumnKey, ReturnType<typeof column>>;
  return {
    cells,
    /** a row's own name and allocation, read from `/periods/{p}/rows/{r}` */
    label: text(`${source}.row.label`, source, "/label"),
    panelLabel: text(`${source}.panel.row.label`, source, "/label"),
    allocation: text(`${source}.panel.row.allocation`, source, "/allocation"),
    /** why a cell has no color: the file's own sentence, read at `/reasons/{code}` */
    reason: text(`${source}.reason`, source, ""),
    panelReason: text(`${source}.panel.reason`, source, ""),
  };
}

export const LANE = { lanes: forSource("lanes"), owners: forSource("owners") } as const;

/** The grid's frame, read from the lanes file; a period's own fields are read from `/periods/{p}`. */
export const FRAME = {
  basisLabel: text("lanes.plan-basis.label", "lanes", "/plan_basis/label"),
  asOf: date("lanes.as-of", "lanes", "/as_of"),
  caveatBenchmarks: text("lanes.caveat.benchmarks", "lanes", "/caveats/0"),
  caveatWinRate: text("lanes.caveat.win-rate", "lanes", "/caveats/1"),
  caveatPooled: text("lanes.caveat.pooled", "lanes", "/caveats/2"),
  unavailable: text("lanes.unavailable", "lanes", "/unavailable"),
  periodKey: text("lanes.period.key", "lanes", "/key"),
  periodStart: date("lanes.period.start", "lanes", "/start"),
  periodEnd: date("lanes.period.end", "lanes", "/end"),
  periodStanding: text("lanes.period.standing", "lanes", "/standing"),
  panelPeriodKey: text("lanes.panel.period.key", "lanes", "/key"),
  panelPeriodStart: date("lanes.panel.period.start", "lanes", "/start"),
  panelPeriodEnd: date("lanes.panel.period.end", "lanes", "/end"),
  panelPeriodStanding: text("lanes.panel.period.standing", "lanes", "/standing"),
  panelAsOf: date("lanes.panel.as-of", "lanes", "/as_of"),
  panelBasisLabel: text("lanes.panel.plan-basis.label", "lanes", "/plan_basis/label"),
} as const;

/** A column's head, read from `/columns/{key=…}`; the panel's copy names the goal as well. */
export const HEAD = {
  title: text("lanes.column.title", "lanes", "/title"),
  unit: text("lanes.column.unit", "lanes", "/unit"),
  panelTitle: text("lanes.panel.column.title", "lanes", "/title"),
  panelUnit: text("lanes.panel.column.unit", "lanes", "/unit"),
  goalLabel: text("lanes.panel.column.goal-label", "lanes", "/goal_label"),
} as const;

/** The goal basis (`lanes-basis.json`): the frozen schedule's bookings beside the targets, and each owner's allocation inputs. */
export const BASIS = {
  /** a quarter of the schedule, read from `/schedule/{i}` */
  scheduleQuarter: text("basis.schedule.quarter", "basis", "/quarter"),
  scheduleBookings: figure("basis.schedule.bookings", "basis", "/bookings", "usd-short"),
  scheduleTarget: figure("basis.schedule.target", "basis", "/target", "usd-short"),
  /** an owner, read from `/owners/{id=…}` */
  ownerQuota: figure("basis.owner.quota", "basis", "/quota", "usd-full", { unavailable: { words: "no quota" } }),
  ownerDays: figure("basis.owner.days", "basis", "/days", "whole"),
  ownerWeight: figure("basis.owner.weight", "basis", "/weight", "usd-full"),
  ownerShare: figure("basis.owner.share", "basis", "/share", "percent1"),
  ownerCaveat: text("basis.owner.caveat", "basis", "/owner_caveat"),
} as const;

/** A deal (`lanes-records.json`), read from `/records/{id}`; and the lists of ids the cells name, counted where they stand. */
export const DEAL = {
  id: text("record.id", "records", "/id"),
  name: text("record.name", "records", "/name"),
  segment: text("record.segment", "records", "/segment"),
  segmentLabel: text("record.segment-label", "lanes", "/label"),
  owner: text("record.owner", "records", "/owner_name"),
  created: date("record.created", "records", "/created"),
  close: date("record.close", "records", "/close", { unavailable: { words: "no date" } }),
  status: text("record.status", "records", "/status"),
  arr: figure("record.arr", "records", "/arr", "usd-short", { unavailable: UNAVAILABLE }),
  arrFirst: figure("record.arr-first", "records", "/arr_first", "usd-short", { unavailable: UNAVAILABLE }),
  /** how many deals a list names, read from the list itself */
  count: bind({ id: "record.count", source: "records", path: "", unit: "count", format: "count", of: "length" }),
  caveat: text("record.caveat", "records", "/caveat"),
} as const;

function everyBinding(): Binding[] {
  const flat = (o: Record<string, unknown>): Binding[] =>
    Object.values(o).flatMap((v) =>
      v && typeof v === "object" && "id" in v && "unit" in v ? [v as Binding] : v && typeof v === "object" ? flat(v as Record<string, unknown>) : [],
    );
  return [...flat(LANE), ...flat(FRAME), ...flat(HEAD), ...flat(BASIS), ...flat(DEAL)];
}

export const LANES_BINDINGS: readonly Binding[] = everyBinding();
