import { useMemo, useState } from "react";
import { formatValue } from "../lib/format";
import { isMuted } from "./Cell";
import { DEFINITIONS } from "./definitions";
import { show } from "./show";
import type { Cell, Column, Deal, LanesData, Row, SplitBars } from "./types";

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="text-[11px] font-medium uppercase text-slate-500">{label}</p>
      <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">{value}</p>
      {note ? <p className="text-[11px] leading-tight text-slate-500">{note}</p> : null}
    </div>
  );
}

function SplitBar({ title, carried, created, bars }: { title: string; carried: string; created: string; bars: { carried_w: string; created_w: string } }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-700">{title}</p>
      <div className="mt-1 flex h-3 w-full overflow-hidden rounded-sm bg-slate-100" role="img" aria-label={`${title}: ${carried} carried in, ${created} created in the period`}>
        <div className="h-full bg-slate-500" style={{ width: bars.carried_w }} data-testid="split-carried" />
        <div className="h-full bg-ft-accent" style={{ width: bars.created_w }} data-testid="split-created" />
      </div>
      <dl className="mt-1.5 space-y-0.5 text-[11px] text-slate-600">
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-sm bg-slate-500" aria-hidden="true" />
            from pipeline carried in
          </dt>
          <dd className="font-medium tabular-nums text-slate-800">{carried}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-sm bg-ft-accent" aria-hidden="true" />
            from pipeline created in the period
          </dt>
          <dd className="font-medium tabular-nums text-slate-800">{created}</dd>
        </div>
      </dl>
    </div>
  );
}

function Split({ column, cell }: { column: Column; cell: Cell }) {
  const bars: SplitBars | null | undefined = cell.split_bars;
  if (!cell.split || !bars) return null;
  const f = (v: string) => show(column.key, v, true);
  const g = (v: string) => show(column.key, v);
  return (
    <section className="mt-5" data-testid="split">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Where it comes from</h4>
      <div className="mt-2 grid gap-3">
        <SplitBar title="Actual" bars={bars.actual} carried={f(cell.split.actual.carried_in)} created={f(cell.split.actual.created_in_period)} />
        <SplitBar title="Forecast" bars={bars.forecast} carried={g(cell.split.forecast.carried_in)} created={g(cell.split.forecast.created_in_period)} />
      </div>
    </section>
  );
}

function Notes({ row, column, cell }: { row: Row; column: Column; cell: Cell }) {
  const notes: string[] = [];
  if (isMuted(row, column)) notes.push("Owner rows show this as evidence only: the samples are too small to judge a person on it, so there is no color and no goal comparison.");
  if (row.level === "owner" && !row.allocated) notes.push(`This owner has no plan allocation (${row.allocation_note}), so there are no goals and no color.`);
  if (cell.thin) notes.push("Few observations: fewer than five wins closed in this period, so treat this figure as thin.");
  if (cell.sample) {
    notes.push(
      `Win rate sample: ${formatValue("count", cell.sample.actual)} deals created ${formatValue("date", cell.created_from)} to ${formatValue("date", cell.created_through)} (${formatValue("count", cell.evaluated_days)} days), ${formatValue("count", cell.sample.actual_wins)} of them won.`,
    );
    notes.push("Pooled: the forecast uses one rate for the whole company, not a rate fitted to this slice. The colored percent compares this slice's actual rate with the plan-start goal.");
  }
  if (cell.goal_inside_range80 && cell.range80) {
    notes.push(`The goal lies inside the 80% range for this forecast (${formatValue("usd-short", cell.range80[0])} to ${formatValue("usd-short", cell.range80[1])}). A wide range does not excuse a shortfall.`);
  }
  if (cell.actual === null && cell.null_reason) notes.push(cell.null_reason);
  if (notes.length === 0) return null;
  return (
    <section className="mt-5">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Sample and caveats</h4>
      <ul className="mt-1.5 space-y-1.5 text-xs leading-snug text-slate-700">
        {notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </section>
  );
}

function Records({ column, row, deals }: { column: Column; row: Row; deals: Record<string, Deal> }) {
  const ids = column.key === "created" ? row.records.created : row.records.won;
  const arrKey = column.key === "created" ? "first_recorded_arr" : "current_arr";
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return ids.map((id) => deals[id]).filter((d) => q === "" || [d.id, d.owner_name, d.stage, d.created, d.close ?? ""].some((v) => v.toLowerCase().includes(q)));
  }, [ids, deals, query]);
  const copy = async () => {
    const lines = [["id", "owner", "created", "close", "ARR", "stage"], ...shown.map((d) => [d.id, d.owner_name, d.created, d.close ?? "", d[arrKey], d.stage])];
    try {
      await navigator.clipboard.writeText(lines.map((l) => l.join("\t")).join("\n"));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <section className="mt-5" data-testid="records">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase text-slate-500">
          Records <span className="font-normal normal-case text-slate-500" data-testid="records-count">({formatValue("count", shown.length)}{query.trim() === "" ? "" : ` of ${formatValue("count", ids.length)}`})</span>
        </h4>
        <button type="button" onClick={copy} className="rounded-ft border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-700 hover:border-slate-300">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <input
        type="search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setCopied(false);
        }}
        placeholder="Search id, owner, stage"
        aria-label="Search records"
        className="mt-2 w-full rounded-ft border border-slate-200 bg-white px-2.5 py-1 text-xs outline-none focus:border-ft-accent focus:ring-2 focus:ring-ft-accentSoft"
      />
      <div className="mt-2 max-h-80 overflow-auto rounded-ft border border-slate-200">
        <table className="w-full text-left text-[11px] tabular-nums">
          <thead className="sticky top-0 bg-slate-50 text-slate-500">
            <tr>
              {["Id", "Owner", "Created", "Close", "ARR", "Stage"].map((h) => (
                <th key={h} scope="col" className="whitespace-nowrap px-2 py-1 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => (
              <tr key={d.id} className="border-t border-slate-100" data-testid="record-row">
                <td className="whitespace-nowrap px-2 py-1 text-slate-700">{d.id}</td>
                <td className="whitespace-nowrap px-2 py-1">{d.owner_name}</td>
                <td className="whitespace-nowrap px-2 py-1">{formatValue("date", d.created)}</td>
                <td className="whitespace-nowrap px-2 py-1">{d.close ? formatValue("date", d.close) : "—"}</td>
                <td className="whitespace-nowrap px-2 py-1 text-right">{formatValue("usd-short", d[arrKey])}</td>
                <td className="whitespace-nowrap px-2 py-1">{d.stage}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface Props {
  data: LanesData;
  periodKey: string;
  periodLabel: string;
  row: Row;
  column: Column;
  onClose: () => void;
}

/** The right-hand panel for one metric in one row: the three numbers, where Won and Bookings come from, what the column means, the records. */
export function CellPanel({ data, periodKey, periodLabel, row, column, onClose }: Props) {
  const cell = row.cells[column.key];
  const muted = isMuted(row, column);
  const noAllocation = row.level === "owner" && !row.allocated;
  const showGoal = cell.has_goal && !noAllocation && !muted;
  const period = data.periods[periodKey];
  return (
    <aside aria-label={`${column.title}, ${row.display_label}, ${periodLabel}`} data-testid="cell-panel" className="fixed bottom-0 right-0 top-0 z-50 flex w-[520px] max-w-full flex-col border-l border-slate-200 bg-white shadow-[-4px_0_16px_rgba(15,23,42,0.08)]">
      <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="min-w-0">
          <h3 className="font-display text-lg font-semibold leading-tight text-ft-brand">{column.title}</h3>
          <p className="mt-0.5 text-sm text-slate-600">
            {row.display_label}
            {row.sub_label ? <span className="text-slate-400"> {row.sub_label}</span> : null}
            <span className="text-slate-400"> / </span>
            {periodLabel}
          </p>
          <p className="text-[11px] text-slate-400">
            {formatValue("date", period.start_exclusive)} (exclusive) to {formatValue("date", period.end_inclusive)}; data as of {formatValue("date", data.meta.as_of)}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close panel" className="rounded px-2 py-0.5 text-lg leading-none text-slate-500 hover:bg-slate-100">
          {"×"}
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-5 pb-8 pt-4">
        <div className="flex gap-4">
          <Figure label="Actual" value={show(column.key, cell.actual, true)} />
          {muted ? null : <Figure label="Forecast" value={show(column.key, cell.forecast)} note={column.key === "win_rate" ? "pooled rate" : undefined} />}
          {muted ? null : showGoal ? (
            <Figure label="Goal" value={show(column.key, cell.goal)} note={cell.goal_label ?? column.goal_label} />
          ) : (
            <Figure label="Goal" value={"—"} note={noAllocation ? row.allocation_note ?? undefined : "no goal"} />
          )}
        </div>
        {showGoal && cell.pct_text ? (
          <p className="mt-2 text-xs text-slate-600">
            {column.key === "win_rate" ? "Actual rate against goal: " : "Forecast against goal: "}
            <span className={`font-semibold ${cell.color === "red" ? "text-red-600" : cell.color === "green" ? "text-green-700" : "text-slate-600"}`}>{cell.pct_text}</span>
          </p>
        ) : null}
        <Split column={column} cell={cell} />
        <section className="mt-5">
          <h4 className="text-xs font-semibold uppercase text-slate-500">What it means</h4>
          <p className="mt-1.5 text-xs leading-snug text-slate-700">{DEFINITIONS[column.key]}</p>
        </section>
        <Notes row={row} column={column} cell={cell} />
        {column.key === "created" || column.key === "won" ? (
          <Records key={`${row.id}-${column.key}-${periodKey}`} column={column} row={row} deals={data.deals} />
        ) : (
          <p className="mt-5 text-xs text-slate-500" data-testid="records-elsewhere">
            Records are listed under Created and Won.
          </p>
        )}
      </div>
    </aside>
  );
}
