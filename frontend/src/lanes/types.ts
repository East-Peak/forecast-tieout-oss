/** The prototype's data file, as `scripts/prepare-lanes-prototype.mjs` writes it. Every number is a decimal string or null. */
export type Color = "red" | "green" | "none";

interface Split {
  carried_in: string;
  created_in_period: string;
}

export interface SplitBars {
  actual: { carried_w: string; created_w: string };
  forecast: { carried_w: string; created_w: string };
}

export interface Cell {
  actual: string | null;
  forecast: string | null;
  goal: string | null;
  ratio: string | null;
  color: Color;
  thin: boolean;
  has_goal: boolean;
  pct_text: string | null;
  actual_share?: string | null;
  forecast_share?: string | null;
  goal_pos?: string;
  actual_pos?: string | null;
  forecast_pos?: string | null;
  null_reason?: string;
  goal_label?: string;
  split?: { actual: Split; forecast: Split };
  split_bars?: SplitBars | null;
  sample?: { actual: number; actual_wins: number; forecast: number; goal: number };
  forecast_basis?: string;
  created_from?: string;
  created_through?: string;
  evaluated_days?: number;
  range80?: [string, string];
  goal_inside_range80?: boolean;
}

export interface Row {
  id: string;
  parent_id: string | null;
  level: "total" | "segment" | "owner";
  label: string;
  display_label: string;
  sub_label: string | null;
  allocated: boolean;
  allocation_note: string | null;
  cells: Record<string, Cell>;
  records: { created: string[]; won: string[] };
}

export interface Column {
  key: string;
  title: string;
  unit: string;
  kind: "volume" | "processing";
  goal_label: string;
}

interface Period {
  start_exclusive: string;
  end_inclusive: string;
  rows: Row[];
}

export interface Deal {
  id: string;
  segment: string;
  owner_id: string;
  owner_name: string;
  created: string;
  close: string | null;
  first_recorded_arr: string;
  current_arr: string;
  stage: string;
  status: string;
}

export interface LanesData {
  meta: {
    company: string;
    as_of: string;
    plan_basis: { label_text: string; cutoff: string };
    frozen_schedule: Array<{ quarter: string; bookings: string; target: string; surplus: string }>;
    schedule_totals: { bookings: string; target: string; surplus: string };
    scale_factors: Record<string, { bookings: string; won: string; created_arr: string }>;
  };
  columns: Column[];
  periods: Record<string, Period>;
  deals: Record<string, Deal>;
}
