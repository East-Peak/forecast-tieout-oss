/**
 * Test-only. What the Plan screen must show for a company and scenario, written by hand as typed
 * accessors on the generated report types. Differences between scenarios are read from comparison.json.
 * Texts come from independent.ts, not from src/lib/format.ts.
 */
import type { TieoutReport } from "../../generated/report";
import { B, REST, TWELVE, W } from "../plan/bindings";
import { kit, orWords } from "./expectKit";
import * as fmt from "./independent";
import type { Built, Case } from "./screenChecks";

type FullPlan = Extract<NonNullable<TieoutReport["plan"]>, { items: unknown }>;
type Actions = Extract<TieoutReport["actions"], { comparison: unknown }>;
type Ranged = { range80: [string, string]; range95: [string, string] };

const SCENARIOS = "/companies/{id={company}}/scenarios";

export function build({ report: r, index, comparison, company, scenario }: Case): Built {
  const { expected, absent, one, many, when } = kit();
  const plan: FullPlan | null = r.plan && !("unavailable" in r.plan) ? r.plan : null;
  const actions: Actions | null = "unavailable" in r.actions ? null : r.actions;
  const me = comparison.rows.find((x) => x.scenario === scenario)!;
  const entry = index.companies.find((c) => c.id === company)!;

  one(B.fiscalYear.id, r.inputs.fiscal_year);
  one(B.asOf.id, fmt.date(r.inputs.as_of));

  // the picker: every scenario of this company, and the one chosen described
  many(B.pickLabel.id, entry.scenarios.map((s) => s.label), entry.scenarios.map((_, i) => `${SCENARIOS}/${i}`));
  one(B.scenarioDescription.id, entry.scenarios.find((s) => s.id === scenario)!.description);

  // a plan that cannot be valued says so; as signed there is no plan and nothing is shown for one
  when(r.plan !== undefined && plan === null, B.planUnavailable.id, () => (r.plan && "unavailable" in r.plan ? r.plan.unavailable : ""));
  when(plan !== null, B.planExpected.id, () => fmt.usdShort(plan!.expected_fiscal_year));
  when(plan !== null, B.planGap.id, () => fmt.usdShort(plan!.gap.fiscal_year.gap_with_plan));
  when(plan !== null, B.cmpGapChange.id, () => orWords(me.fiscal_year_gap_change, fmt.usdShort));
  when(plan !== null, B.cmpMoreNext.id, () => orWords(me.bookings_change?.[TWELVE] ?? null, fmt.usdShort));
  when(plan !== null, B.cmpCost.id, () => orWords(me.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered"));
  when(plan !== null, B.planDefinition.id, () => plan!.baseline_definition);
  when(plan !== null, B.planFile.id, () => plan!.file);

  // both windows, each with its ranges (the 95% ones in the opened row)
  const horizons = r.forecasts.fitted_ranges.horizons as Record<string, Ranged>;
  const bookings = plan?.ranges.bookings_in_window as Record<string, Ranged> | undefined;
  for (const [key, window] of [["rest", REST], ["next12", TWELVE]] as const) {
    const w = W[key];
    when(plan !== null, w.asSigned.id, () => fmt.usdShort(plan!.baseline[window]));
    when(plan !== null, w.withPlan.id, () => fmt.usdShort(plan!.with_plan[window]));
    when(plan !== null, w.gain.id, () => orWords(me.bookings_change?.[window] ?? null, fmt.usdShort));
    when(plan !== null, w.base80Low.id, () => fmt.usdShort(horizons[window].range80[0]));
    when(plan !== null, w.base80High.id, () => fmt.usdShort(horizons[window].range80[1]));
    when(plan !== null, w.base95Low.id, () => fmt.usdShort(horizons[window].range95[0]));
    when(plan !== null, w.base95High.id, () => fmt.usdShort(horizons[window].range95[1]));
    when(plan !== null, w.plan80Low.id, () => fmt.usdShort(bookings![window].range80[0]));
    when(plan !== null, w.plan80High.id, () => fmt.usdShort(bookings![window].range80[1]));
    when(plan !== null, w.plan95Low.id, () => fmt.usdShort(bookings![window].range95[0]));
    when(plan !== null, w.plan95High.id, () => fmt.usdShort(bookings![window].range95[1]));
  }
  when(plan !== null, B.rangeStatus.id, () => plan!.ranges.status);
  when(plan !== null, B.rangeDrawn.id, () => plan!.ranges.what_is_drawn);

  // the gap to target in both windows
  when(plan !== null, B.gapFyBase.id, () => fmt.usdShort(plan!.gap.fiscal_year.baseline_gap));
  when(plan !== null, B.gapFyPlan.id, () => fmt.usdShort(plan!.gap.fiscal_year.gap_with_plan));
  const next = plan?.gap.next_twelve_months ?? null;
  when(plan !== null && next !== null, B.gapNextBase.id, () => fmt.usdShort(next!.baseline_gap));
  when(plan !== null && next !== null, B.gapNextPlan.id, () => fmt.usdShort(next!.gap_with_plan));
  when(plan !== null, B.gapNextNote.id, () => (next === null ? "no target in this window" : next.note));

  // the plan's items, each with its contribution and cost
  const items = plan?.items ?? [];
  const iRows = items.map((_, i) => `/plan/items/${i}`);
  many(B.iLabel.id, items.map((x) => x.label), iRows);
  many(B.iDetail.id, items.map((x) => x.detail), iRows);
  many(B.iRest.id, items.map((x) => (x.contribution === null ? `unavailable: ${"note" in x ? x.note : ""}` : fmt.usdShort(x.contribution[REST]))), iRows);
  many(B.iNext.id, items.map((x) => (x.contribution === null ? "not valued" : fmt.usdShort(x.contribution[TWELVE]))), iRows);
  many(B.iCost.id, items.map((x) => orWords(x.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered")), iRows);
  const programmes = items.map((x, i) => [x, i] as const).filter(([x]) => x.kind === "programme");
  many(B.iSchedule.id, programmes.map(([x]) => ("payment_schedule" in x ? x.payment_schedule : "")), programmes.map(([, i]) => `/plan/items/${i}`));
  when(plan !== null, B.itemsCost.id, () => orWords(plan!.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered"));
  when(plan !== null, B.itemsRest.id, () => fmt.usdShort(plan!.contributions_total[REST]));
  when(plan !== null, B.itemsNext.id, () => fmt.usdShort(plan!.contributions_total[TWELVE]));
  when(plan !== null, B.itemsOrder.id, () => plan!.order);
  when(plan !== null, B.itemsCostNote.id, () => plan!.cost_note);

  // the two unit actions, compared
  when(actions === null, B.actionsUnavailable.id, () => ("unavailable" in r.actions ? r.actions.unavailable : ""));
  const rows = actions?.comparison ?? [];
  const aRows = rows.map((_, i) => `/actions/comparison/${i}`);
  when(actions !== null, B.actionsDefinition.id, () => actions!.definition);
  when(actions !== null, B.actionsMeaning.id, () => actions!.meaning);
  when(actions !== null, B.actionsShape.id, () => actions!.programme_shape);
  const best = rows.map((x, i) => [x, i] as const).filter(([x]) => x.rank === 1);
  many(B.bestAction.id, best.map(([x]) => x.action), best.map(([, i]) => `/actions/comparison/${i}`));
  many(B.bestPerDollar.id, best.map(([x]) => fmt.multiple(x.gain_per_dollar!)), best.map(([, i]) => `/actions/comparison/${i}`));
  many(B.aAction.id, rows.map((x) => x.action), aRows);
  many(B.aStatus.id, rows.map((x) => x.status), aRows);
  many(B.aRank.id, rows.map((x) => (x.rank === null ? "not ranked" : fmt.quantity(x.rank))), aRows);
  const why = (x: Actions["comparison"][number], fallback = "unavailable") => (x.not_ranked_because === null ? fallback : `unavailable: ${x.not_ranked_because}`);
  many(B.aNext.id, rows.map((x) => (x.bookings_gained === null ? why(x) : fmt.usdShort(x.bookings_gained[TWELVE]))), aRows);
  many(B.aRest.id, rows.map((x) => (x.bookings_gained === null ? why(x) : fmt.usdShort(x.bookings_gained[REST]))), aRows);
  many(B.aCost.id, rows.map((x) => (x.cash_cost_in_twelve_months === null ? why(x) : fmt.usdShort(x.cash_cost_in_twelve_months))), aRows);
  many(B.aPerDollar.id, rows.map((x) => (x.gain_per_dollar === null ? why(x) : fmt.multiple(x.gain_per_dollar))), aRows);
  many(B.aStarts.id, rows.map((x) => (x.starts_paying === null ? why(x, "not within the window") : fmt.month(x.starts_paying))), aRows);

  // what closes the gap alone
  const close = actions?.close_the_fiscal_year_gap;
  when(actions !== null, B.closeBasis.id, () => close!.basis);
  when(actions !== null, B.closeGap.id, () => fmt.usdShort(close!.fiscal_year_gap));
  const hires = close?.hires;
  const hiresFull = hires !== undefined && "bound" in hires ? hires : null;
  when(actions !== null, B.hiresOutcome.id, () => hires!.outcome);
  when(actions !== null && hiresFull === null, B.hiresNote.id, () => (hires && "note" in hires ? hires.note : ""));
  when(hiresFull !== null, B.hiresCount.id, () => (hiresFull!.count === null ? "no number of hires closes it" : fmt.quantity(hiresFull!.count)));
  when(hiresFull !== null, B.hiresBound.id, () => fmt.quantity(hiresFull!.bound));
  when(hiresFull !== null, B.hiresBoundBasis.id, () => hiresFull!.bound_basis);
  when(hiresFull !== null, B.hiresCost.id, () => orWords(hiresFull!.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered"));
  const programme = close?.programme;
  when(actions !== null, B.programmeOutcome.id, () => programme!.outcome);
  when(actions !== null, B.programmeDollars.id, () => orWords(programme!.dollars, fmt.usdShort, "no amount closes it within the cap"));
  when(actions !== null, B.programmeCap.id, () => fmt.usdShort(programme!.cap));
  when(actions !== null, B.programmeOver.id, () => orWords(programme!.needed_but_over_the_cap, fmt.usdShort, "not over the cap"));
  when(actions !== null, B.programmeCost.id, () => orWords(programme!.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered"));

  // every scenario side by side, from comparison.json
  const cRows = comparison.rows.map((_, i) => `/rows/${i}`);
  const baselineRow = (x: (typeof comparison.rows)[number]) => x.scenario === comparison.baseline;
  many(B.sLabel.id, comparison.rows.map((x) => x.label), cRows);
  many(B.sExpected.id, comparison.rows.map((x) => orWords(x.expected_fiscal_year, fmt.usdShort)), cRows);
  many(B.sGap.id, comparison.rows.map((x) => orWords(x.fiscal_year_gap, fmt.usdShort)), cRows);
  many(B.sGapChange.id, comparison.rows.map((x) => orWords(x.fiscal_year_gap_change, fmt.usdShort, "no plan valued")), cRows);
  many(B.sRest.id, comparison.rows.map((x) => orWords(x.bookings_change?.[REST] ?? null, fmt.usdShort, "no plan valued")), cRows);
  many(B.sNext.id, comparison.rows.map((x) => orWords(x.bookings_change?.[TWELVE] ?? null, fmt.usdShort, "no plan valued")), cRows);
  const rowsBy = (pick: boolean) => comparison.rows.map((x, i) => [x, i] as const).filter(([x]) => baselineRow(x) === pick);
  many(B.sCostNone.id, rowsBy(true).map(() => "no plan, no cost"), rowsBy(true).map(([, i]) => `/rows/${i}`));
  many(B.sCost.id, rowsBy(false).map(([x]) => orWords(x.cash_cost_in_twelve_months, fmt.usdShort, "cost not entered")), rowsBy(false).map(([, i]) => `/rows/${i}`));

  return { expected, absent, periodLabels: [] };
}
