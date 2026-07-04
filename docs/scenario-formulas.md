# Scenario Formulas Specification

These formulas are the contract between the Python engine and the TypeScript
scenario adapter. Both must produce identical results when given identical
inputs. The shared golden vectors in
`tests/parity/fixtures/scenario-golden-vectors.json` define the executable
tolerance policy: integers/counts are exact; floats use
`max(absoluteEpsilon, relativeEpsilon * max(1, abs(expected)))`, currently
`absoluteEpsilon = 1e-6` and `relativeEpsilon = 1e-9`.

## Pipeline Rollforward (Weighted Projection)

For each open deal:
```
expected_value = deal.metric_value × stage_win_rate[deal.stage]
```

Total projection:
```
total_expected = SUM(expected_value for each open deal)
```

## Capacity-Based Projection

For each month:
```
capacity_bookings = ae_count × productivity_per_ae × ramp_factor
```

Where:
- `ae_count` = number of quota-carrying AEs active in that month
- `productivity_per_ae` = observed or configured monthly productivity
- `ramp_factor` = blended ramp percentage (1.0 for fully ramped team)

## Scenario Override Application

When a user overrides a stage win rate:
```
adjusted_expected = deal.metric_value × override_rate[deal.stage]
gap_delta = adjusted_total - baseline_total
```

When a user overrides AE count:
```
adjusted_capacity = override_ae_count × productivity_per_ae × ramp_factor
```

## Snapshot Scenario Planner

The public Scenario Planner runs from the snapshot's
`scenario_building_blocks`. Months with `monthly_is_actual = true` are locked:
their expected, capped, AE creation, MQL creation, capacity, and AE count values
come directly from the snapshot.

Projected months start at the first `monthly_is_actual = false` entry.

Baseline pipeline created:
```
monthly_pipeline_created = monthly_ae_creation + monthly_mql_creation
```

AE seat overrides create incremental AE cohorts. A quarter-level `addAes`
cohort starts at the first month in that quarter. Month-level
`aeMonthTargets` create the additional cohorts needed to reach the requested
total AE count, never below the snapshot baseline and never below the prior
edited month. New cohorts contribute from their start month forward:
```
extra_ae_creation =
  productivity_per_ae_per_month
  × added_ae_count
  × ramp_factor(months_since_cohort_start)
  × s0_to_s1
  × s1_to_s2
  × avg_deal_size

extra_capacity = capacity_per_ae × added_ae_count × ramp_factor
extra_ae_count = added_ae_count
```

Funnel overrides scale projected pipeline creation for the affected quarter:
```
ae_factor = avg_deal_size × s0_to_s1 × s1_to_s2
mql_factor = mql_to_s0 × ae_factor

ae_creation *= effective_ae_factor / baseline_ae_factor
mql_creation *= (effective_mql_factor / baseline_mql_factor)
                × max(0, 1 + mql_change_pct)
```

If a baseline factor is zero, the corresponding scale is `1.0`.

Changes to future pipeline creation become future wins by applying the
snapshot's `future_generation_win_rates` and stacking through the snapshot's
`decay_curve`:
```
creation_delta = adjusted_pipeline_created - baseline_pipeline_created
win_adjusted_delta = creation_delta × future_generation_win_rate[month]
future_wins_delta = stack_cohorts(win_adjusted_delta, decay_curve)
monthly_future_wins = baseline_future_wins + future_wins_delta
```

The monthly expected forecast is:
```
monthly_expected = monthly_inventory_wins + monthly_future_wins
```

Monthly capacity caps expected bookings with overflow carried forward:
```
available = monthly_expected + prior_overflow
monthly_capped = min(available, monthly_capacity)
monthly_overflow = max(0, available - monthly_capacity)
```

Fiscal-year totals are full-precision sums of the monthly series:
```
fy_expected = SUM(monthly_expected)
fy_capped = SUM(monthly_capped)
```

## Rounding

All intermediate calculations use full floating-point precision.
Final display values are rounded to the nearest integer (for currency)
or 1 decimal place (for percentages).

## Edge Cases

- Deal with null/zero amount: treated as $0 in projection (contributes nothing)
- Deal with stage not in stage_win_rates: uses 0% win rate
- Empty deal list: total_expected = 0
- No-op override (rate matches baseline): output must equal baseline exactly
- Zero pipeline, capacity, AE count, or win rate inputs remain zero unless an
  explicit override creates projected-month pipeline.
- Missing `overridable_quarters` or invalid/missing `quarter_by_month` means no
  quarter overrides apply.
- Overrides never mutate actual months.
