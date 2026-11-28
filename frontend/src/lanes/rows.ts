import type { Row } from "./types";

/** What the reader has done to the grid: the drill path, the segments opened to their owners, the rows excluded. */
export interface View {
  /** ids of the rows drilled into, outermost first; empty means the company total is the root */
  path: string[];
  expanded: ReadonlySet<string>;
  hidden: ReadonlySet<string>;
}

export interface VisibleRow {
  row: Row;
  /** "root" is the row the grid is drilled into: tinted like the total, with its children below */
  role: "root" | "segment" | "owner";
  expandable: boolean;
  open: boolean;
}

export const NO_VIEW: View = { path: [], expanded: new Set(), hidden: new Set() };

const childrenOf = (rows: Row[], id: string) => rows.filter((r) => r.parent_id === id);

/** The rows to draw, in order, and how many of the rows in view the reader has excluded. */
export function visibleRows(rows: Row[], view: View): { shown: VisibleRow[]; hiddenCount: number } {
  const root = rows.find((r) => r.id === (view.path[0] ?? "total")) ?? rows[0];
  const shown: VisibleRow[] = [{ row: root, role: "root", expandable: false, open: false }];
  const excluded: string[] = [];
  for (const child of childrenOf(rows, root.id)) {
    if (view.hidden.has(child.id)) {
      excluded.push(child.id);
      continue;
    }
    const grandchildren = childrenOf(rows, child.id);
    const open = view.expanded.has(child.id) && grandchildren.length > 0;
    shown.push({ row: child, role: child.level === "owner" ? "owner" : "segment", expandable: grandchildren.length > 0, open });
    if (open) {
      for (const g of grandchildren) {
        if (view.hidden.has(g.id)) excluded.push(g.id);
        else shown.push({ row: g, role: "owner", expandable: false, open: false });
      }
    }
  }
  return { shown, hiddenCount: excluded.length };
}

/** The chips of the drill path: the rows drilled into, then the level whose members are the rows. */
export function levelName(rows: Row[], view: View): { drilled: Array<{ id: string; level: string; label: string }>; trailing: string } {
  const drilled = view.path.map((id) => {
    const row = rows.find((r) => r.id === id)!;
    return { id, level: row.level === "segment" ? "Segment" : "Owner", label: row.display_label };
  });
  return { drilled, trailing: view.path.length === 0 ? "Segment" : "Owner" };
}
