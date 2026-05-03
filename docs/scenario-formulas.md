# Scenario Formulas Specification

These formulas are the contract between the Python engine and the TypeScript
scenario adapter. Both must produce identical results (within ±0.1% tolerance)
when given identical inputs.

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

## Rounding

All intermediate calculations use full floating-point precision.
Final display values are rounded to the nearest integer (for currency)
or 1 decimal place (for percentages).

## Edge Cases

- Deal with null/zero amount: treated as $0 in projection (contributes nothing)
- Deal with stage not in stage_win_rates: uses 0% win rate
- Empty deal list: total_expected = 0
- No-op override (rate matches baseline): output must equal baseline exactly
