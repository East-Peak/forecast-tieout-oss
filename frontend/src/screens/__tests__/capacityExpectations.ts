/**
 * Test-only. What the Capacity screen must show for a company and scenario, written by hand as typed
 * accessors on the generated report types (not by following the screen's pointers). Texts come from
 * independent.ts, not from src/lib/format.ts.
 */
import type { TieoutReport } from "../../generated/report";
import { B } from "../capacity/bindings";
import { kit, orWords } from "./expectKit";
import * as fmt from "./independent";
import type { Built, Case } from "./screenChecks";

type Roster = Extract<TieoutReport["roster_capacity"]["roster"], { heads_at_as_of: number }>;
type Quota = Extract<TieoutReport["quota_productivity"], { all_reps: unknown }>;
type Group = Quota["all_reps"];

const RC = "/roster_capacity";
const QP = "/quota_productivity";

export function build({ report: r, index: _index }: Case): Built {
  const { expected, absent, one, many, when } = kit();
  const rc = r.roster_capacity;
  const roster: Roster | null = "unavailable" in rc.roster ? null : rc.roster;
  const quota: Quota | null = "unavailable" in r.quota_productivity ? null : r.quota_productivity;

  one(B.fiscalYear.id, r.inputs.fiscal_year);
  one(B.asOf.id, fmt.date(r.inputs.as_of));

  // the headline
  when(roster === null, B.rosterUnavailable.id, () => ("unavailable" in rc.roster ? rc.roster.unavailable : ""));
  when(roster !== null, B.heads.id, () => fmt.quantity(roster!.heads_at_as_of));
  when(roster !== null, B.ramped.id, () => orWords(roster!.ramped_equivalents_at_as_of, fmt.quantity));
  when(roster !== null, B.target.id, () =>
    roster!.headcount_target_this_month === null ? "no headcount target entered" : fmt.quantity(roster!.headcount_target_this_month),
  );
  when(roster !== null, B.targetNote.id, () => roster!.headcount_target_note);
  when(roster !== null && rc.attrition !== undefined, B.departed.id, () => fmt.quantity(roster!.departed_to_date));

  // quota against what was observed
  when(quota === null, B.quotaUnavailable.id, () => ("unavailable" in r.quota_productivity ? r.quota_productivity.unavailable : ""));
  when(quota !== null, B.quotaOverTarget.id, () => orWords(quota!.total_quota.quota_over_target, fmt.multiple, "no target to compare with"));
  when(quota !== null, B.attainmentAll.id, () => orWords(quota!.all_reps.attainment, fmt.percent1, "no quota in the window"));
  when(quota !== null, B.quotaAnnual.id, () => fmt.usdShort(quota!.total_quota.annual_quota_of_people_employed_at_as_of));
  when(quota !== null, B.quotaTarget.id, () => fmt.usdShort(quota!.total_quota.fiscal_year_target));
  when(quota !== null, B.quotaPeople.id, () => fmt.quantity(quota!.total_quota.people));
  when(quota !== null, B.quotaNote.id, () => quota!.total_quota.note);
  when(quota !== null, B.quotaDefinition.id, () => quota!.definition);
  when(quota !== null, B.quotaWindow.id, () => quota!.window);
  when(quota !== null, B.winsCredited.id, () => fmt.usdShort(quota!.wins_credited));
  when(quota !== null, B.winsInWindow.id, () => fmt.usdShort(quota!.wins_in_window));
  when(quota !== null, B.winsUnattributed.id, () => fmt.usdShort(quota!.wins_unattributed));
  when(quota !== null, B.unattributedNote.id, () => quota!.unattributed_note);
  when(quota !== null, B.repsWithoutQuota.id, () => fmt.quantity(quota!.reps_without_quota));
  when(quota !== null, B.spreadMinDays.id, () => fmt.quantity(quota!.spread_min_days));

  const groups: Array<[string, Group]> = quota
    ? [[`${QP}/all_reps`, quota.all_reps], ...Object.entries(quota.by_segment).map(([name, g]) => [`${QP}/by_segment/${name}`, g!] as [string, Group])]
    : [];
  const rowsOf = (pick: (g: Group) => boolean) => groups.filter(([, g]) => pick(g)).map(([row]) => row);
  const have = (g: Group) => g.spread_across_reps !== null;
  many(B.gReps.id, groups.map(([, g]) => fmt.quantity(g.reps)), groups.map(([row]) => row));
  many(B.gSpreadReps.id, groups.map(([, g]) => fmt.quantity(g.spread_reps)), groups.map(([row]) => row));
  many(B.gQuota.id, groups.map(([, g]) => fmt.usdShort(g.prorated_quota)), groups.map(([row]) => row));
  many(B.gWins.id, groups.map(([, g]) => fmt.usdShort(g.wins_credited)), groups.map(([row]) => row));
  many(B.gAttainment.id, groups.map(([, g]) => orWords(g.attainment, fmt.percent1, "no quota in the window")), groups.map(([row]) => row));
  // a group with no spread says so once, in the place of the median
  many(
    B.gMedian.id,
    groups.map(([, g]) => (g.spread_across_reps === null ? "not enough tenure to show a spread" : fmt.percent1(g.spread_across_reps.median))),
    groups.map(([row]) => row),
  );
  for (const [binding, pick] of [
    [B.gMin, (s: NonNullable<Group["spread_across_reps"]>) => s.min],
    [B.gP25, (s: NonNullable<Group["spread_across_reps"]>) => s.p25],
    [B.gP75, (s: NonNullable<Group["spread_across_reps"]>) => s.p75],
    [B.gMax, (s: NonNullable<Group["spread_across_reps"]>) => s.max],
  ] as const) {
    many(binding.id, groups.filter(([, g]) => have(g)).map(([, g]) => fmt.percent1(pick(g.spread_across_reps!))), rowsOf(have));
  }

  // does headcount explain pipeline
  const d = rc.decision;
  const notAdopted = d.outcome !== "adopted";
  one(B.decisionOutcome.id, d.outcome);
  one(B.decisionLabel.id, d.label);
  one(B.decisionReason.id, d.reason, notAdopted ? 2 : 1); // beside the headline when capacity is not used, and in the decision's own card
  one(B.decisionRule.id, d.declared_rule);
  one(B.decisionUses.id, d.forecast_uses);
  one(B.decisionScoredOn.id, d.scored_on);
  one(B.decisionAssociation.id, d.association);
  one(B.decisionVariation.id, orWords(d.staffing_variation, fmt.percent1, "not measured"));
  one(B.periodFrom.id, d.scored_period === null ? "no scored period" : fmt.date(d.scored_period[0]));
  when(d.scored_period !== null, B.periodTo.id, () => fmt.date(d.scored_period![1]));
  many(B.hMonths.id, d.horizons.map((h) => fmt.quantity(h.horizon_months)), d.horizons.map((_, i) => `${RC}/decision/horizons/${i}`));
  many(B.hFolds.id, d.horizons.map((h) => fmt.quantity(h.folds)), d.horizons.map((_, i) => `${RC}/decision/horizons/${i}`));
  many(B.hCapacity.id, d.horizons.map((h) => fmt.usdShort(h.mean_absolute_error_capacity)), d.horizons.map((_, i) => `${RC}/decision/horizons/${i}`));
  many(B.hFlat.id, d.horizons.map((h) => fmt.usdShort(h.mean_absolute_error_flat)), d.horizons.map((_, i) => `${RC}/decision/horizons/${i}`));
  many(B.hImprovement.id, d.horizons.map((h) => fmt.percent1(h.improvement)), d.horizons.map((_, i) => `${RC}/decision/horizons/${i}`));
  when(rc.diagnostic !== undefined, B.hiringAction.id, () => rc.diagnostic!.hiring_action);
  when(rc.diagnostic !== undefined, B.diagnosticLabel.id, () => rc.diagnostic!.label);

  // ramp, attrition and the creation rate
  const ramp = rc.ramp;
  when(ramp !== undefined, B.rampSource.id, () => ramp!.source);
  when(ramp !== undefined, B.rampSample.id, () => ramp!.sample);
  when(ramp !== undefined, B.rampDefinition.id, () => ramp!.definition);
  when(ramp !== undefined, B.rampAfter.id, () => ramp!.after);
  when(ramp !== undefined && ramp.why_not_fitted !== "", B.rampWhyNot.id, () => ramp!.why_not_fitted);
  when(ramp !== undefined && ramp.limitation !== null, B.rampLimitation.id, () => ramp!.limitation!);
  when(ramp !== undefined && ramp.fitted_through !== null, B.rampFittedThrough.id, () => ramp!.fitted_through!);
  when(ramp !== undefined, B.rampLeftOut.id, () => fmt.quantity(ramp!.deals_left_out.count));
  when(ramp !== undefined && ramp.deals_left_out.why !== null, B.rampLeftOutWhy.id, () => ramp!.deals_left_out.why!);
  const weights = ramp?.weights ?? [];
  const wRow = (i: number) => `${RC}/ramp/weights/${i}`;
  many(B.wMonth.id, weights.map((w) => fmt.quantity(w.tenure_month)), weights.map((_, i) => wRow(i)));
  many(B.wWeight.id, weights.map((w) => fmt.percent1(w.weight)), weights.map((_, i) => wRow(i)));
  const idx = (pick: (w: (typeof weights)[number]) => boolean) => weights.map((w, i) => [w, i] as const).filter(([w]) => pick(w));
  const pair = idx((w) => Array.isArray(w.range95));
  many(B.wLow.id, pair.map(([w]) => fmt.percent1((w.range95 as [string, string])[0])), pair.map(([, i]) => wRow(i)));
  many(B.wHigh.id, pair.map(([w]) => fmt.percent1((w.range95 as [string, string])[1])), pair.map(([, i]) => wRow(i)));
  const ceiling = idx((w) => typeof w.range95 === "string");
  many(B.wCeiling.id, ceiling.map(([w]) => w.range95 as string), ceiling.map(([, i]) => wRow(i)));
  const none = idx((w) => w.range95 === null);
  many(B.wNoRange.id, none.map(() => "no range: not fitted"), none.map(([, i]) => wRow(i)));

  const a = rc.attrition;
  when(a !== undefined, B.attritionRate.id, () => fmt.percent1(a!.monthly_rate));
  when(a !== undefined, B.attritionSource.id, () => a!.source);
  when(a !== undefined, B.attritionSample.id, () => a!.sample);
  when(a !== undefined, B.attritionLow.id, () => (a!.range95 === null ? "no range: not fitted" : fmt.percent1(a!.range95[0])));
  when(a !== undefined && a.range95 !== null, B.attritionHigh.id, () => fmt.percent1(a!.range95![1]));
  when(a !== undefined && a.why_not_fitted !== "", B.attritionWhyNot.id, () => a!.why_not_fitted);
  when(a !== undefined, B.attritionForward.id, () => a!.forward);
  const c = rc.creation_rate;
  when(c !== undefined, B.creationRate.id, () => fmt.decimal2(c!.deals_per_ramped_ae_month));
  when(c !== undefined, B.creationDeals.id, () => fmt.quantity(c!.trailing_deals));
  when(c !== undefined, B.creationMonths.id, () => fmt.quantity(c!.trailing_ramped_ae_months));
  when(c !== undefined, B.creationWindow.id, () => c!.window);

  // the month table: every month, past then forward
  const months = rc.months ?? [];
  const mRow = (i: number) => `${RC}/months/${i}`;
  many(B.mMonth.id, months.map((m) => fmt.month(m.month)), months.map((_, i) => mRow(i)));
  many(B.mKind.id, months.map((m) => m.kind), months.map((_, i) => mRow(i)));
  many(B.mHeads.id, months.map((m) => fmt.quantity(m.heads)), months.map((_, i) => mRow(i)));
  many(B.mRamped.id, months.map((m) => fmt.quantity(m.ramped)), months.map((_, i) => mRow(i)));
  many(B.mDepartures.id, months.map((m) => fmt.quantity(m.departures)), months.map((_, i) => mRow(i)));
  many(B.mTarget.id, months.map((m) => (m.headcount_target === null ? "no target" : fmt.quantity(m.headcount_target))), months.map((_, i) => mRow(i)));

  // stated limits: the roster's, then the quota's
  const limits: Array<[string, string]> = [
    ...rc.limitations.map((t, i) => [`${RC}/limitations/${i}`, t] as [string, string]),
    ...r.quota_productivity.limits.map((t, i) => [`${QP}/limits/${i}`, t] as [string, string]),
  ];
  many(B.limit.id, limits.map(([, t]) => t), limits.map(([row]) => row));

  const periodLabels = months.map((m) => fmt.month(m.month));
  return { expected, absent, periodLabels };
}
