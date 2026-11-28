import type { TieoutLanes } from "../generated/lanes";
import type { TieoutLanesBasis } from "../generated/lanesBasis";
import type { TieoutLanesOwners } from "../generated/lanesOwners";
import type { TieoutLanesRecords } from "../generated/lanesRecords";

/** The four files of the swimlane grid, as the core writes them (types generated from their schemas). */
export type LanesFile = Extract<TieoutLanes, { periods: unknown }>;
export type OwnersFile = TieoutLanesOwners;
export type BasisFile = TieoutLanesBasis;
export type RecordsFile = TieoutLanesRecords;

export type LanesAny = TieoutLanes;
type Column = LanesFile["columns"][number];
export type ColumnKey = Column["key"];
/** A cell of either file: the owners' hold what a lane's does, and the lane's total bookings cell adds its 80% range. */
export type Cell = OwnersFile["periods"][number]["rows"][number]["cells"][ColumnKey] & {
  goal_inside_range80?: boolean | null;
  range80?: [string, string] | null;
  /** where the strip's three points stand, 0 to 100, written by the core for a rate, a duration or a size of a lane */
  marks?: { actual: string | null; forecast: string | null; goal: string } | null;
};
export type Status = Cell["status"];

/** A row of either file, as the grid and the panel read it: total, segment, owner, planned hires or programs. */
export interface Row {
  allocation: string;
  cells: Record<ColumnKey, Cell>;
  kind: string;
  label: string;
  path: readonly string[];
}


/** The files a company's grid reads, by the path the index gives each. */
export interface LanesLoaders {
  lanes(path: string): Promise<TieoutLanes>;
  owners(path: string): Promise<OwnersFile>;
  basis(path: string): Promise<BasisFile>;
  records(path: string): Promise<RecordsFile>;
}
