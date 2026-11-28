import type { ColumnKey } from "./types";

/** What each column means, in plain words (the swimlane spec's table). */
export const DEFINITIONS: Record<ColumnKey, string> = {
  open: "Deals open immediately before the period starts. A stock, never added across quarters. The goal is the fiscal year's opening snapshot.",
  created: "Deals created in the period up to the as-of date. The forecast adds the creation still expected. The goal is what the frozen creation schedule requires.",
  created_arr: "The first recorded ARR of the deals created in the period. The forecast adds the pipeline still expected to be created. The goal comes from the same frozen schedule.",
  win_rate:
    "The share of deals created in the trailing year, old enough to have resolved, that were won. It is a dated benchmark, not a multiplier for this period's created deals. The forecast uses the pooled rate for new pipeline; the goal is the rate assumed at the plan start.",
  cycle: "Average days from creation to close for the period's wins. The forecast blends actual wins with those still expected. The goal is the frozen schedule's implied cycle.",
  won: "Deals won in the period: wins from pipeline carried in plus wins from pipeline created in the period. The forecast adds the wins still expected. The goal is the bookings target over the plan-start average won ARR.",
  avg_won_arr: "Bookings divided by wins. The forecast is forecast bookings over forecast wins. Shown as unavailable when there are no wins.",
  bookings: "Won ARR closed in the period. The forecast adds the expected remainder. The goal is the entered target.",
};

/** What the two numbers a rate, a duration or a size is made of are, column by column. */
export const PARTS: Partial<Record<ColumnKey, { top: string; bottom: string }>> = {
  win_rate: { top: "won", bottom: "deals in the cohort" },
  cycle: { top: "days from creation to close", bottom: "wins" },
  avg_won_arr: { top: "bookings", bottom: "wins" },
};
