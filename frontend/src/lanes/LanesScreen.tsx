import { useEffect, useMemo, useState } from "react";
import { formatValue } from "../lib/format";
import { GridCell } from "./Cell";
import { CellPanel } from "./CellPanel";
import { PlanBasis } from "./PlanBasis";
import { NO_VIEW, levelName, visibleRows } from "./rows";
import type { View, VisibleRow } from "./rows";
import type { LanesData, Row } from "./types";

const DATA_URL = "/prototype/lanes_ui.json";

interface Menu {
  row: Row;
  role: VisibleRow["role"];
  top: number;
  left: number;
}

/** "Q3FY26" is the quarter, "FY26" the fiscal year: the labels on the period selector. */
const periodLabel = (key: string) => (key.startsWith("Q") ? key.slice(0, 2) : "Fiscal year");

function Toolbar({
  data,
  periodKey,
  setPeriod,
  processing,
  setProcessing,
  view,
  rollUp,
  clear,
  hiddenCount,
  showHidden,
}: {
  data: LanesData;
  periodKey: string;
  setPeriod: (key: string) => void;
  processing: boolean;
  setProcessing: (on: boolean) => void;
  view: View;
  rollUp: () => void;
  clear: () => void;
  hiddenCount: number;
  showHidden: () => void;
}) {
  const rows = data.periods[periodKey].rows;
  const chips = levelName(rows, view);
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2" role="toolbar" aria-label="Grid controls">
      <div className="inline-flex rounded-ft border border-slate-200 bg-white p-0.5 shadow-ft" role="group" aria-label="Period">
        {Object.keys(data.periods).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={key === periodKey}
            onClick={() => setPeriod(key)}
            className={`rounded px-3 py-1 text-sm ${key === periodKey ? "bg-ft-accentSoft font-medium text-ft-brand" : "text-slate-600 hover:text-slate-900"}`}
          >
            {periodLabel(key)}
          </button>
        ))}
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" role="switch" checked={processing} onChange={(e) => setProcessing(e.target.checked)} className="peer sr-only" />
        <span aria-hidden="true" className="relative h-4 w-7 rounded-full bg-slate-300 transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-3 after:w-3 after:rounded-full after:bg-white after:transition-all peer-checked:bg-ft-accent peer-checked:after:left-3.5 peer-focus-visible:ring-2 peer-focus-visible:ring-ft-accent peer-focus-visible:ring-offset-1" />
        Processing metrics
      </label>
      <div className="flex flex-wrap items-center gap-1.5" aria-label="Drill path" role="group">
        <span className="text-[11px] font-semibold uppercase text-slate-500">Rows by</span>
        {chips.drilled.map((chip) => (
          <span key={chip.id} className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-50 py-0.5 pl-2.5 pr-1 text-xs text-slate-700" data-testid="chip">
            {chip.level}: {chip.label}
            <button type="button" aria-label={`Roll up ${chip.label}`} onClick={rollUp} className="flex h-4 w-4 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200">
              {"×"}
            </button>
          </span>
        ))}
        <span className="inline-flex items-center rounded-full border border-ft-accent/50 bg-ft-accentSoft px-2.5 py-0.5 text-xs font-medium text-ft-brand" data-testid="chip">
          {chips.trailing}
        </span>
      </div>
      <button type="button" onClick={clear} className="text-xs text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline">
        Clear
      </button>
      {hiddenCount > 0 ? (
        <button type="button" onClick={showHidden} className="text-xs text-slate-600 underline underline-offset-2 hover:text-slate-900" data-testid="hidden-link">
          {formatValue("count", hiddenCount)} hidden, show
        </button>
      ) : null}
    </div>
  );
}

function MenuItem({ children, disabled, onClick }: { children: string; disabled?: boolean; onClick: () => void }) {
  return (
    <button type="button" role="menuitem" disabled={disabled} onClick={onClick} className="block w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100 disabled:cursor-default disabled:text-slate-300 disabled:hover:bg-transparent">
      {children}
    </button>
  );
}

/** The grid itself, drawn from a prepared data file. */
export function LanesGrid({ data }: { data: LanesData }) {
  const periodKeys = Object.keys(data.periods);
  const [periodKey, setPeriodKey] = useState(periodKeys[0]);
  const [processing, setProcessing] = useState(true);
  const [view, setView] = useState<View>(NO_VIEW);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [selected, setSelected] = useState<{ rowId: string; column: string } | null>(null);

  const period = data.periods[periodKey];
  const columns = data.columns.filter((c) => processing || c.kind === "volume");
  const { shown, hiddenCount } = useMemo(() => visibleRows(period.rows, view), [period, view]);

  useEffect(() => {
    if (!menu) return undefined;
    const close = () => setMenu(null);
    const escape = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("click", close);
    document.addEventListener("keydown", escape);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  const toggle = (set: ReadonlySet<string>, id: string) => {
    const next = new Set(set);
    if (!next.delete(id)) next.add(id);
    return next;
  };
  const expand = (id: string) => setView((v) => ({ ...v, expanded: new Set(v.expanded).add(id) }));
  const rollUp = () => setView((v) => ({ ...v, path: v.path.slice(0, -1) }));
  const drill = (id: string) => setView((v) => ({ ...v, path: [id] }));
  const exclude = (id: string) => setView((v) => ({ ...v, hidden: new Set(v.hidden).add(id) }));
  const showHidden = () => setView((v) => ({ ...v, hidden: new Set() }));

  const selectedRow = selected ? period.rows.find((r) => r.id === selected.rowId) : undefined;
  const selectedColumn = selected ? data.columns.find((c) => c.key === selected.column) : undefined;

  const openMenu = (row: Row, role: VisibleRow["role"], button: HTMLElement) => {
    const rect = button.getBoundingClientRect();
    const cell = (button.parentElement ?? button).getBoundingClientRect();
    setMenu({ row, role, top: rect.bottom, left: cell.left });
  };

  return (
    <div className="space-y-3">
      <Toolbar
        data={data}
        periodKey={periodKey}
        setPeriod={setPeriodKey}
        processing={processing}
        setProcessing={setProcessing}
        view={view}
        rollUp={rollUp}
        clear={() => setView(NO_VIEW)}
        hiddenCount={hiddenCount}
        showHidden={showHidden}
      />
      <PlanBasis meta={data.meta} />
      <div className="max-h-[calc(100vh-250px)] min-h-[320px] overflow-auto rounded-ft border border-slate-200 bg-white shadow-ft" data-testid="grid-scroll">
        <table className="w-full border-separate border-spacing-0 text-left" data-testid="grid">
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 top-0 z-30 w-[168px] min-w-[168px] border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-semibold uppercase text-slate-500">
                {periodLabel(periodKey)}
              </th>
              {columns.map((c) => (
                <th key={c.key} scope="col" data-col={c.key} className="sticky top-0 z-20 min-w-[148px] border-b border-l border-slate-200 bg-slate-50 px-2.5 py-2 align-bottom">
                  <span className="block text-xs font-semibold text-slate-800">{c.title}</span>
                  <span className="block text-[10px] font-normal uppercase text-slate-500">{c.unit}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((v) => {
              const tint = v.role === "root" ? "bg-slate-50" : "bg-white";
              return (
                <tr key={v.row.id} data-testid={`row-${v.row.id}`} data-role={v.role} className="group/row">
                  <th scope="row" className={`sticky left-0 z-10 border-b border-r border-slate-200 px-3 py-2 text-left align-middle font-normal ${tint}`}>
                    <div className={`flex w-[142px] items-center gap-1.5 ${v.role === "owner" ? "pl-5" : ""}`}>
                      {v.expandable ? (
                        <button type="button" aria-expanded={v.open} aria-label={`${v.open ? "Collapse" : "Expand"} ${v.row.display_label}`} onClick={() => setView((s) => ({ ...s, expanded: toggle(s.expanded, v.row.id) }))} className="-ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-500 hover:bg-slate-100">
                          <svg viewBox="0 0 10 10" className={`h-2.5 w-2.5 ${v.open ? "rotate-90" : ""}`} fill="currentColor" aria-hidden="true">
                            <path d="M3 1.5 7.5 5 3 8.5z" />
                          </svg>
                        </button>
                      ) : null}
                      <span className="min-w-0 flex-1">
                        <span className={`block truncate text-sm ${v.role === "owner" ? "text-slate-700" : "font-semibold text-slate-900"}`}>{v.row.display_label}</span>
                        {v.row.allocation_note ? (
                          <span className="block text-[11px] leading-tight text-amber-700">
                            {v.row.allocation_note.startsWith("joined") ? "joined after the plan start" : v.row.allocation_note}
                          </span>
                        ) : v.row.sub_label ? (
                          <span className="block truncate text-[11px] leading-tight text-slate-500">{v.row.sub_label}</span>
                        ) : null}
                      </span>
                    </div>
                  </th>
                  {columns.map((c) => (
                    <td key={c.key} className={`border-b border-l border-slate-200 p-0 align-top ${tint}`}>
                      <GridCell
                        row={v.row}
                        column={c}
                        cell={v.row.cells[c.key]}
                        selected={selected?.rowId === v.row.id && selected.column === c.key}
                        onOpen={() => setSelected({ rowId: v.row.id, column: c.key })}
                        onMore={(button) => openMenu(v.row, v.role, button)}
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {menu ? (
        <div role="menu" aria-label={`Actions for ${menu.row.display_label}`} style={{ position: "fixed", top: menu.top, left: menu.left }} className="z-50 mt-1 w-40 rounded-ft border border-slate-200 bg-white py-1 shadow-lg" onClick={(e) => e.stopPropagation()}>
          <MenuItem
            disabled={menu.role !== "segment" || view.expanded.has(menu.row.id)}
            onClick={() => {
              expand(menu.row.id);
              setMenu(null);
            }}
          >
            Expand
          </MenuItem>
          <MenuItem
            disabled={menu.role !== "segment"}
            onClick={() => {
              drill(menu.row.id);
              setMenu(null);
            }}
          >
            Drill down
          </MenuItem>
          <MenuItem
            disabled={view.path.length === 0}
            onClick={() => {
              rollUp();
              setMenu(null);
            }}
          >
            Roll up
          </MenuItem>
          <MenuItem
            disabled={menu.role === "root"}
            onClick={() => {
              exclude(menu.row.id);
              setMenu(null);
            }}
          >
            Exclude
          </MenuItem>
        </div>
      ) : null}
      {selectedRow && selectedColumn ? (
        <CellPanel data={data} periodKey={periodKey} periodLabel={periodLabel(periodKey)} row={selectedRow} column={selectedColumn} onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}

/** The `/lanes` screen: loads the prepared file and draws the grid. */
export default function LanesScreen({ data: given }: { data?: LanesData }) {
  const [data, setData] = useState<LanesData | null>(given ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (given) return;
    let live = true;
    fetch(DATA_URL)
      .then((r) => (r.ok ? (r.json() as Promise<LanesData>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => live && setData(d))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : "could not load"));
    return () => {
      live = false;
    };
  }, [given]);

  return (
    <div className="space-y-3">
      <div className="rounded-ft border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900" role="note">
        Prototype: figures come from a scratch calculation, not yet from the app's verified reports.
      </div>
      <div className="flex items-baseline gap-3">
        <h2 className="font-display text-xl font-semibold text-ft-brand">Lanes</h2>
        <p className="text-sm text-slate-500">Where the year is weaker than plan: which link, which segment, which owner.</p>
      </div>
      <p className="rounded-ft border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 lg:hidden">The lanes prototype needs a larger screen (1024 pixels wide or more).</p>
      <div className="hidden lg:block">
        {error ? <p className="text-sm text-red-700" role="alert">The lanes file could not be loaded: {error}</p> : data ? <LanesGrid data={data} /> : <p className="text-sm text-slate-500">Loading the lanes.</p>}
      </div>
    </div>
  );
}
