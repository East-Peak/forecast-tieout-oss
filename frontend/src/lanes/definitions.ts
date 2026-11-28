/** What each column means, in plain words (from the swimlane spec's table). */
export const DEFINITIONS: Record<string, string> = {
  opening:
    "Deals open immediately before the period starts. A stock, never added across quarters. The goal is the fiscal year's opening snapshot.",
  created:
    "Deals created in the period up to the as-of date. The forecast adds the creation still expected. The goal is what the frozen creation schedule requires.",
  created_arr:
    "The first recorded ARR of the deals created in the period. The forecast adds the pipeline still expected to be created. The goal comes from the same frozen schedule.",
  win_rate:
    "The share of deals created in the trailing 365 days, old enough to have resolved, that were won. It is a dated benchmark, not a multiplier for this period's Created. The forecast uses the pooled rate for new pipeline; the goal is the rate assumed at the plan start.",
  cycle:
    "Average days from creation to close for the period's wins. The forecast blends actual wins with those still expected. The goal is the frozen schedule's implied cycle.",
  won:
    "Deals won in the period: wins from pipeline carried in plus wins from pipeline created in the period. The forecast adds the wins still expected. The goal is the bookings target divided by the plan-start average won ARR.",
  avg_won_arr:
    "Bookings divided by wins. The forecast is forecast bookings over forecast wins. Shown as unavailable when there are no wins.",
  bookings:
    "Won ARR closed in the period. The forecast adds the expected remainder. The goal is the entered target.",
};
