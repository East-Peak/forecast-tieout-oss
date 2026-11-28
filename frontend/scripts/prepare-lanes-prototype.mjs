// Prepares the swimlane prototype's data file. The browser may do no arithmetic (src/__tests__/noArithmetic.test.ts),
// so every number a cell needs that the scratch calculation does not already give is worked out here and written
// beside the original fields: percent text from the ratio, bar positions as CSS percent strings, split bar widths,
// display labels and the reasons a figure is missing. The scratch file's own values are copied through untouched.
//
//   node scripts/prepare-lanes-prototype.mjs [path/to/lanes_ui.json]
//
// Writes public/prototype/lanes_ui.json.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRATCH =
  "/private/tmp/claude-501/-Users-tammypais/54753c67-503b-45bb-ba79-916036516f56/scratchpad/lanes-proto/proto/lanes_ui.json";
const source = process.argv[2] ?? SCRATCH;
const target = resolve(HERE, "../public/prototype/lanes_ui.json");

const raw = JSON.parse(readFileSync(source, "utf8"));

/** columns whose bar is "actual and forecast as a share of the goal" */
const SHARE_COLUMNS = new Set(["opening", "created", "created_arr", "won", "bookings"]);

const num = (s) => (s === null || s === undefined ? null : Number(s));
const clamp = (x) => Math.min(100, Math.max(0, x));
const css = (x) => `${(Math.round(clamp(x) * 10) / 10).toString()}%`;

/** ratio 0.896 -> "-10%"; a ratio of exactly one reads "0%" */
function pctText(ratio) {
  const r = num(ratio);
  if (r === null || !Number.isFinite(r)) return null;
  const pct = Math.round((r - 1) * 100);
  if (pct === 0) return "0%";
  return pct > 0 ? `+${pct}%` : `-${Math.abs(pct)}%`;
}

function splitBars(split, actualTotal, forecastTotal) {
  const scale = Math.max(num(actualTotal) ?? 0, num(forecastTotal) ?? 0);
  if (!split || scale <= 0) return null;
  const width = (v) => css((num(v) / scale) * 100);
  return {
    actual: { carried_w: width(split.actual.carried_in), created_w: width(split.actual.created_in_period) },
    forecast: { carried_w: width(split.forecast.carried_in), created_w: width(split.forecast.created_in_period) },
  };
}

const NULL_REASON = {
  win_rate: "Too few mature deals in this slice to show a trailing win rate.",
  cycle: "No wins closed in this period, so there is no cycle to average.",
  avg_won_arr: "No wins closed in this period, so there is no average won ARR.",
};

function prepareCell(key, cell) {
  const goal = num(cell.goal);
  const actual = num(cell.actual);
  const forecast = num(cell.forecast);
  const hasGoal = goal !== null && goal > 0;
  const out = { ...cell, pct_text: hasGoal ? pctText(cell.ratio) : null, has_goal: hasGoal };
  if (hasGoal && SHARE_COLUMNS.has(key)) {
    out.actual_share = actual === null ? null : css((actual / goal) * 100);
    out.forecast_share = forecast === null ? null : css((forecast / goal) * 100);
  } else if (hasGoal) {
    // rates, days and averages: the goal is the tick at the middle of the track; each figure sits where it is
    // relative to the goal, magnified so that 20% either side spans the track
    const around = (v) => (v === null ? null : css(50 + (v / goal - 1) * 250));
    out.goal_pos = "50%";
    out.actual_pos = around(actual);
    out.forecast_pos = around(forecast);
  }
  if (cell.split) out.split_bars = splitBars(cell.split, cell.actual, cell.forecast);
  if (actual === null && NULL_REASON[key]) out.null_reason = NULL_REASON[key];
  return out;
}

const SEGMENT_NAMES = { enterprise: "Enterprise", mid_market: "Mid-market", commercial: "Commercial" };

function prepareRow(row) {
  const cells = Object.fromEntries(Object.entries(row.cells).map(([k, c]) => [k, prepareCell(k, c)]));
  let display = row.label;
  let sub = null;
  if (row.level === "total") {
    display = "Total";
    sub = row.label;
  } else if (row.level === "segment") {
    display = SEGMENT_NAMES[row.label] ?? row.label;
  } else {
    const m = /^(.*) \[(.+)\]$/.exec(row.label);
    if (m) {
      display = m[1];
      sub = m[2];
    }
  }
  const unallocated = row.level === "owner" && row.allocation.startsWith("none");
  return {
    ...row,
    display_label: display,
    sub_label: sub,
    allocated: !unallocated,
    allocation_note: unallocated ? row.allocation.replace(/^none: /, "") : null,
    cells,
  };
}

const periods = Object.fromEntries(
  Object.entries(raw.periods).map(([k, p]) => [k, { ...p, rows: p.rows.map(prepareRow) }]),
);

// the schedule against the targets, with the sums the explanation quotes
const schedule = raw.meta.frozen_schedule;
const sumOf = (key) => schedule.reduce((s, q) => s + Number(q[key]), 0);
const meta = {
  ...raw.meta,
  plan_basis: {
    ...raw.meta.plan_basis,
    label_text: raw.meta.plan_basis.label.replace(/, \d{4}-\d{2}-\d{2}$/, ""),
  },
  schedule_totals: { bookings: String(sumOf("bookings")), target: String(sumOf("target")), surplus: String(sumOf("surplus")) },
};

// tie-outs: the records behind Created and Won are as many as the cells say
let problems = 0;
for (const [pk, p] of Object.entries(periods)) {
  for (const row of p.rows) {
    for (const [col, key] of [["created", "created"], ["won", "won"]]) {
      if (row.records[key].length !== num(row.cells[col].actual)) {
        problems += 1;
        console.error(`records mismatch ${pk} ${row.id} ${col}`);
      }
    }
  }
}
if (problems) process.exit(1);

mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, `${JSON.stringify({ ...raw, meta, periods })}\n`);
console.log(`wrote ${target}`);
