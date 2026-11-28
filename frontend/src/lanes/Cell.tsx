import type { KeyboardEvent, MouseEvent } from "react";
import { GaugeIcon, TargetIcon } from "./icons";
import { show } from "./show";
import type { Cell as CellData, Color, Column, Row } from "./types";

const TEXT: Record<Color, string> = { red: "text-red-600", green: "text-green-700", none: "text-slate-500" };
const STROKE: Record<Color, string> = { red: "#dc2626", green: "#15803d", none: "#64748b" };

/** The color a cell shows: owners are not judged on rates, cycle or average size, and a later hire has no goal to miss. */
function effectiveColor(row: Row, column: Column, cell: CellData): Color {
  if (row.level === "owner" && (column.kind === "processing" || !row.allocated)) return "none";
  return cell.color;
}

export function isMuted(row: Row, column: Column): boolean {
  return row.level === "owner" && column.kind === "processing";
}

function Bar({ column, cell, color }: { column: Column; cell: CellData; color: Color }) {
  const stroke = STROKE[color];
  return (
    <svg className="mt-1.5 block h-1.5 w-full" aria-hidden="true">
      <line x1="0" x2="100%" y1="50%" y2="50%" stroke="#e2e8f0" strokeWidth="6" />
      {column.kind === "volume" && cell.actual_share != null && cell.forecast_share != null ? (
        <>
          <line x1={cell.actual_share} x2={cell.forecast_share} y1="50%" y2="50%" stroke={stroke} strokeWidth="6" strokeDasharray="1.5 2.5" opacity="0.7" />
          <line x1="0" x2={cell.actual_share} y1="50%" y2="50%" stroke={stroke} strokeWidth="6" />
        </>
      ) : null}
      {column.kind === "processing" && cell.goal_pos ? (
        <>
          <line x1={cell.goal_pos} x2={cell.goal_pos} y1="0" y2="100%" stroke="#94a3b8" strokeWidth="1.5" />
          {cell.forecast_pos ? <circle cx={cell.forecast_pos} cy="50%" r="2.5" fill="#fff" stroke={stroke} strokeWidth="1.3" /> : null}
          {cell.actual_pos ? <circle cx={cell.actual_pos} cy="50%" r="2.5" fill={stroke} /> : null}
        </>
      ) : null}
    </svg>
  );
}

interface Props {
  row: Row;
  column: Column;
  cell: CellData;
  selected: boolean;
  onOpen: () => void;
  onMore: (button: HTMLElement) => void;
}

/** One cell of the grid: the actual large, the forecast against goal as a percent, a bar, and the forecast and goal beneath. */
export function GridCell({ row, column, cell, selected, onOpen, onMore }: Props) {
  const color = effectiveColor(row, column, cell);
  const muted = isMuted(row, column);
  const noAllocation = row.level === "owner" && !row.allocated;
  const showGoal = cell.has_goal && !noAllocation;
  const pooled = column.key === "win_rate";
  const key = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpen();
    }
  };
  const more = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onMore(e.currentTarget);
  };
  const title = `${column.title}, ${row.display_label}`;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Open ${title}`}
      aria-pressed={selected}
      data-testid={`cell-${row.id}-${column.key}`}
      data-color={color}
      onClick={onOpen}
      onKeyDown={key}
      className={`group relative flex h-full min-h-[76px] cursor-pointer flex-col justify-center px-2.5 pb-1.5 pt-4 outline-none transition-colors hover:bg-slate-100/80 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ft-accent ${selected ? "bg-slate-100" : ""}`}
    >
      <button
        type="button"
        aria-label={`More actions for ${title}`}
        aria-haspopup="menu"
        onClick={more}
        className="absolute right-1 top-0.5 flex h-4 items-center rounded px-1 text-[11px] font-semibold leading-none tracking-wide text-slate-400 opacity-0 hover:bg-white hover:text-slate-700 focus-visible:opacity-100 group-hover:opacity-100"
      >
        <span aria-hidden="true">{"···"}</span>
      </button>
      {muted ? (
        <span className="text-[15px] tabular-nums text-slate-500" title={cell.actual === null ? cell.null_reason : "Shown as evidence: too few observations to judge a person on this"}>
          {show(column.key, cell.actual, true)}
        </span>
      ) : (
        <>
          <div className="flex items-baseline justify-between gap-1">
            <span className="flex items-baseline gap-1">
              <span className="text-lg font-semibold leading-none tabular-nums text-slate-900" title={cell.actual === null ? cell.null_reason : undefined}>
                {show(column.key, cell.actual, true)}
              </span>
              {cell.thin ? (
                <span title="few observations" aria-label="few observations" data-testid="thin-mark" className="inline-block h-1.5 w-1.5 shrink-0 translate-y-[-2px] rounded-full border border-slate-400" />
              ) : null}
            </span>
            {showGoal && cell.pct_text ? (
              <span className={`text-xs font-semibold tabular-nums ${TEXT[color]}`} data-testid="pct">
                {cell.pct_text}
              </span>
            ) : null}
          </div>
          {showGoal ? <Bar column={column} cell={cell} color={color} /> : <div className="mt-1.5 h-1.5" />}
          <div className="mt-1 flex items-center justify-between gap-1 text-[11px] tabular-nums text-slate-500">
            <span className="flex items-center gap-0.5" title="forecast">
              <GaugeIcon />
              {show(column.key, cell.forecast)}
              {pooled ? <span className="ml-0.5 rounded bg-slate-100 px-0.5 text-[8px] font-medium uppercase leading-3 text-slate-500">pooled</span> : null}
            </span>
            {showGoal ? (
              <span className="flex items-center gap-0.5" title={`goal: ${column.goal_label}`}>
                <TargetIcon />
                {show(column.key, cell.goal)}
              </span>
            ) : (
              <span className="text-slate-400" title={noAllocation ? `no goal: ${row.allocation_note}` : undefined}>
                no goal
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
