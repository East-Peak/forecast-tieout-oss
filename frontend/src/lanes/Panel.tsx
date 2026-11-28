import { useEffect, useRef } from "react";
import { Bound } from "../binding/Bound";
import { BASIS, FRAME, HEAD, LANE } from "./bindings";
import type { CellSource } from "./bindings";
import { PARTS } from "./definitions";
import { Maybe } from "./Maybe";
import { RecordCount, Records } from "./Records";
import { TEXT, toneOf } from "./tone";
import type { BasisFile, Cell, ColumnKey, LanesFile, RecordsFile, Row } from "./types";
import type { Loaded } from "./useFile";

function Figure({ label, note, children }: { label: string; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="text-[11px] font-medium uppercase text-slate-500">{label}</p>
      <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">{children}</p>
      {note ? <div className="text-[11px] leading-tight text-slate-500">{note}</div> : null}
    </div>
  );
}

const WHICH = ["actual", "forecast", "goal"] as const;

/** A rate, a duration or a size with the two numbers it is made of, for the actual, the forecast and the goal where the file keeps them. */
function Parts({ source, column, cell, at }: { source: CellSource; column: ColumnKey; cell: Cell; at: string }) {
  const labels = PARTS[column];
  if (!labels || !cell.parts) return null;
  const own = LANE[source].cells[column].panel.parts;
  if (!own) return null;
  return (
    <section className="mt-5" data-testid="parts">
      <h4 className="text-xs font-semibold uppercase text-slate-500">What it is made of</h4>
      <dl className="mt-1.5 space-y-1 text-xs text-slate-700">
        {WHICH.map((which) => {
          const part = cell.parts?.[which];
          const bound = own[which];
          return part && bound ? (
            <div key={which} className="flex items-baseline justify-between gap-3">
              <dt className="capitalize text-slate-500">{which}</dt>
              <dd className="tabular-nums">
                <Bound binding={bound.numerator} row={`${at}/parts/${which}`} className="font-medium text-slate-900" /> {labels.top} over{" "}
                <Bound binding={bound.denominator} row={`${at}/parts/${which}`} className="font-medium text-slate-900" /> {labels.bottom}
              </dd>
            </div>
          ) : null;
        })}
      </dl>
    </section>
  );
}

/** Where a Won or Bookings figure comes from: pipeline carried in, and pipeline created in the period. What is modeled is labeled so and is never a deal. */
function Contributions({ source, column, cell, at }: { source: CellSource; column: ColumnKey; cell: Cell; at: string }) {
  const own = LANE[source].cells[column].panel.split;
  if (!cell.split || !own) return null;
  return (
    <section className="mt-5" data-testid="contributions">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Where it comes from</h4>
      <dl className="mt-1.5 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-xs text-slate-700">
        <dt className="col-span-2 mt-1 font-medium text-slate-800">Actual</dt>
        <dt>from pipeline carried in</dt>
        <dd className="text-right font-medium tabular-nums text-slate-900"><Bound binding={own.actualCarried} row={at} /></dd>
        <dt>from pipeline created in the period</dt>
        <dd className="text-right font-medium tabular-nums text-slate-900"><Bound binding={own.actualCreated} row={at} /></dd>
        <dt className="col-span-2 mt-2 font-medium text-slate-800">Forecast (modeled contributions, not deals)</dt>
        <dt>modeled, from pipeline carried in</dt>
        <dd className="text-right font-medium tabular-nums text-slate-900"><Bound binding={own.forecastCarried} row={at} /></dd>
        <dt>modeled, from pipeline created in the period</dt>
        <dd className="text-right font-medium tabular-nums text-slate-900"><Bound binding={own.forecastCreated} row={at} /></dd>
      </dl>
    </section>
  );
}

/** Where the goal comes from: the row's own allocation sentence, and for an owner the inputs of that allocation from the goal basis. */
function GoalSource({ source, row, rowPointer, basis }: { source: CellSource; row: Row; rowPointer: string; basis: Loaded<BasisFile> }) {
  const ownerId = row.kind === "owner" ? row.path[3] : null;
  const owner = ownerId !== null && basis.status === "ready" ? basis.doc.owners.find((o) => o.id === ownerId) : undefined;
  return (
    <section className="mt-5" data-testid="goal-source">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Where the goal comes from</h4>
      <p className="mt-1.5 text-xs leading-snug text-slate-700">
        <Bound binding={LANE[source].allocation} row={rowPointer} />
      </p>
      {ownerId !== null ? (
        owner ? (
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-xs text-slate-700">
            <dt className="text-slate-500">Annual quota</dt>
            <dd className="tabular-nums"><Bound binding={BASIS.ownerQuota} row={`/owners/{id=${ownerId}}`} /></dd>
            <dt className="text-slate-500">Days employed in the year</dt>
            <dd className="tabular-nums"><Bound binding={BASIS.ownerDays} row={`/owners/{id=${ownerId}}`} /></dd>
            <dt className="text-slate-500">Weight (quota times days)</dt>
            <dd className="tabular-nums"><Bound binding={BASIS.ownerWeight} row={`/owners/{id=${ownerId}}`} /></dd>
            <dt className="text-slate-500">Share of the segment</dt>
            <dd className="tabular-nums"><Bound binding={BASIS.ownerShare} row={`/owners/{id=${ownerId}}`} /></dd>
          </dl>
        ) : null
      ) : null}
      {owner ? (
        <p className="mt-2 text-[11px] leading-snug text-slate-500">
          <Bound binding={BASIS.ownerCaveat} />
        </p>
      ) : null}
    </section>
  );
}

interface Props {
  source: CellSource;
  lanes: LanesFile;
  basis: Loaded<BasisFile>;
  records: Loaded<RecordsFile>;
  row: Row;
  /** the pointer of the row in the file the cell is read from */
  rowPointer: string;
  periodIndex: number;
  column: ColumnKey;
  onClose: () => void;
}

/** The side panel of one cell: what it is, its three values and where they come from, and the deals behind the actual. */
export function CellPanel({ source, lanes, basis, records, row, rowPointer, periodIndex, column, onClose }: Props) {
  const cell = row.cells[column];
  const own = LANE[source].cells[column].panel;
  const at = `${rowPointer}/cells/${column}`;
  const period = lanes.periods[periodIndex];
  const tone = toneOf(cell.status);
  // an owner's rate has only what was recorded; the opening stock is one figure, so its forecast and goal are not repeated
  const actualOnly = (cell.forecast === null && cell.goal === null) || column === "open";
  const noGoal = cell.none_because === "no_goal";
  const reason = cell.status === "none" && cell.none_because !== null ? cell.none_because : null;
  const columnRow = `/columns/{key=${column}}`;
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    root.current?.focus();
  }, [column, rowPointer, periodIndex]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [onClose]);

  return (
    <aside
      ref={root}
      tabIndex={-1}
      role="complementary"
      aria-label="Cell details"
      data-testid="cell-panel"
      className="fixed inset-x-0 bottom-0 z-50 flex max-h-[55vh] flex-col rounded-t-xl border-t border-slate-200 bg-white shadow-[0_-4px_20px_rgba(15,23,42,0.12)] outline-none lg:inset-x-auto lg:right-0 lg:top-[var(--ft-header-height,0px)] lg:max-h-none lg:w-[420px] lg:rounded-none lg:border-l lg:border-t-0 lg:shadow-[-4px_0_20px_rgba(15,23,42,0.12)] xl:sticky xl:inset-auto xl:top-[var(--ft-header-height,0px)] xl:z-10 xl:max-h-[calc(100vh-var(--ft-header-height,0px)-16px)] xl:shrink-0 xl:rounded-ft xl:border xl:shadow-ft"
    >
      <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <div className="min-w-0">
          <h3 className="font-display text-lg font-semibold leading-tight text-ft-brand">
            <Bound binding={HEAD.panelTitle} row={columnRow} />{" "}
            <span className="text-xs font-normal uppercase text-slate-500"><Bound binding={HEAD.panelUnit} row={columnRow} /></span>
          </h3>
          <p className="mt-0.5 text-sm text-slate-700">
            <Bound binding={LANE[source].panelLabel} row={rowPointer} className="font-medium" /> <span className="text-slate-400">/</span>{" "}
            <Bound binding={FRAME.panelPeriodKey} row={`/periods/${periodIndex}`} />{" "}
            <span className="text-xs text-slate-500">(<Bound binding={FRAME.panelPeriodStanding} row={`/periods/${periodIndex}`} />)</span>
          </p>
          <p className="text-[11px] leading-snug text-slate-500">
            <Bound binding={FRAME.panelPeriodStart} row={`/periods/${periodIndex}`} /> to <Bound binding={FRAME.panelPeriodEnd} row={`/periods/${periodIndex}`} />; data as of <Bound binding={FRAME.panelAsOf} />
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close panel" className="rounded px-2 py-0.5 text-lg leading-none text-slate-500 hover:bg-slate-100">
          {"×"}
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-5 pb-6 pt-4">
        <div className="flex gap-4">
          <Figure label="Actual" note={column === "open" ? <Bound binding={HEAD.goalLabel} row={columnRow} /> : undefined}>
            <Bound binding={own.actual} row={at} />
          </Figure>
          {actualOnly ? null : (
            <>
              <Figure label="Forecast" note={column === "win_rate" ? "pooled rate" : undefined}>
                <Maybe binding={own.forecast} row={at} />
              </Figure>
              <Figure label="Goal" note={<Bound binding={HEAD.goalLabel} row={columnRow} />}>
                {noGoal ? "no goal" : <Maybe binding={own.goal} row={at} />}
              </Figure>
            </>
          )}
        </div>
        <div className="mt-2">
          <RecordCount records={records} path={row.path} periodKey={period.key} column={column} />
        </div>
        {cell.ratio !== null && cell.goal !== null ? (
          <p className="mt-2 text-xs text-slate-600">
            {cell.compared === "actual" ? "Actual rate against goal: " : "Forecast against goal: "}
            <Maybe binding={own.ratio} row={at} className={`font-semibold ${TEXT[tone]}`} />
          </p>
        ) : null}
        {reason ? (
          <p className="mt-2 text-xs leading-snug text-slate-600" data-testid="panel-reason">
            <Bound binding={LANE[source].panelReason} row={`/reasons/${reason}`} />
          </p>
        ) : null}
        {cell.goal_inside_range80 === true && cell.range80 && own.range ? (
          <p className="mt-2 text-xs leading-snug text-slate-700" data-testid="panel-range">
            The goal lies inside the 80% range of this forecast, <Bound binding={own.range.low} row={at} /> to <Bound binding={own.range.high} row={at} />. A wide range does not excuse a shortfall.
          </p>
        ) : null}
        <Parts source={source} column={column} cell={cell} at={at} />
        <Contributions source={source} column={column} cell={cell} at={at} />
        {actualOnly ? null : <GoalSource source={source} row={row} rowPointer={rowPointer} basis={basis} />}
        <section className="mt-5">
          <h4 className="text-xs font-semibold uppercase text-slate-500">What it means</h4>
          <p className="mt-1.5 text-xs leading-snug text-slate-700"><Bound binding={HEAD.definition} row={columnRow} /></p>
          <p className="mt-1.5 text-[11px] text-slate-500">
            Basis: <Bound binding={FRAME.panelBasisLabel} />
          </p>
        </section>
        {records.status === "ready" ? (
          <Records records={records.doc} lanes={lanes} path={row.path} periodKey={period.key} column={column} />
        ) : (
          <p className="mt-5 text-xs text-slate-500" data-testid="records" data-state={records.status}>
            {records.status === "error" ? "The records could not be loaded." : "Loading the records."}
          </p>
        )}
      </div>
    </aside>
  );
}
