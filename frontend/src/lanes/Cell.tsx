import { useId } from "react";
import { Bound } from "../binding/Bound";
import { pointScale } from "../binding/chartData";
import { LANE, STRIP_COLUMNS } from "./bindings";
import type { CellSource } from "./bindings";
import { Maybe } from "./Maybe";
import { GaugeIcon, TargetIcon } from "./icons";
import { LIGHT, MARK_FILL, MARK_RING, SOLID, TEXT, toneOf } from "./tone";
import type { Tone } from "./tone";
import type { Cell as CellData, ColumnKey } from "./types";

/** Solid to the actual, lighter to the forecast, on a track that ends at the goal: the browser's own progress element lays out the file's figures. */
function Bar({ cell, tone }: { cell: CellData; tone: Tone }) {
  const layer = "absolute inset-0 block h-full w-full appearance-none border-0 bg-transparent [&::-webkit-progress-bar]:bg-transparent";
  return (
    <span className="relative mt-1.5 block h-2 w-full overflow-hidden rounded-full bg-slate-200" aria-hidden="true" data-testid="bar">
      <progress className={`${layer} ${LIGHT[tone]}`} max={cell.goal ?? undefined} value={cell.forecast ?? undefined} />
      <progress className={`${layer} ${SOLID[tone]}`} max={cell.goal ?? undefined} value={cell.actual ?? undefined} />
    </span>
  );
}

/**
 * Three points on one small strip, for a rate, a duration or a size: the actual a solid dot, the forecast a ring above it, the
 * goal a tick across both. The strip runs from the least to the greatest of the three, so a rate is not drawn from zero.
 */
function Strip({ cell, tone }: { cell: CellData; tone: Tone }) {
  const [actual, forecast, goal] = pointScale([cell.actual, cell.forecast, cell.goal], 9);
  return (
    <span className="relative mt-1 block h-[26px] w-full" aria-hidden="true" data-testid="strip">
      <span className="absolute inset-x-0 top-[13px] h-px bg-slate-300" />
      {goal !== null ? <span data-mark="goal" data-at={goal} className="absolute top-0 h-[26px] w-0.5 -translate-x-1/2 rounded bg-slate-700" style={{ left: `${goal}%` }} /> : null}
      {forecast !== null ? <span data-mark="forecast" data-at={forecast} className={`absolute top-[2px] h-3 w-3 -translate-x-1/2 rounded-full border-2 bg-white ${MARK_RING[tone]}`} style={{ left: `${forecast}%` }} /> : null}
      {actual !== null ? <span data-mark="actual" data-at={actual} className={`absolute top-[14px] h-3 w-3 -translate-x-1/2 rounded-full ${MARK_FILL[tone]}`} style={{ left: `${actual}%` }} /> : null}
    </span>
  );
}

interface Props {
  source: CellSource;
  /** the pointer of the cell's row in the file, `/periods/{p}/rows/{r}` */
  rowPointer: string;
  rowId: string;
  /** the ids of the row's and the column's heads, which name the cell */
  headIds: string;
  column: ColumnKey;
  cell: CellData;
  selected: boolean;
  onOpen: (button: HTMLButtonElement) => void;
}

/** One cell of the grid: the actual large, the percent against the goal, a bar or a strip, and the forecast and the goal beneath. */
export function GridCell({ source, rowPointer, rowId, headIds, column, cell, selected, onOpen }: Props) {
  const own = LANE[source].cells[column];
  const at = `${rowPointer}/cells/${column}`;
  const tone = toneOf(cell.status);
  const actualOnly = cell.forecast === null && cell.goal === null;
  const noGoal = cell.none_because === "no_goal";
  const rated = cell.ratio !== null && cell.goal !== null;
  const strip = STRIP_COLUMNS.includes(column);
  const tip = useId();
  const content = useId();
  const reason = cell.status === "none" && cell.none_because !== null ? cell.none_because : null;
  const inRange = cell.goal_inside_range80 === true && cell.range80 !== null;
  return (
    <button
      type="button"
      data-testid={`cell-${rowId}-${column}`}
      data-color={tone}
      data-status={cell.status}
      aria-pressed={selected}
      aria-labelledby={`${headIds} ${content}`}
      aria-describedby={reason ? tip : undefined}
      onClick={(e) => onOpen(e.currentTarget)}
      className={`group relative block h-full min-h-[88px] w-full cursor-pointer px-2.5 pb-2 pt-2.5 text-left outline-none transition-colors hover:bg-slate-100/80 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ft-accent ${selected ? "bg-slate-100" : ""}`}
    >
      <span id={content} className="block">
        <span className="flex items-baseline justify-between gap-1">
          <Bound binding={own.actual} row={at} className="text-lg font-semibold leading-none tabular-nums text-slate-900 data-[unavailable=true]:text-sm data-[unavailable=true]:font-normal data-[unavailable=true]:text-slate-500" />
          {rated ? <Maybe binding={own.ratio} row={at} className={`text-xs font-semibold tabular-nums ${TEXT[tone]}`} /> : null}
        </span>
        {actualOnly ? null : (
          <>
            {rated && !strip ? <Bar cell={cell} tone={tone} /> : null}
            {strip && cell.goal !== null && !noGoal ? <Strip cell={cell} tone={tone} /> : null}
            {!rated && !strip ? <span className="mt-1.5 block h-2" aria-hidden="true" /> : null}
            <span className="mt-1 flex items-center justify-between gap-1 text-[11px] tabular-nums text-slate-600">
              <span className="flex min-w-0 items-center gap-0.5">
                <GaugeIcon />
                <span className="sr-only">Forecast </span>
                <Maybe binding={own.forecast} row={at} />
              </span>
              <span className="flex min-w-0 items-center gap-0.5">
                <TargetIcon />
                <span className="sr-only">Goal </span>
                {noGoal ? <span>no goal</span> : <Maybe binding={own.goal} row={at} />}
              </span>
            </span>
          </>
        )}
      </span>
      {inRange && own.range ? (
        <span data-testid="range-marker" className="absolute right-1.5 top-1 flex items-center gap-0.5 rounded-sm border border-slate-300 bg-white px-1 text-[9px] font-medium uppercase leading-3 text-slate-600">
          goal in 80% range
          <span className="sr-only">
            : <Bound binding={own.range.low} row={at} /> to <Bound binding={own.range.high} row={at} />
          </span>
        </span>
      ) : null}
      {reason ? (
        <span id={tip} role="tooltip" className="pointer-events-none absolute inset-x-1 top-1 z-30 hidden rounded bg-slate-800 px-2 py-1.5 text-[11px] font-normal leading-snug text-white shadow-lg group-hover:block group-focus-visible:block">
          <Bound binding={LANE[source].reason} row={`/reasons/${reason}`} />
        </span>
      ) : null}
    </button>
  );
}
