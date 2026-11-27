# Forecast tieout: engine/data-v2/sprout-labs

As of **2026-08-31**, fiscal year FY26 (2026-02-01 to 2027-01-31). One money measure throughout: new-business ARR bookings (type = new_business, the arr column).
Profile `engine/config/profiles/sprout-labs`. Fit: matured snapshots. Ranges from 2000 simulated draws, seed 0, drawing deal outcomes only.

## 1. Reconciliation

871 rows in `deals.csv` (ARR $69,666,093.00); 871 new-business rows included, 0 excluded.

New-business bookings fiscal year to date: **$3,931,144.00**.

| Month | Bookings |
|---|---|
| 2026-02 | $107,277.00 |
| 2026-03 | $452,268.00 |
| 2026-04 | $397,099.00 |
| 2026-05 | $805,949.00 |
| 2026-06 | $1,294,824.00 |
| 2026-07 | $549,410.00 |
| 2026-08 | $324,317.00 |

Pipeline flow, fiscal-year start to as-of (current amounts):

|  | Deals | ARR |
|---|---|---|
| open at fiscal-year start | 75 | $4,890,701.00 |
| created | 274 | $24,597,596.00 |
| won | 39 | $3,931,144.00 |
| lost | 229 | $19,612,159.00 |
| open at as-of | 81 | $5,944,994.00 |

| Check | Result | Detail |
|---|---|---|
| rows partition | pass | 871 included + 0 excluded = 871 of 871 source rows |
| arr partition | pass | included + excluded arr = 69666093 against source total 69666093 (0 rows had no readable arr) |
| bookings tie to source | pass | source file new-business won FYTD 3931144 = included 3931144 + excluded rows 0 |
| pipeline flow | pass | open at FY start 4890701 + created 24597596 = won 3931144 + lost 19612159 + open now 5944994 |

## 2. What the history can support

871 new-business deals, first created 2024-02-01 (30 months before the as-of date); 790 closed outcomes; 19 monthly snapshots old enough to score a full horizon.

What cannot be reconstructed or relied on:

- stage_history.csv records stage changes only: it holds no past deal amounts and no past expected close dates
- deal_observations.csv supplies past amounts and expected close dates (3006 observations); a deal's state on a past date is its latest observation on or before that date
- 15 deals have no stage history, so they never appear in a win-rate snapshot; 4 of them are open: today's forecasts use their current stage from deals.csv, but at past cutoffs their stage is unknown and back-test folds leave them out
- win rates learn only from snapshots at least 365 days old, so a change in conversion shows up a year late (the recency fit was not adopted: mean absolute error not lower at both 1 and 3 months (1m: 140,113 vs 96,781; 3m: 299,207 vs 269,872))
- the model is pooled across segments; a segment split is not evaluated in this report
- roles on team_members.csv: ae 8, founder 2, sdr 2, se 1; the capacity term is adopted (created-pipeline error with realized staffing: 3 months 1,130,288 against 2,448,980 (53.9% lower); 6 months 1,624,304 against 6,001,442 (72.9% lower); ramped AE-months varied 93%)
- team_members.csv holds no history of role, segment, quota or deal ownership: today's values stand in for every past date, and a deal's owner is its current owner

## 3. Three forecasts, side by side

| Method | Part | 2026-09 | 2026-10 | 2026-11 | 2026-12 | 2027-01 | 2027-02 | 2027-03 | 2027-04 | 2027-05 | 2027-06 | 2027-07 | 2027-08 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trailing run-rate | run-rate | $478,430 | $494,378 | $478,430 | $494,378 | $494,378 | $446,535 | $494,378 | $478,430 | $494,378 | $478,430 | $494,378 | $494,378 | $5,820,902 |
| stage-weighted pipeline | existing pipeline | $498,457 | $304,863 | $137,208 | $48,580 | $0 | $0 | $0 | $0 | $0 | $0 | $0 | $0 | $989,108 |
| stage-weighted pipeline | future pipeline | $0 | $0 | $0 | $73,465 | $253,046 | $228,558 | $253,046 | $244,884 | $253,046 | $244,884 | $253,046 | $253,046 | $2,057,022 |
| fitted model | existing pipeline | $270,729 | $303,097 | $375,092 | $293,354 | $164,365 | $104,973 | $79,767 | $28,612 | $0 | $3,933 | $0 | $25,577 | $1,649,499 |
| fitted model | future pipeline | $0 | $36,535 | $130,497 | $251,946 | $363,166 | $394,373 | $455,132 | $454,632 | $477,771 | $459,956 | $465,763 | $461,847 | $3,951,620 |

Two windows:

| Method | rest of fiscal year (2026-09 to 2027-01) | next twelve months (2026-09 to 2027-08) |
|---|---|---|
| trailing run-rate | $2,439,995 | $5,820,902 |
| stage-weighted pipeline | $1,315,620 | $3,046,130 |
| fitted model | $2,188,781 | $5,601,118 |

Fitted-model ranges (1-month unvalidated (the coverage statistics read back-tested) (80% range held 88% of 16 folds); 3-month unvalidated (the coverage statistics read back-tested) (80% range held 93% of 14 folds); 6-month unvalidated (the coverage statistics read too narrow) (80% range held 45% of 11 folds)):

Months: simulated; see how the ranges were checked.

| Month | Median | 80% range | 95% range |
|---|---|---|---|
| 2026-09 | $252,387 | $128,024 to $417,549 | $81,599 to $502,224 |
| 2026-10 | $321,325 | $136,384 to $558,023 | $70,984 to $698,578 |
| 2026-11 | $496,954 | $239,524 to $825,944 | $149,574 to $1,040,902 |
| 2026-12 | $522,468 | $265,256 to $860,068 | $171,795 to $1,072,482 |
| 2027-01 | $497,589 | $238,691 to $842,796 | $131,344 to $1,048,105 |
| 2027-02 | $485,868 | $227,350 to $819,740 | $130,550 to $1,031,863 |
| 2027-03 | $509,186 | $245,959 to $880,736 | $153,059 to $1,092,624 |
| 2027-04 | $454,610 | $213,969 to $768,212 | $110,447 to $996,898 |
| 2027-05 | $444,602 | $204,434 to $779,806 | $117,563 to $972,165 |
| 2027-06 | $438,120 | $191,995 to $757,330 | $94,278 to $948,582 |
| 2027-07 | $446,808 | $197,390 to $778,804 | $90,124 to $999,082 |
| 2027-08 | $463,228 | $208,141 to $782,093 | $109,978 to $990,728 |
| rest of fiscal year (unvalidated; 95%: simulated, not separately tested) | $2,154,154 | $1,669,685 to $2,742,742 | $1,420,186 to $3,091,625 |
| next twelve months (unvalidated; 95%: simulated, not separately tested) | $5,585,774 | $4,609,210 to $6,674,529 | $4,086,957 to $7,260,882 |

Assumptions:

- **trailing run-rate**: new-business bookings continue at the trailing 365-day rate of 15947.68 per day
- **stage-weighted pipeline**: open deals book at their amount times the profile's stage probability (stages.yaml), in the month of their expected close; past-due deals count in the first month; new pipeline is created at 102034.81 ARR per day (trailing 365 days) and converts at the Discovery probability 0.08, closing 113 days after creation (median cycle of 63 trailing wins)
- **fitted model**: open deals book at their current amount times the fitted win rate for their stage and age, on the fitted close-timing distribution; new pipeline is created at 8.1836 deals per ramped AE-month (trailing 365 days) times the expected ramped AE-months of the roster and wins at the fitted creation-cohort rate 0.1566, averaging 69645.61 ARR per win

## 4. Every rate once

Each rate has one definition, used everywhere it appears.

| Rate | Value | Numerator / denominator | Cohort | Horizon | n | Source |
|---|---|---|---|---|---|---|
| `win_within_horizon:S1` | 0.178862 (95%: 0.136-0.2316) | 44 won within 365 days / 246 deals open in S1 at their first matured snapshot | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 246 | fitted |
| `win_within_horizon:S2` | 0.325926 (95%: 0.2526-0.4089) | 44 won within 365 days / 135 deals open in S2 at their first matured snapshot | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 135 | fitted |
| `win_within_horizon:S3` | 0.444444 (95%: 0.3412-0.5527) | 36 won within 365 days / 81 deals open in S3 at their first matured snapshot | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 81 | fitted |
| `win_within_horizon:S4` | 0.703704 (95%: 0.5717-0.8086) | 38 won within 365 days / 54 deals open in S4 at their first matured snapshot | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 54 | fitted |
| `win_within_horizon:S5` | 0.878788 (95%: 0.7267-0.9518) | 29 won within 365 days / 33 deals open in S5 at their first matured snapshot | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 33 | fitted |
| `win_within_horizon:S1:0-90d` | 0.178862 | 44 won within 365 days (+20 x stage rate) / 246 deals open in S1 aged 0-90d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 246 | fitted |
| `win_within_horizon:S1:181d+` | 0.155532 | 0 won within 365 days (+20 x stage rate) / 3 deals open in S1 aged 181d+ at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 3 | fitted |
| `win_within_horizon:S1:91-180d` | 0.143089 | 0 won within 365 days (+20 x stage rate) / 5 deals open in S1 aged 91-180d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 5 | fitted |
| `win_within_horizon:S2:0-90d` | 0.323650 | 43 won within 365 days (+20 x stage rate) / 133 deals open in S2 aged 0-90d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 133 | fitted |
| `win_within_horizon:S2:181d+` | 0.271605 | 0 won within 365 days (+20 x stage rate) / 4 deals open in S2 aged 181d+ at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 4 | fitted |
| `win_within_horizon:S2:91-180d` | 0.284284 | 4 won within 365 days (+20 x stage rate) / 17 deals open in S2 aged 91-180d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 17 | fitted |
| `win_within_horizon:S3:0-90d` | 0.450418 | 33 won within 365 days (+20 x stage rate) / 73 deals open in S3 aged 0-90d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 73 | fitted |
| `win_within_horizon:S3:181d+` | 0.473430 | 2 won within 365 days (+20 x stage rate) / 3 deals open in S3 aged 181d+ at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 3 | fitted |
| `win_within_horizon:S3:91-180d` | 0.444444 | 12 won within 365 days (+20 x stage rate) / 27 deals open in S3 aged 91-180d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 27 | fitted |
| `win_within_horizon:S4:0-90d` | 0.681481 | 20 won within 365 days (+20 x stage rate) / 30 deals open in S4 aged 0-90d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 30 | fitted |
| `win_within_horizon:S4:181d+` | 0.717813 | 1 won within 365 days (+20 x stage rate) / 1 deals open in S4 aged 181d+ at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 1 | fitted |
| `win_within_horizon:S4:91-180d` | 0.695389 | 20 won within 365 days (+20 x stage rate) / 29 deals open in S4 aged 91-180d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 29 | fitted |
| `win_within_horizon:S5:0-90d` | 0.921799 | 11 won within 365 days (+20 x stage rate) / 11 deals open in S5 aged 0-90d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 11 | fitted |
| `win_within_horizon:S5:181d+` | 0.889807 | 2 won within 365 days (+20 x stage rate) / 2 deals open in S5 aged 181d+ at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 2 | fitted |
| `win_within_horizon:S5:91-180d` | 0.839394 | 16 won within 365 days (+20 x stage rate) / 20 deals open in S5 aged 91-180d at their first matured snapshot (+20) | monthly snapshots 2024-02-29 to 2025-08-31 | 365 days | 20 | fitted |
| `new_pipeline_win_rate` | 0.156584 (95%: 0.1188-0.2037) | 44 won within 365 days / 281 deals created | new-business deals created 2024-09-01 to 2025-08-31 | 365 days | 281 | fitted |
| `mean_won_arr` | 69645.613636 | booked ARR of those wins / 44 wins | new-business deals created 2024-09-01 to 2025-08-31 | 365 days | 44 | fitted |
| `mean_created_arr` | 75198.291815 | ARR of created deals / 281 deals with a known amount | new-business deals created 2024-09-01 to 2025-08-31 | at creation | 281 | fitted |
| `created_deals_per_day` | 1.213699 | 443 deals created / 365 days | created 2025-09-01 to 2026-08-31 | trailing | 443 | fitted |
| `trailing_bookings_per_day` | 15947.676712 | 5820902.00 ARR booked / 365 days | closed 2025-09-01 to 2026-08-31 | trailing | 63 | fitted |
| `stage_probability:S1` | 0.080000 | probability that a deal in Discovery is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S2` | 0.180000 | probability that a deal in Qualification is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S3` | 0.350000 | probability that a deal in Technical Evaluation is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S4` | 0.550000 | probability that a deal in Business Case is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S5` | 0.800000 | probability that a deal in Negotiation is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `created_arr_per_day` | 102034.805479 | 37242704.00 ARR created (first recorded amount) / 365 days | created 2025-09-01 to 2026-08-31 | trailing | 443 | fitted |
| `median_won_cycle_days` | 113 | median of days to close / 63 wins | closed 2025-09-01 to 2026-08-31 | trailing | 63 | fitted |
| `horizon_days` | 365 | days within which a win counts for a win rate |  |  | 0 | default |
| `smoothing_pseudo_observations` | 20 | pull of an age-group cell toward its stage rate |  |  | 0 | default |
| `min_timing_samples` | 20 | wins a stage needs for its own close timing |  |  | 0 | default |
| `trailing_days` | 365 | window for trailing rates |  |  | 0 | default |
| `recency_months` | 24 | trailing months of snapshots for the cumulative-incidence fit |  |  | 0 | default |
| `lever_cap_multiple` | 3 | cap on added pipeline, times trailing created pipeline |  |  | 0 | default |
| `simulation_draws` | 2000 | Monte Carlo draws behind the ranges |  |  | 0 | default |
| `ramp_weight:1` | 0.166700 | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 3 | entered |
| `ramp_weight:2` | 0.500000 | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 3 | entered |
| `ramp_weight:3` | 0.833300 | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 3 | entered |
| `attrition_per_ae_month` | 0.020000 | 2 departures / 109.6 AE-months employed | 2024-02-01 to 2026-08-31 | per AE-month | 2 | entered |
| `created_deals_per_ramped_ae_month` | 8.183581 | 443 deals created / 54.13 ramped AE-months | trailing 365 days to 2026-08-31 | per ramped AE-month | 443 | fitted |
| `loaded_cost_per_ae_month` | 12000 | cash cost of one AE for one month (capacity.yaml) | capacity.yaml | unstated | 0 | entered |
| `program_cost_per_dollar_of_pipeline` | 0.080000 | cash cost per dollar of program pipeline created (capacity.yaml) | capacity.yaml | unstated | 0 | entered |
| `program_ramp_months` | 3 | months a program takes to reach its full monthly pipeline | capacity.yaml | unstated | 0 | entered |
| `capacity_min_staffing_variation` | 0.200000 | ramped AE-months must vary by this much across the scored period for capacity to be testable |  |  | 0 | default |
| `capacity_min_improvement` | 0.100000 | capacity's created-pipeline error must be this much lower than the flat rate's at both horizons |  |  | 0 | default |
| `capacity_min_folds` | 6 | folds needed at each scored horizon |  |  | 0 | default |
| `days_per_ae_month` | 30.437500 | days in one AE-month |  |  | 0 | default |

## 5. The gap

Forecast: fitted model (expected value). Gap = target - actual - forecast (positive = short).

| Quarter | Status | Target | Actual | Forecast | Expected | Gap | Expected 80% range |
|---|---|---|---|---|---|---|---|
| Q1FY26 | closed | $1,600,000 | $956,644 | $0 | $956,644 | $643,356 | $956,644 to $956,644 |
| Q2FY26 | closed | $1,700,000 | $2,650,183 | $0 | $2,650,183 | -$950,183 | $2,650,183 to $2,650,183 |
| Q3FY26 | in progress | $2,100,000 | $324,317 | $610,361 | $934,678 | $1,165,322 | $696,162 to $1,170,600 |
| Q4FY26 | not started | $2,600,000 | $0 | $1,578,420 | $1,578,420 | $1,021,580 | $1,102,952 to $2,113,494 |

Fiscal year: target $8,000,000, actual to date $3,931,144, forecast rest of year $2,188,781, expected **$6,119,925** (80%: $5,600,829 to $6,673,886, simulated; 95%: $5,351,330 to $7,022,769, simulated, not separately tested), gap **$1,880,075**.

Next twelve months (2026-09 to 2027-08): quarters with a target ending in the window (Q3FY26, Q4FY26, through 2027-01-31): target $4,700,000, actual to date $324,317, forecast $2,188,781, gap **$2,186,902**.

2027-02 to 2027-08: forecast $3,412,337 (months outside a targeted quarter (targets end 2027-01-31): bookings alone).

**Pipeline to meet the fiscal-year total, spread evenly, new-business pipeline added: feasible: $43,153,974.81.** Schedule: added evenly across the 5 months to the target's end; cap $111,728,112 (3 times the new-business pipeline created in the trailing 365 days). Forecast without it $6,119,925, with it $8,000,000, against $8,000,000. Bookings gained at the required amount: rest of fiscal year $1,880,075; next twelve months $6,057,717.
_'feasible' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable._

**Pipeline to meet the next-twelve-months targets, spread evenly, new-business pipeline added: feasible: $50,196,674.45.** Schedule: added evenly across the 5 months to the target's end; cap $111,728,112 (3 times the new-business pipeline created in the trailing 365 days). Forecast without it $2,513,098, with it $4,700,000, against $4,700,000. Bookings gained at the required amount: rest of fiscal year $2,186,902; next twelve months $7,046,333.
_'feasible' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable._

## 6. Back-test

Scoring (declared before building): per horizon, mean absolute dollar error over all folds; 'yes' only if the fitted model's error is lower than both baselines at 1 and 3 months; under 6 folds is 'not enough history to say'.

| Horizon | Folds | Method | Mean abs. error | Signed bias | 80% coverage | 95% coverage |
|---|---|---|---|---|---|---|
| 1 mo | 16 | trailing run-rate | $216,742 | -$142,083 |  |  |
| 1 mo | 16 | stage-weighted pipeline | $389,134 | $389,134 |  |  |
| 1 mo | 16 | fitted model | $96,781 | -$31,063 | 88% | 100% |
| 3 mo | 14 | trailing run-rate | $567,903 | -$567,903 |  |  |
| 3 mo | 14 | stage-weighted pipeline | $287,967 | -$144,344 |  |  |
| 3 mo | 14 | fitted model | $269,872 | $5,596 | 93% | 100% |
| 6 mo | 11 | trailing run-rate | $1,053,349 | -$1,053,349 |  |  |
| 6 mo | 11 | stage-weighted pipeline | $1,041,745 | -$1,041,745 |  |  |
| 6 mo | 11 | fitted model | $585,444 | $37,546 | 45% | 64% |

Recency candidate (cumulative incidence) against the Goal 1 fit (matured snapshots), same folds. Rule: adopted only if the fitted model's mean absolute error is lower than the Goal 1 fit's at both 1 and 3 months, on the same folds (at least 6 at each).

| Horizon | Folds | matured snapshots | cumulative incidence |
|---|---|---|---|
| 1m | 16 | $96,781 | $140,113 |
| 3m | 14 | $269,872 | $299,207 |

**Not adopted**: mean absolute error not lower at both 1 and 3 months (1m: 140,113 vs 96,781; 3m: 299,207 vs 269,872). The forecast, rates, ranges and verdict use the matured snapshots fit.

Ranges stretched by the model's own past misses. Rule: adopted if there are at least 6 scored folds at 1 and at 3 months, pooled 80% coverage over 1 and 3 months is closer to 80% than the simulated range's on the same folds, and no horizon (1, 3 or 6 months) moves more than 10 points further from 80%; each side's factor is the smallest, never below 1, that would have put at least 90% of the eligible past folds inside on that side (a fold is eligible once its whole horizon has ended; at least 5 are needed).

| Horizon | Eligible folds | Scored folds | Simulated 80% coverage | Stretched 80% coverage | Median 80% width, simulated | Median 80% width, stretched | Lower factor | Upper factor |
|---|---|---|---|---|---|---|---|---|
| 1 mo | 16 | 11 | 10 of 11 (91%) | 10 of 11 (91%) | $425,155 | $441,784 | 1.0000 | 1.0736 |
| 3 mo | 14 | 7 | 6 of 7 (86%) | 6 of 7 (86%) | $798,444 | $798,444 | 1.0000 | 1.0000 |
| 6 mo | 11 | 1 | 0 of 1 (0%) | 0 of 1 (0%) | $1,122,961 | $1,495,397 | 1.3272 | 1.9026 |

**Not adopted**: pooled over 1 and 3 months, 18 scored folds: simulated 16 held (89%), stretched 16 held (89%); the stretched coverage is not closer to 80%.

Method: Each side's factor is the ceil(90% of n)-th smallest of the factors the n eligible past forecasts would have needed: the plain empirical rule, not a finite-sample guarantee. Six-month factors come from overlapping forecasts (each shares five of its six months with its neighbors) and are noisier: 11 past six-month forecasts to learn from, 1 scored.

## 7. Verdicts

**The software is correct: yes.** 22 of 22 self-checks passed (runtime self-checks on this report's own numbers; the arithmetic is also checked on hand-calculated fixtures by the test suite (pytest engine/tests/tieout_core)).

| Check | Result | Detail |
|---|---|---|
| rows partition | pass | 871 included + 0 excluded = 871 of 871 source rows |
| arr partition | pass | included + excluded arr = 69666093 against source total 69666093 (0 rows had no readable arr) |
| bookings tie to source | pass | source file new-business won FYTD 3931144 = included 3931144 + excluded rows 0 |
| pipeline flow | pass | open at FY start 4890701 + created 24597596 = won 3931144 + lost 19612159 + open now 5944994 |
| existing pipeline conserved | pass | open 5944994.00 = won in window 1649498.57 + won later 0.00 + not won 4295495.43 |
| lever agrees with forward function | pass | forward($43,153,974.81) = 8000000.0002 against target 8000000 |
| twelve-month lever agrees with forward function | pass | forward($50,196,674.45) = 4700000.0003 against target 4700000 |
| simulation centered on the expectation | pass | simulated mean 5,612,923.93 vs expected 5,601,118.09 (tolerance 72,157.75, 2000 draws) |
| forecast parts add up | pass | each method's total equals the sum of its months (largest difference 2.00E-21) |
| folds saw nothing after their cutoff | pass | 16 cutoffs rebuilt with as_known_at; each fold asserts its latest fact is on or before its cutoff |
| every rate defined once | pass | 51 rates in one registry |
| roster rows partition | pass | 8 quota-carrying + 5 other roles + 0 excluded = 13 of 13 roster rows |
| the forecast uses capacity exactly when it was adopted | pass | capacity decision: adopted; forecast uses the capacity term |
| wins credited plus unattributed equal bookings in the window | pass | 5559017.00 + 261885.00 = 5820902.00 against 5820902.00 |
| each solvable quarter meets its target under the schedules solved up to and including it | pass | 1 solvable quarters re-run through the forward function, each with the schedules solved up to and including its own; 1 unreachable checked against the cap, the cap left and the selling window |
| the completed schedule books each quarter's stated bookings and surplus over target | pass | 2 quarters rebuilt by adding each quarter's own schedule to the no-pipeline forecast |
| cents booked in each quarter, re-derived from the solved schedule, match the stated yield | pass | 1 solved schedules re-run on their own |
| lead-time yields match an independent forward run on a probe schedule, and the count shares sum to one | pass | 4 quarters checked on a $250,000 probe in two parts; win share 0.1566, not 0.8434 |
| plan contributions sum to the difference | pass | rest of fiscal year: 36261.69 = 2225042.53 - 2188780.84; next twelve months: 844156.36 = 6445274.45 - 5601118.09 |
| plan simulation centered on its expectation | pass | simulated mean 6,476,851.19 vs expected 6,445,274.46 (2000 draws) |
| hires solve returns the smallest whole number that closes the gap | pass | unreachable: None hires give 6230674.42 against 8000000 |
| program solve agrees with the forward function | pass | feasible: forward(58885194.74) = 8000000.00 against 8000000 |

**The forecast is better than the baselines: yes.** the model's mean absolute error is lower than both baselines at 1 and 3 months.

## 8. Roster and capacity

**Capacity term: adopted.** created-pipeline error with realized staffing: 3 months 1,130,288 against 2,448,980 (53.9% lower); 6 months 1,624,304 against 6,001,442 (72.9% lower); ramped AE-months varied 93%.

Scored on created-pipeline dollars at 3 and 6 months on the back-test's folds; the per-rep rate is fitted only from data before each cutoff and applied to the ramped AE-months that actually occurred. Conditional on realized staffing: it asks whether headcount explains pipeline, not how well it forecasts.
Declared rule: adopted only if ramped AE-months varied by at least 20% across the scored period, the capacity rate's mean absolute error is at least 10% lower than the flat trailing rate's at both 3 and 6 months, and there are at least 6 folds at each.
The forecast, gap, plan and actions use the the capacity term (ramped AE-months times created deals per ramped AE-month). An association in the history, not a promise: that a new hire adds pipeline at this rate is an assumption.

| Horizon | Folds | Flat trailing rate, mean abs. error | Capacity rate, mean abs. error | Improvement |
|---|---|---|---|---|
| 3 mo | 14 | $2,448,980 | $1,130,288 | 53.8% |
| 6 mo | 11 | $6,001,442 | $1,624,304 | 72.9% |

Ramped AE-months varied 93% across the scored period (2025-04-30 to 2026-08-31).

Roster: 13 rows; 8 quota-carrying people on file, 6 employed at the as-of date, 6.00 ramped equivalents, against a headcount target of 6 this month (monthly_ae_targets in targets.yaml: a comparison line only; it never creates a hire). 2 have left to date; 0 signed hires.

Counted, carrying no capacity: founder 2, sdr 2, se 1.

**Ramp (entered):** 3 reps observed from hire through their sixth month; 3 tenured reps alongside. created deals per rep by tenure month, relative to reps with twelve or more months' tenure in the same calendar month; 1 from the next tenure month on. Not fitted because 3 reps observed from hire through their sixth month; 8 are needed.

| Tenure month | Weight | 95% range |
|---|---|---|
| 1 | 0.1667 |  |
| 2 | 0.5000 |  |
| 3 | 0.8333 |  |

**Attrition (entered):** 0.02000 per AE-month, 2 departures over 109.6 AE-months; not fitted because 2 departures; 5 are needed to fit a rate. Forward: an expectation in the headline (a constant daily hazard from this monthly rate); a random draw in the ranges; nobody is back-filled unless the plan says so.

**Created deals per ramped AE-month:** 8.183581 (443 deals over 54.13 ramped AE-months, trailing 365 days to 2026-08-31).

Heads, ramped equivalents and departures by month (forward months are expectations):

| Month |  | Heads | Ramped | Departures | Headcount target |
|---|---|---|---|---|---|
| 2025-09 | past | 4 | 3.99 | 0 |  |
| 2025-10 | past | 3 | 3.94 | 1 |  |
| 2025-11 | past | 4 | 3.13 | 0 |  |
| 2025-12 | past | 4 | 3.42 | 0 |  |
| 2026-01 | past | 4 | 3.76 | 0 |  |
| 2026-02 | past | 4 | 3.96 | 0 | 4 |
| 2026-03 | past | 5 | 4.16 | 0 | 5 |
| 2026-04 | past | 6 | 4.64 | 0 | 6 |
| 2026-05 | past | 6 | 5.30 | 0 | 6 |
| 2026-06 | past | 6 | 5.81 | 0 | 6 |
| 2026-07 | past | 6 | 5.99 | 0 | 6 |
| 2026-08 | past | 6 | 6.00 | 0 | 6 |
| 2026-09 | forward | 5.9 | 5.94 | 0.12 | 6 |
| 2026-10 | forward | 5.8 | 5.82 | 0.12 | 6 |
| 2026-11 | forward | 5.6 | 5.70 | 0.11 | 6 |
| 2026-12 | forward | 5.5 | 5.59 | 0.12 | 6 |
| 2027-01 | forward | 5.4 | 5.47 | 0.11 | 6 |
| 2027-02 | forward | 5.3 | 5.37 | 0.10 |  |
| 2027-03 | forward | 5.2 | 5.26 | 0.11 |  |
| 2027-04 | forward | 5.1 | 5.16 | 0.10 |  |
| 2027-05 | forward | 5.0 | 5.06 | 0.10 |  |
| 2027-06 | forward | 4.9 | 4.95 | 0.10 |  |
| 2027-07 | forward | 4.8 | 4.86 | 0.10 |  |
| 2027-08 | forward | 4.7 | 4.76 | 0.10 |  |

Limits:

- team_members.csv records no history of role, segment, quota or deal ownership: today's values stand in for every past date
- a deal's owner is its current owner, not necessarily the person who created it
- people who left the company before the first deal in the files are not on the roster

## 9. Quota against observed productivity

Wins credited to the owner on deals.csv and closed while that person was employed, over annual quota prorated by days employed in the window (trailing 365 days to 2026-08-31). Observed, never model output.

| Segment | Reps | Prorated quota | Wins credited | Attainment | Across reps employed 180+ days (min / p25 / median / p75 / max) |
|---|---|---|---|---|---|
| commercial | 4 | $3,994,521 | $1,955,398 | 49% | 6% / 17% / 28% / 64% / 100% |
| mid_market | 3 | $4,454,795 | $3,603,619 | 81% | 62% / 78% / 94% / 110% / 126% |
| all reps | 7 | $8,449,315 | $5,559,017 | 66% | 6% / 28% / 62% / 100% / 126% |

Wins in the window $5,820,902: credited $5,559,017, unattributed $261,885 (wins whose owner is not on the roster, or who had left or not yet started on the close date).

Total quota $10,500,000 for 6 people over a target of $8,000,000: **1.31x** (full-ramp annual quotas of the quota-carrying people employed on the as-of date (signed hires excluded) over the fiscal year's bookings target).

Limits:

- the owner is the deal's current owner and the quota is today's annual quota, standing in for their history
- quota is a full-ramp annual figure; ramp is not prorated out of it

## 10. Required against expected pipeline, by quarter

One deterministic solve in quarter order; each quarter's pipeline is created evenly on every day from the day after the as-of date to its end (creation starts now), and meets that quarter's target given its actual bookings, the pipeline already open and what earlier quarters were assigned; an unreachable quarter is assigned nothing. Pipeline assigned to a later quarter is also created in the earlier quarters' months, so it can only add to them. Forward function: the capacity term. Cap: $111,728,112 (one cap across the quarters: three times the new-business pipeline created in the trailing 365 days, less what earlier quarters were assigned).

**The requirement.**

| Quarter | Target | Actual | Created between | Result | Cents booked in the quarter per dollar created | Bookings without own pipeline | Bookings under the completed schedule | Surplus over target |
|---|---|---|---|---|---|---|---|---|
| Q3FY26 | $2,100,000 | $324,317 | 2026-08-31 to 2026-10-31 | unreachable within the cap (it would take $234,427,525.59) | 0.50c | $934,678 | $983,756 | -$1,116,244 |
| Q4FY26 | $2,600,000 | $0 | 2026-08-31 to 2027-01-31 | required: $24,763,697.22 | 4.13c | $1,578,420 | $2,600,000 | $0 |

**Against the team's record.** Everything created in the span includes what earlier quarters were assigned.

| Quarter | Extra pipeline required | Expected created | Earlier quarters' assignments in the span | Total created in the span | Per day | Against the team's best per day | Per ramped AE-month (the forecast's basis) | Against the team's best per ramped AE-month | Too late, and why |
|---|---|---|---|---|---|---|---|---|---|
| Q3FY26 | n/a | $7,249,650 | $0 | $241,677,175 | $3,961,921 | 39.64x | $20,514,926 | 28.11x | too late: over_cap; total_rate; per_rep |
| Q4FY26 | $24,763,697 | $17,643,128 | $0 | $42,406,826 | $277,169 | 2.77x | $1,479,148 | 2.03x | too late: total_rate; per_rep |

Too late, as a rule: a quarter is too late to fund with new pipeline when its requirement is over the cap (or the cap is used up, or no pipeline created in time can book inside it), or when everything created in its span (expected, earlier quarters' assignments and its own requirement) per day is above the team's best four-quarter average of total created pipeline per day, or, only where capacity is the forecast's basis, when that total per ramped AE-month is above the team's best; the reason names exactly the legs that fired. Per-ramped-AE-month comparison applies: capacity is the forecast's basis, so the team's best per ramped AE-month is a third leg beside the cap and the total rate.

**Q3FY26: too late to fund with new pipeline: this quarter depends on the pipeline already open.** Why: the requirement is over the cap; needs $3,961,920.91 of pipeline created a day in total, above the team's best four-quarter average of $99,946.49 a day; needs $20,514,926 per ramped AE-month, above the team's best four-quarter average of $729,930. The open pipeline ($5,944,994) is expected to book $573,825 inside the quarter; to close it, $1,739,148 of the open pipeline would have to book inside the quarter (29.3% of its dollars) against the 9.7% expected (arithmetic on the figures above, not a lever the model solves).

**Q4FY26: too late to fund with new pipeline: this quarter depends on the pipeline already open.** Why: needs $277,168.79 of pipeline created a day in total, above the team's best four-quarter average of $99,946.49 a day; needs $1,479,148 per ramped AE-month, above the team's best four-quarter average of $729,930. The open pipeline ($5,944,994) is expected to book $832,811 inside the quarter; to close it, $1,854,391 of the open pipeline would have to book inside the quarter (31.2% of its dollars) against the 14.0% expected (arithmetic on the figures above, not a lever the model solves).

**Lead time: of a dollar of pipeline created next month (at its first recorded amount), the cents booked by the end of each of the next four quarters** (created 2026-08-31 to 2026-09-30; the production forward function's own timing, on a probe dollar-amount created evenly through the month; independent of the capacity decision. These are dollar yields, not probabilities: amounts change between creation and win, so they can exceed or fall short of what the deal counts imply and are not forced to sum to one).

| Quarter | Cents booked inside the quarter | Cents booked by its end |
|---|---|---|
| Q3FY26 | 1.00c | 1.00c |
| Q4FY26 | 9.04c | 10.04c |
| Q1FY27 | 3.47c | 13.51c |
| Q2FY27 | 0.66c | 14.17c |
| After the fourth quarter | 0.33c |  |

Count outcome, of the deals created, from the fit in use; counts, so these sum to one: 15.7% expected to win within the horizon, 84.3% not.

Fiscal year, pipeline to meet every remaining quarter's target: **partial: 1 of 2 quarters solvable (unreachable: Q3FY26); $24,763,697.22 covers only the solvable ones; too late to fund with new pipeline: Q3FY26, Q4FY26**. Section 5's pipeline to meet the fiscal-year total, spread evenly to year end (section 5): feasible: $43,153,974.81. Meeting every quarter's own target is stricter than meeting the year's total: a quarter that is ahead cannot lend its surplus to one that is behind, and pipeline created in a quarter mostly books after it.

The team's own record (10 complete quarters, created pipeline dollars per ramped AE-month): median $722,768, best four-quarter average $729,930; best four-quarter average of total created pipeline $99,946 a day. Observed over the complete fiscal quarters in the files, with today's roster and ramp; fewer than four quarters has no four-quarter average.

_'required' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable. Expected pipeline is what the forward function in use creates; the ramped AE-months beside it are the roster's expected ones._

## 11. The plan

Plan file `engine/config/profiles/sprout-labs/plan.yaml`. Hires first, then programs, each in the plan file's order; each contribution is the extra bookings from adding that item to everything above it, so they sum to the difference. Baseline: the roster as signed and nothing planned.

| Item | What |  | Adds, rest of fiscal year | Adds, next twelve months | Cash cost in twelve months |
|---|---|---|---|---|---|
| 1 Mid Market hire from 2026-10 | 1 AE(s), segment Mid Market, starting 2026-10-01 | valued | $23,444 | $455,601 | $118,413 |
| 1 Commercial hire from 2026-12 | 1 AE(s), segment Commercial, starting 2026-12-01 | valued | $1,103 | $305,179 | $98,809 |
| Partner referrals | $600,000 of created pipeline from 2026-10 | valued | $11,715 | $83,377 | $48,000 |

| Bookings | rest of fiscal year | next twelve months |
|---|---|---|
| Baseline | $2,188,780.84 | $5,601,118.09 |
| With the plan | $2,225,042.53 | $6,445,274.45 |
| Difference | $36,261.69 | $844,156.36 |
| Sum of the contributions | $36,261.69 | $844,156.36 |

Fiscal-year gap: $1,880,075 before the plan, **$1,843,813** with it (target $8,000,000, actual to date $3,931,144).

Twelve-month gap (against the quarters with a target that end in the window; later months are bookings alone): $2,186,902 before, **$2,150,640** with the plan.

Cash cost of the plan in the twelve months: $265,222 (hires at loaded cost per AE-month over expected months employed; programs at their cost, paid in step with the pipeline they create (or on the plan's own payment schedule), counting only what falls inside the twelve months).

Bookings with the plan, simulated (unvalidated: these ranges include the plan and the capacity term; they have not been back-tested; 2000 draws, drawing deal outcomes, future departures, with the planned hires and program pipeline in the scenario):

| Window | Median | 80% range | 95% range |
|---|---|---|---|
| rest of fiscal year | $2,195,898 | $1,688,587 to $2,793,152 | $1,434,514 to $3,149,219 |
| next twelve months | $6,456,096 | $5,367,968 to $7,586,268 | $4,888,062 to $8,212,518 |

Fiscal-year expected with the plan, 80% range: $5,619,731 to $6,724,296.

## 12. Two actions, compared

Two unit actions through the same forward function, the roster as signed: hire one AE starting 2026-09-01; add $1,000,000 of program pipeline starting 2026-09-01. Gain per dollar is the bookings gained in the next twelve months over the cash cost inside the same twelve months. An action starts paying in the first month it adds at least 1% of its twelve-month gain. Program shape: created from 2026-09 to the fiscal-year end, ramping up over the entered ramp (3 months unless capacity.yaml says otherwise).

| Action | Rank | Gains, rest of fiscal year | Gains, next twelve months | Starts paying | Cash cost inside the twelve months | Gain per dollar |
|---|---|---|---|---|---|---|
| Hire one AE starting 2026-09-01 | 1 | $55,375 | $530,581 | 2026-11 | $127,964 | 4.15 |
| Add $1,000,000 of program pipeline starting 2026-09-01 | 2 | $31,928 | $139,780 | 2026-11 | $80,000 | 1.75 |

Closing the fiscal-year gap of $1,880,075: the baseline forecast (the roster as signed, nothing planned), each action alone.

- **Hires:** unreachable within the bound of 2 (the most the company has started in one fiscal quarter); the best case gives $6,230,674.
- **Program pipeline:** feasible: $58,885,194.74 of created pipeline closes it (overshoot $0.00); cash cost $4,710,816; 3% of those dollars book by the fiscal-year end.

_'feasible' means achievable inside the model's bounds, not operationally achievable; that a new hire adds pipeline at the fitted rate is an assumption._
