# Forecast tieout: engine/data-v2/sapling-industries

As of **2026-08-31**, fiscal year FY26 (2026-02-01 to 2027-01-31). One money measure throughout: new-business ARR bookings (type = new_business, the arr column).
Profile `engine/config/profiles/sapling-industries`. Fit: cumulative incidence. Ranges from 2000 simulated draws, seed 0, drawing deal outcomes only.

## 1. Reconciliation

1335 rows in `deals.csv` (ARR $509,616,229.00); 1252 new-business rows included, 83 excluded.

New-business bookings fiscal year to date: **$29,699,760.00**.

| Month | Bookings |
|---|---|
| 2026-02 | $2,143,610.00 |
| 2026-03 | $3,107,297.00 |
| 2026-04 | $3,365,758.00 |
| 2026-05 | $5,473,845.00 |
| 2026-06 | $3,743,138.00 |
| 2026-07 | $4,337,298.00 |
| 2026-08 | $7,528,814.00 |

Pipeline flow, fiscal-year start to as-of (current amounts):

|  | Deals | ARR |
|---|---|---|
| open at fiscal-year start | 128 | $46,644,255.00 |
| created | 401 | $163,677,459.00 |
| won | 81 | $29,699,760.00 |
| lost | 288 | $112,733,453.00 |
| open at as-of | 160 | $67,888,501.00 |

Other motions, reconciled separately and excluded:

| Motion | Rows | ARR | Won FYTD |
|---|---|---|---|
| expansion | 83 | $12,561,691.00 | $1,769,215.00 |

| Check | Result | Detail |
|---|---|---|
| rows partition | pass | 1252 included + 83 excluded = 1335 of 1335 source rows |
| arr partition | pass | included + excluded arr = 509616229 against source total 509616229 (0 rows had no readable arr) |
| bookings tie to source | pass | source file new-business won FYTD 29699760 = included 29699760 + excluded rows 0 |
| pipeline flow | pass | open at FY start 46644255 + created 163677459 = won 29699760 + lost 112733453 + open now 67888501 |

Excluded rows by reason:

| Reason | Rows |
|---|---|
| excluded motion: expansion | 83 |

<details><summary>Every excluded row</summary>

| Row | Deal | Reason | ARR |
|---|---|---|---|
| 13 | SAP-00012 | excluded motion: expansion | $81,779.00 |
| 18 | SAP-00017 | excluded motion: expansion | $75,274.00 |
| 20 | SAP-00019 | excluded motion: expansion | $140,039.00 |
| 41 | SAP-00040 | excluded motion: expansion | $318,550.00 |
| 42 | SAP-00041 | excluded motion: expansion | $190,620.00 |
| 44 | SAP-00043 | excluded motion: expansion | $245,724.00 |
| 53 | SAP-00052 | excluded motion: expansion | $133,096.00 |
| 64 | SAP-00063 | excluded motion: expansion | $198,582.00 |
| 88 | SAP-00087 | excluded motion: expansion | $62,907.00 |
| 122 | SAP-00121 | excluded motion: expansion | $129,006.00 |
| 123 | SAP-00122 | excluded motion: expansion | $45,299.00 |
| 125 | SAP-00124 | excluded motion: expansion | $98,999.00 |
| 136 | SAP-00135 | excluded motion: expansion | $99,496.00 |
| 147 | SAP-00146 | excluded motion: expansion | $154,217.00 |
| 167 | SAP-00166 | excluded motion: expansion | $327,593.00 |
| 193 | SAP-00192 | excluded motion: expansion | $292,386.00 |
| 194 | SAP-00193 | excluded motion: expansion | $117,114.00 |
| 197 | SAP-00196 | excluded motion: expansion | $224,414.00 |
| 198 | SAP-00197 | excluded motion: expansion | $52,528.00 |
| 223 | SAP-00222 | excluded motion: expansion | $151,845.00 |
| 249 | SAP-00248 | excluded motion: expansion | $78,209.00 |
| 266 | SAP-00265 | excluded motion: expansion | $236,523.00 |
| 270 | SAP-00269 | excluded motion: expansion | $188,732.00 |
| 275 | SAP-00274 | excluded motion: expansion | $166,113.00 |
| 297 | SAP-00296 | excluded motion: expansion | $349,145.00 |
| 316 | SAP-00315 | excluded motion: expansion | $178,102.00 |
| 321 | SAP-00320 | excluded motion: expansion | $99,383.00 |
| 322 | SAP-00321 | excluded motion: expansion | $195,915.00 |
| 323 | SAP-00322 | excluded motion: expansion | $202,892.00 |
| 343 | SAP-00342 | excluded motion: expansion | $108,533.00 |
| 361 | SAP-00360 | excluded motion: expansion | $130,294.00 |
| 365 | SAP-00364 | excluded motion: expansion | $149,449.00 |
| 389 | SAP-00388 | excluded motion: expansion | $73,918.00 |
| 391 | SAP-00390 | excluded motion: expansion | $243,485.00 |
| 395 | SAP-00394 | excluded motion: expansion | $209,542.00 |
| 407 | SAP-00406 | excluded motion: expansion | $83,521.00 |
| 420 | SAP-00419 | excluded motion: expansion | $62,611.00 |
| 425 | SAP-00424 | excluded motion: expansion | $165,626.00 |
| 446 | SAP-00445 | excluded motion: expansion | $223,126.00 |
| 447 | SAP-00446 | excluded motion: expansion | $156,435.00 |
| 485 | SAP-00484 | excluded motion: expansion | $128,768.00 |
| 486 | SAP-00485 | excluded motion: expansion | $42,442.00 |
| 494 | SAP-00493 | excluded motion: expansion | $248,579.00 |
| 498 | SAP-00497 | excluded motion: expansion | $262,572.00 |
| 512 | SAP-00511 | excluded motion: expansion | $144,887.00 |
| 524 | SAP-00523 | excluded motion: expansion | $138,863.00 |
| 566 | SAP-00565 | excluded motion: expansion | $156,595.00 |
| 570 | SAP-00569 | excluded motion: expansion | $55,851.00 |
| 591 | SAP-00590 | excluded motion: expansion | $183,671.00 |
| 607 | SAP-00606 | excluded motion: expansion | $492,364.00 |
| 608 | SAP-00607 | excluded motion: expansion | $42,899.00 |
| 620 | SAP-00619 | excluded motion: expansion | $128,396.00 |
| 625 | SAP-00624 | excluded motion: expansion | $363,707.00 |
| 633 | SAP-00632 | excluded motion: expansion | $85,439.00 |
| 640 | SAP-00639 | excluded motion: expansion | $141,044.00 |
| 662 | SAP-00661 | excluded motion: expansion | $102,272.00 |
| 663 | SAP-00662 | excluded motion: expansion | $54,098.00 |
| 674 | SAP-00673 | excluded motion: expansion | $308,712.00 |
| 710 | SAP-00709 | excluded motion: expansion | $104,699.00 |
| 714 | SAP-00713 | excluded motion: expansion | $79,762.00 |
| 744 | SAP-00743 | excluded motion: expansion | $115,329.00 |
| 761 | SAP-00760 | excluded motion: expansion | $256,201.00 |
| 778 | SAP-00777 | excluded motion: expansion | $171,269.00 |
| 783 | SAP-00782 | excluded motion: expansion | $91,577.00 |
| 793 | SAP-00792 | excluded motion: expansion | $57,409.00 |
| 795 | SAP-00794 | excluded motion: expansion | $108,758.00 |
| 820 | SAP-00819 | excluded motion: expansion | $64,842.00 |
| 821 | SAP-00820 | excluded motion: expansion | $159,223.00 |
| 843 | SAP-00842 | excluded motion: expansion | $112,949.00 |
| 846 | SAP-00845 | excluded motion: expansion | $220,449.00 |
| 852 | SAP-00851 | excluded motion: expansion | $68,076.00 |
| 860 | SAP-00859 | excluded motion: expansion | $54,579.00 |
| 881 | SAP-00880 | excluded motion: expansion | $130,150.00 |
| 935 | SAP-00934 | excluded motion: expansion | $94,313.00 |
| 982 | SAP-00981 | excluded motion: expansion | $216,608.00 |
| 1085 | SAP-01084 | excluded motion: expansion | $33,396.00 |
| 1097 | SAP-01096 | excluded motion: expansion | $121,831.00 |
| 1124 | SAP-01123 | excluded motion: expansion | $109,108.00 |
| 1183 | SAP-01182 | excluded motion: expansion | $168,201.00 |
| 1189 | SAP-01188 | excluded motion: expansion | $80,745.00 |
| 1253 | SAP-01253 | excluded motion: expansion | $64,808.00 |
| 1285 | SAP-01286 | excluded motion: expansion | $291,672.00 |
| 1289 | SAP-01290 | excluded motion: expansion | $63,556.00 |

</details>

## 2. What the history can support

1252 new-business deals, first created 2024-02-01 (30 months before the as-of date); 1092 closed outcomes; 24 monthly snapshots old enough to score a full horizon.

What cannot be reconstructed or relied on:

- stage_history.csv records stage changes only: it holds no past deal amounts and no past expected close dates
- deal_observations.csv supplies past amounts and expected close dates (4738 observations); a deal's state on a past date is its latest observation on or before that date
- 12 deals have no stage history, so they never appear in a win-rate snapshot; 3 of them are open: today's forecasts use their current stage from deals.csv, but at past cutoffs their stage is unknown and back-test folds leave them out
- win rates use snapshots from the trailing 24 months, young ones counted only for the days observed (the recency fit was adopted: lower mean absolute error at 1 and 3 months (1m: 998,999 vs 1,384,619; 3m: 1,944,676 vs 2,261,995))
- the model is pooled across segments; a segment split is not evaluated in this report
- roles on team_members.csv: ae 49, manager 3, sdr 6, se 5, vp_sales 1; the capacity term is adopted (created-pipeline error with realised staffing: 3 months 6,601,779 against 13,010,602 (49.3% lower); 6 months 9,102,642 against 26,549,427 (65.7% lower); ramped AE-months varied 61%)
- team_members.csv holds no history of role, segment, quota or deal ownership: today's values stand in for every past date, and a deal's owner is its current owner

## 3. Three forecasts, side by side

| Method | Part | 2026-09 | 2026-10 | 2026-11 | 2026-12 | 2027-01 | 2027-02 | 2027-03 | 2027-04 | 2027-05 | 2027-06 | 2027-07 | 2027-08 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trailing run-rate | run-rate | $3,863,293 | $3,992,069 | $3,863,293 | $3,992,069 | $3,992,069 | $3,605,740 | $3,992,069 | $3,863,293 | $3,992,069 | $3,863,293 | $3,992,069 | $3,992,069 | $47,003,397 |
| stage-weighted pipeline | existing pipeline | $9,953,952 | $2,102,901 | $751,542 | $1,058,695 | $0 | $0 | $0 | $0 | $0 | $0 | $0 | $0 | $13,867,089 |
| stage-weighted pipeline | future pipeline | $0 | $0 | $0 | $319,999 | $1,239,996 | $1,119,997 | $1,239,996 | $1,199,996 | $1,239,996 | $1,199,996 | $1,239,996 | $1,239,996 | $10,039,969 |
| fitted model | existing pipeline | $5,608,756 | $4,676,417 | $4,438,776 | $3,116,632 | $2,531,562 | $1,681,280 | $838,267 | $802,951 | $394,302 | $28,999 | $203,472 | $68,110 | $24,389,525 |
| fitted model | future pipeline | $911 | $206,399 | $1,198,456 | $2,669,351 | $3,942,704 | $4,452,535 | $5,759,679 | $6,027,717 | $6,658,104 | $6,736,607 | $7,198,712 | $7,432,306 | $52,283,482 |

Two windows:

| Method | rest of fiscal year (2026-09 to 2027-01) | next twelve months (2026-09 to 2027-08) |
|---|---|---|
| trailing run-rate | $19,702,794 | $47,003,397 |
| stage-weighted pipeline | $15,427,084 | $23,907,058 |
| fitted model | $28,389,964 | $76,673,007 |

Fitted-model ranges (1-month unvalidated (the coverage statistics read back-tested) (80% range held 94% of 16 folds); 3-month unvalidated (the coverage statistics read back-tested) (80% range held 86% of 14 folds); 6-month unvalidated (the coverage statistics read back-tested) (80% range held 100% of 11 folds)):

| Month | Median | 80% range | 95% range |
|---|---|---|---|
| 2026-09 | $5,544,060 | $3,388,877 to $7,850,931 | $2,461,072 to $9,023,987 |
| 2026-10 | $4,776,322 | $2,618,029 to $7,557,706 | $1,683,009 to $9,831,916 |
| 2026-11 | $5,222,954 | $2,935,354 to $8,897,492 | $1,998,915 to $11,728,357 |
| 2026-12 | $5,513,395 | $2,847,767 to $9,102,439 | $1,971,807 to $11,770,805 |
| 2027-01 | $5,981,682 | $3,159,502 to $9,902,809 | $2,037,668 to $12,465,811 |
| 2027-02 | $5,775,000 | $2,915,839 to $9,680,486 | $2,013,375 to $12,760,221 |
| 2027-03 | $6,200,801 | $3,188,126 to $10,249,052 | $2,090,255 to $12,590,304 |
| 2027-04 | $6,515,842 | $3,371,328 to $10,621,658 | $2,113,069 to $12,909,084 |
| 2027-05 | $6,826,337 | $3,624,464 to $11,181,912 | $2,429,950 to $13,541,104 |
| 2027-06 | $6,472,968 | $3,213,156 to $10,511,318 | $2,190,545 to $13,232,718 |
| 2027-07 | $7,126,705 | $3,902,520 to $11,396,015 | $2,734,483 to $14,173,094 |
| 2027-08 | $7,181,820 | $3,935,230 to $11,694,179 | $2,529,702 to $14,474,253 |
| rest of fiscal year (unvalidated) | $28,122,170 | $22,636,891 to $34,387,378 | $20,285,726 to $38,339,258 |
| next twelve months (unvalidated) | $76,393,742 | $65,680,445 to $88,236,076 | $60,433,871 to $94,448,822 |

Assumptions:

- **trailing run-rate**: new-business bookings continue at the trailing 365-day rate of 128776.43 per day
- **stage-weighted pipeline**: open deals book at their amount times the profile's stage probability (stages.yaml), in the month of their expected close; past-due deals count in the first month; new pipeline is created at 666664.59 ARR per day (trailing 365 days) and converts at the Discovery probability 0.06, closing 114 days after creation (median cycle of 129 trailing wins)
- **fitted model**: open deals book at their current amount times the fitted win rate for their stage and age, on the fitted close-timing distribution; new pipeline is created at 2.0662 deals per ramped AE-month (trailing 365 days) times the expected ramped AE-months of the roster and wins at the fitted creation-cohort rate 0.2193, averaging 413835.73 ARR per win

## 4. Every rate once

Each rate has one definition, used everywhere it appears.

| Rate | Value | Numerator / denominator | Cohort | Horizon | n | Source |
|---|---|---|---|---|---|---|
| `win_within_horizon:S1` | 0.199064 (95%: 0.1655-0.2375) | 92 wins observed within 365 days / 571 deals open in S1 at their first snapshot in the trailing 24 months (73 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 571 | fitted |
| `win_within_horizon:S2` | 0.356861 (95%: 0.3079-0.409) | 121 wins observed within 365 days / 396 deals open in S2 at their first snapshot in the trailing 24 months (53 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 396 | fitted |
| `win_within_horizon:S3` | 0.520496 (95%: 0.4579-0.5824) | 128 wins observed within 365 days / 280 deals open in S3 at their first snapshot in the trailing 24 months (33 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 280 | fitted |
| `win_within_horizon:S4` | 0.681807 (95%: 0.6087-0.747) | 119 wins observed within 365 days / 185 deals open in S4 at their first snapshot in the trailing 24 months (12 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 185 | fitted |
| `win_within_horizon:S5` | 0.842262 (95%: 0.7559-0.902) | 79 wins observed within 365 days / 96 deals open in S5 at their first snapshot in the trailing 24 months (2 still open at the cutoff) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 96 | fitted |
| `win_within_horizon:S1:0-90d` | 0.199852 | 92 wins observed within 365 days (+20 x stage rate) / 569 deals open in S1 aged 0-90d (469.0 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 569 | fitted |
| `win_within_horizon:S1:181d+` | 0.202799 | 2 wins observed within 365 days (+20 x stage rate) / 15 deals open in S1 aged 181d+ (9.3 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 15 | fitted |
| `win_within_horizon:S1:91-180d` | 0.206441 | 5 wins observed within 365 days (+20 x stage rate) / 32 deals open in S1 aged 91-180d (22.1 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 32 | fitted |
| `win_within_horizon:S2:0-90d` | 0.357043 | 114 wins observed within 365 days (+20 x stage rate) / 373 deals open in S2 aged 0-90d (321.7 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 373 | fitted |
| `win_within_horizon:S2:181d+` | 0.260821 | 3 wins observed within 365 days (+20 x stage rate) / 22 deals open in S2 aged 181d+ (18.9 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 22 | fitted |
| `win_within_horizon:S2:91-180d` | 0.311559 | 20 wins observed within 365 days (+20 x stage rate) / 75 deals open in S2 aged 91-180d (66.9 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 75 | fitted |
| `win_within_horizon:S3:0-90d` | 0.552818 | 103 wins observed within 365 days (+20 x stage rate) / 213 deals open in S3 aged 0-90d (184.6 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 213 | fitted |
| `win_within_horizon:S3:181d+` | 0.480818 | 10 wins observed within 365 days (+20 x stage rate) / 27 deals open in S3 aged 181d+ (20.6 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 27 | fitted |
| `win_within_horizon:S3:91-180d` | 0.433097 | 37 wins observed within 365 days (+20 x stage rate) / 106 deals open in S3 aged 91-180d (87.2 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 106 | fitted |
| `win_within_horizon:S4:0-90d` | 0.719256 | 62 wins observed within 365 days (+20 x stage rate) / 91 deals open in S4 aged 0-90d (80.1 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 91 | fitted |
| `win_within_horizon:S4:181d+` | 0.600573 | 17 wins observed within 365 days (+20 x stage rate) / 33 deals open in S4 aged 181d+ (30.3 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 33 | fitted |
| `win_within_horizon:S4:91-180d` | 0.668733 | 60 wins observed within 365 days (+20 x stage rate) / 97 deals open in S4 aged 91-180d (88.8 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 97 | fitted |
| `win_within_horizon:S5:0-90d` | 0.865004 | 29 wins observed within 365 days (+20 x stage rate) / 33 deals open in S5 aged 0-90d (33.0 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 33 | fitted |
| `win_within_horizon:S5:181d+` | 0.853992 | 20 wins observed within 365 days (+20 x stage rate) / 24 deals open in S5 aged 181d+ (22.2 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 24 | fitted |
| `win_within_horizon:S5:91-180d` | 0.808719 | 43 wins observed within 365 days (+20 x stage rate) / 54 deals open in S5 aged 91-180d (54.0 effective after censoring, +20) | monthly snapshots 2024-08-31 to 2026-07-31 | 365 days | 54 | fitted |
| `new_pipeline_win_rate` | 0.219306 (95%: 0.1928-0.2483) | 181 wins observed within 365 days / 1068 deals created (158 still open at the cutoff) | new-business deals created 2024-09-01 to 2026-08-31 | 365 days | 1068 | fitted |
| `mean_won_arr` | 413835.730063 | booked ARR of those wins / 181 wins observed | new-business deals created 2024-09-01 to 2026-08-31 | 365 days | 181 | fitted |
| `mean_created_arr` | 391508.998127 | ARR of created deals / 1068 deals with a known amount | new-business deals created 2024-09-01 to 2026-08-31 | at creation | 1068 | fitted |
| `created_deals_per_day` | 1.726027 | 630 deals created / 365 days | created 2025-09-01 to 2026-08-31 | trailing | 630 | fitted |
| `trailing_bookings_per_day` | 128776.430137 | 47003397.00 ARR booked / 365 days | closed 2025-09-01 to 2026-08-31 | trailing | 129 | fitted |
| `stage_probability:S1` | 0.060000 | probability that a deal in Discovery is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S2` | 0.140000 | probability that a deal in Qualification is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S3` | 0.280000 | probability that a deal in Technical Evaluation is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S4` | 0.520000 | probability that a deal in Business Case is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `stage_probability:S5` | 0.780000 | probability that a deal in Negotiation is won (stages.yaml) | stages.yaml | unstated | 0 | entered |
| `created_arr_per_day` | 666664.594521 | 243332577.00 ARR created (first recorded amount) / 365 days | created 2025-09-01 to 2026-08-31 | trailing | 630 | fitted |
| `median_won_cycle_days` | 114 | median of days to close / 129 wins | closed 2025-09-01 to 2026-08-31 | trailing | 129 | fitted |
| `horizon_days` | 365 | days within which a win counts for a win rate |  |  | 0 | default |
| `smoothing_pseudo_observations` | 20 | pull of an age-group cell toward its stage rate |  |  | 0 | default |
| `min_timing_samples` | 20 | wins a stage needs for its own close timing |  |  | 0 | default |
| `trailing_days` | 365 | window for trailing rates |  |  | 0 | default |
| `recency_months` | 24 | trailing months of snapshots for the cumulative-incidence fit |  |  | 0 | default |
| `lever_cap_multiple` | 3 | cap on added pipeline, times trailing created pipeline |  |  | 0 | default |
| `simulation_draws` | 2000 | Monte Carlo draws behind the ranges |  |  | 0 | default |
| `ramp_weight:1` | 0.277881 (95%: 0.1747-0.4421) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:2` | 0.339297 (95%: 0.2131-0.5403) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:3` | 0.442781 (95%: 0.2943-0.6661) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:4` | 0.531655 (95%: 0.367-0.7703) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:5` | 0.514862 (95%: 0.3329-0.7962) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:6` | 0.615784 (95%: 0.4292-0.8835) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:7` | 0.759918 (95%: 0.5379-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:8` | 0.593009 (95%: 0.3934-0.8939) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:9` | 0.753191 (95%: 0.5192-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:10` | 0.850006 (95%: 0.5964-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `ramp_weight:11` | 1 (95%: 1.0-1.0) | deals created by reps in this tenure month / deals the same reps would have created at the tenured reps' rate in the same calendar months | reps observed 2024-02-01 to 2026-08-31 | per tenure month | 21 | fitted |
| `attrition_per_ae_month` | 0.007268 (95%: 0.0023-0.017) | 5 departures / 687.9 AE-months employed | 2024-02-01 to 2026-08-31 | per AE-month | 5 | fitted |
| `created_deals_per_ramped_ae_month` | 2.066174 | 630 deals created / 304.91 ramped AE-months | trailing 365 days to 2026-08-31 | per ramped AE-month | 630 | fitted |
| `loaded_cost_per_ae_month` | 14000 | cash cost of one AE for one month (capacity.yaml) | capacity.yaml | unstated | 0 | entered |
| `programme_cost_per_dollar_of_pipeline` | 0.060000 | cash cost per dollar of programme pipeline created (capacity.yaml) | capacity.yaml | unstated | 0 | entered |
| `programme_ramp_months` | 3 | months a programme takes to reach its full monthly pipeline | capacity.yaml | unstated | 0 | entered |
| `capacity_min_staffing_variation` | 0.200000 | ramped AE-months must vary by this much across the scored period for capacity to be testable |  |  | 0 | default |
| `capacity_min_improvement` | 0.100000 | capacity's created-pipeline error must be this much lower than the flat rate's at both horizons |  |  | 0 | default |
| `capacity_min_folds` | 6 | folds needed at each scored horizon |  |  | 0 | default |
| `days_per_ae_month` | 30.437500 | days in one AE-month |  |  | 0 | default |

## 5. The gap

Forecast: fitted model (expected value). Gap = target - actual - forecast (positive = short).

| Quarter | Status | Target | Actual | Forecast | Expected | Gap | Expected 80% range |
|---|---|---|---|---|---|---|---|
| Q1FY26 | closed | $10,000,000 | $8,616,665 | $0 | $8,616,665 | $1,383,335 | $8,616,665 to $8,616,665 |
| Q2FY26 | closed | $13,000,000 | $13,554,281 | $0 | $13,554,281 | -$554,281 | $13,554,281 to $13,554,281 |
| Q3FY26 | in progress | $17,000,000 | $7,528,814 | $10,492,483 | $18,021,297 | -$1,021,297 | $15,267,195 to $21,014,585 |
| Q4FY26 | not started | $20,000,000 | $0 | $17,897,482 | $17,897,482 | $2,102,518 | $12,461,322 to $23,521,983 |

Fiscal year: target $60,000,000, actual to date $29,699,760, forecast rest of year $28,389,964, expected **$58,089,724** (80%: $52,336,651 to $64,087,138; 95%: $49,985,486 to $68,039,018), gap **$1,910,276**.

Next twelve months (2026-09 to 2027-08): quarters with a target ending in the window (Q3FY26, Q4FY26, through 2027-01-31): target $37,000,000, actual to date $7,528,814, forecast $28,389,964, gap **$1,081,222**.

2027-02 to 2027-08: forecast $48,283,043 (months outside a targeted quarter (targets end 2027-01-31): bookings alone).

**Pipeline to meet the fiscal-year total, spread evenly, new-business pipeline added: feasible: $32,444,653.50.** Schedule: added evenly across the 5 months to the target's end; cap $729,997,731 (3 times the new-business pipeline created in the trailing 365 days). Forecast without it $58,089,724, with it $60,000,000, against $60,000,000. Bookings gained at the required amount: rest of fiscal year $1,910,276; next twelve months $7,215,264.
_'feasible' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable._

**Pipeline to meet the next-twelve-months targets, spread evenly, new-business pipeline added: feasible: $18,363,769.99.** Schedule: added evenly across the 5 months to the target's end; cap $729,997,731 (3 times the new-business pipeline created in the trailing 365 days). Forecast without it $35,918,778, with it $37,000,000, against $37,000,000. Bookings gained at the required amount: rest of fiscal year $1,081,222; next twelve months $4,083,861.
_'feasible' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable._

## 6. Back-test

Scoring (declared before building): per horizon, mean absolute dollar error over all folds; 'yes' only if the fitted model's error is lower than both baselines at 1 and 3 months; under 6 folds is 'not enough history to say'.

| Horizon | Folds | Method | Mean abs. error | Signed bias | 80% coverage | 95% coverage |
|---|---|---|---|---|---|---|
| 1 mo | 16 | trailing run-rate | $1,260,351 | -$417,073 |  |  |
| 1 mo | 16 | stage-weighted pipeline | $3,922,262 | $3,892,978 |  |  |
| 1 mo | 16 | fitted model | $998,998 | $705,649 | 94% | 100% |
| 3 mo | 14 | trailing run-rate | $1,942,333 | -$1,190,396 |  |  |
| 3 mo | 14 | stage-weighted pipeline | $1,776,756 | -$1,048,949 |  |  |
| 3 mo | 14 | fitted model | $1,944,676 | $1,121,574 | 86% | 100% |
| 6 mo | 11 | trailing run-rate | $2,211,456 | -$2,019,937 |  |  |
| 6 mo | 11 | stage-weighted pipeline | $9,849,823 | -$9,849,823 |  |  |
| 6 mo | 11 | fitted model | $1,489,985 | $1,086,856 | 100% | 100% |

Recency candidate (cumulative incidence) against the Goal 1 fit (matured snapshots), same folds. Rule: adopted only if the fitted model's mean absolute error is lower than the Goal 1 fit's at both 1 and 3 months, on the same folds (at least 6 at each).

| Horizon | Folds | matured snapshots | cumulative incidence |
|---|---|---|---|
| 1m | 16 | $1,384,619 | $998,998 |
| 3m | 14 | $2,261,995 | $1,944,676 |

**Adopted**: lower mean absolute error at 1 and 3 months (1m: 998,999 vs 1,384,619; 3m: 1,944,676 vs 2,261,995). The forecast, rates, ranges and verdict use the cumulative incidence fit.

## 7. Verdicts

**The software is correct: yes.** 22 of 22 self-checks passed (runtime self-checks on this report's own numbers; the arithmetic is also checked on hand-calculated fixtures by the test suite (pytest engine/tests/tieout_core)).

| Check | Result | Detail |
|---|---|---|
| rows partition | pass | 1252 included + 83 excluded = 1335 of 1335 source rows |
| arr partition | pass | included + excluded arr = 509616229 against source total 509616229 (0 rows had no readable arr) |
| bookings tie to source | pass | source file new-business won FYTD 29699760 = included 29699760 + excluded rows 0 |
| pipeline flow | pass | open at FY start 46644255 + created 163677459 = won 29699760 + lost 112733453 + open now 67888501 |
| existing pipeline conserved | pass | open 67888501.00 = won in window 24389524.96 + won later 0.00 + not won 43498976.04 |
| lever agrees with forward function | pass | forward($32,444,653.50) = 60000000.0003 against target 60000000 |
| twelve-month lever agrees with forward function | pass | forward($18,363,769.99) = 37000000.0006 against target 37000000 |
| simulation centred on the expectation | pass | simulated mean 76,717,596.17 vs expected 76,673,006.81 (tolerance 791,742.07, 2000 draws) |
| forecast parts add up | pass | each method's total equals the sum of its months (largest difference 1.00E-20) |
| folds saw nothing after their cutoff | pass | 16 cutoffs rebuilt with as_known_at; each fold asserts its latest fact is on or before its cutoff |
| every rate defined once | pass | 59 rates in one registry |
| roster rows partition | pass | 49 quota-carrying + 15 other roles + 0 excluded = 64 of 64 roster rows |
| the forecast uses capacity exactly when it was adopted | pass | capacity decision: adopted; forecast uses the capacity term |
| wins credited plus unattributed equal bookings in the window | pass | 43252317.00 + 3751080.00 = 47003397.00 against 47003397.00 |
| each solvable quarter meets its target under the schedules solved up to and including it | pass | 2 solvable quarters re-run through the forward function, each with the schedules solved up to and including its own; 0 unreachable checked against the cap, the cap left and the selling window |
| the completed schedule books each quarter's stated bookings and surplus over target | pass | 2 quarters rebuilt by adding each quarter's own schedule to the no-pipeline forecast |
| cents booked in each quarter, re-derived from the solved schedule, match the stated yield | pass | 1 solved schedules re-run on their own |
| lead-time yields match an independent forward run on a probe schedule, and the count shares sum to one | pass | 4 quarters checked on a $250,000 probe in two parts; win share 0.2193, not 0.7807 |
| plan contributions sum to the difference | pass | rest of fiscal year: 235289.18 = 28625253.47 - 28389964.29; next twelve months: 2979488.19 = 79652495.00 - 76673006.81 |
| plan simulation centred on its expectation | pass | simulated mean 79,512,355.48 vs expected 79,652,494.98 (2000 draws) |
| hires solve returns the smallest whole number that closes the gap | pass | unreachable: None hires give 58872158.49 against 60000000 |
| programme solve agrees with the forward function | pass | feasible: forward(45404741.70) = 60000000.00 against 60000000 |

**The forecast is better than the baselines: no.** the model's mean absolute error is not lower than every baseline: 3m: model 1,944,676 vs trailing run-rate 1,942,333; 3m: model 1,944,676 vs stage-weighted pipeline 1,776,756.

## 8. Roster and capacity

**Capacity term: adopted.** created-pipeline error with realised staffing: 3 months 6,601,779 against 13,010,602 (49.3% lower); 6 months 9,102,642 against 26,549,427 (65.7% lower); ramped AE-months varied 61%.

Scored on created-pipeline dollars at 3 and 6 months on the back-test's folds; the per-rep rate is fitted only from data before each cutoff and applied to the ramped AE-months that actually occurred. Conditional on realised staffing: it asks whether headcount explains pipeline, not how well it forecasts.
Declared rule: adopted only if ramped AE-months varied by at least 20% across the scored period, the capacity rate's mean absolute error is at least 10% lower than the flat trailing rate's at both 3 and 6 months, and there are at least 6 folds at each.
The forecast, gap, plan and actions use the the capacity term (ramped AE-months times created deals per ramped AE-month). An association in the history, not a promise: that a new hire adds pipeline at this rate is an assumption.

| Horizon | Folds | Flat trailing rate, mean abs. error | Capacity rate, mean abs. error | Improvement |
|---|---|---|---|---|
| 3 mo | 14 | $13,010,602 | $6,601,778 | 49.3% |
| 6 mo | 11 | $26,549,427 | $9,102,642 | 65.7% |

Ramped AE-months varied 61% across the scored period (2025-04-30 to 2026-08-31).

Roster: 64 rows; 49 quota-carrying people on file, 44 employed at the as-of date, 32.76 ramped equivalents, against a headcount target of 45 this month (monthly_ae_targets in targets.yaml: a comparison line only; it never creates a hire). 5 have left to date; 0 signed hires.

Counted, carrying no capacity: manager 3, sdr 6, se 5, vp_sales 1.

**Ramp (fitted):** 21 reps observed from hire through their sixth month; 27 tenured reps alongside. created deals per rep by tenure month, relative to reps with twelve or more months' tenure in the same calendar month; 1 from the next tenure month on. Limit: ownership on deals.csv says who owns a deal, not who made it: deals handed to a new rep count as that rep's, so a fitted ramp can read faster than the true one.

| Tenure month | Weight | 95% range |
|---|---|---|
| 1 | 0.2779 | 0.1747 to 0.4421 |
| 2 | 0.3393 | 0.2131 to 0.5403 |
| 3 | 0.4428 | 0.2943 to 0.6661 |
| 4 | 0.5317 | 0.3670 to 0.7703 |
| 5 | 0.5149 | 0.3329 to 0.7962 |
| 6 | 0.6158 | 0.4292 to 0.8835 |
| 7 | 0.7599 | 0.5379 to 1.0000 |
| 8 | 0.5930 | 0.3934 to 0.8939 |
| 9 | 0.7532 | 0.5192 to 1.0000 |
| 10 | 0.8500 | 0.5964 to 1.0000 |
| 11 | 1.0000 | a to t to   to t to h to e to   to c to e to i to l to i to n to g to   to ( to 1 to ) |

**Attrition (fitted):** 0.00727 per AE-month, 5 departures over 687.9 AE-months (95%: 0.00234 to 0.01696). Forward: an expectation in the headline (a constant daily hazard from this monthly rate); a random draw in the ranges; nobody is back-filled unless the plan says so.

**Created deals per ramped AE-month:** 2.066174 (630 deals over 304.91 ramped AE-months, trailing 365 days to 2026-08-31).

Heads, ramped equivalents and departures by month (forward months are expectations):

| Month |  | Heads | Ramped | Departures | Headcount target |
|---|---|---|---|---|---|
| 2025-09 | past | 26 | 20.29 | 0 |  |
| 2025-10 | past | 26 | 21.26 | 0 |  |
| 2025-11 | past | 25 | 21.59 | 1 |  |
| 2025-12 | past | 26 | 22.53 | 0 |  |
| 2026-01 | past | 26 | 23.21 | 0 |  |
| 2026-02 | past | 30 | 24.80 | 0 | 30 |
| 2026-03 | past | 30 | 25.05 | 0 | 30 |
| 2026-04 | past | 30 | 25.75 | 0 | 30 |
| 2026-05 | past | 36 | 28.04 | 0 | 36 |
| 2026-06 | past | 36 | 29.42 | 0 | 36 |
| 2026-07 | past | 35 | 30.15 | 1 | 36 |
| 2026-08 | past | 44 | 32.81 | 1 | 45 |
| 2026-09 | forward | 22.8 | 32.52 | 0.16 | 45 |
| 2026-10 | forward | 22.7 | 34.26 | 0.17 | 45 |
| 2026-11 | forward | 23.5 | 36.17 | 0.17 | 45 |
| 2026-12 | forward | 23.3 | 35.89 | 0.17 | 45 |
| 2027-01 | forward | 27.0 | 37.03 | 0.20 | 45 |
| 2027-02 | forward | 26.8 | 38.63 | 0.18 |  |
| 2027-03 | forward | 26.6 | 38.32 | 0.20 |  |
| 2027-04 | forward | 32.1 | 38.96 | 0.22 |  |
| 2027-05 | forward | 31.8 | 39.74 | 0.24 |  |
| 2027-06 | forward | 31.6 | 40.72 | 0.23 |  |
| 2027-07 | forward | 40.6 | 40.76 | 0.29 |  |
| 2027-08 | forward | 40.3 | 40.46 | 0.30 |  |

Limits:

- team_members.csv records no history of role, segment, quota or deal ownership: today's values stand in for every past date
- a deal's owner is its current owner, not necessarily the person who created it
- people who left the company before the first deal in the files are not on the roster

## 9. Quota against observed productivity

Wins credited to the owner on deals.csv and closed while that person was employed, over annual quota prorated by days employed in the window (trailing 365 days to 2026-08-31). Observed, never model output.

| Segment | Reps | Prorated quota | Wins credited | Attainment | Across reps employed 180+ days (min / p25 / median / p75 / max) |
|---|---|---|---|---|---|
| commercial | 18 | $9,872,877 | $4,034,672 | 41% | 0% / 25% / 52% / 64% / 78% |
| enterprise | 13 | $30,097,534 | $25,149,215 | 84% | 0% / 20% / 56% / 73% / 250% |
| mid_market | 16 | $18,414,247 | $14,068,430 | 76% | 0% / 40% / 84% / 115% / 143% |
| all reps | 47 | $58,384,658 | $43,252,317 | 74% | 0% / 26% / 57% / 82% / 250% |

Wins in the window $47,003,397: credited $43,252,317, unattributed $3,751,080 (wins whose owner is not on the roster, or who had left or not yet started on the close date).

Total quota $79,300,000 for 44 people over a target of $60,000,000: **1.32x** (full-ramp annual quotas of the quota-carrying people employed on the as-of date (signed hires excluded) over the fiscal year's bookings target).

Limits:

- the owner is the deal's current owner and the quota is today's annual quota, standing in for their history
- quota is a full-ramp annual figure; ramp is not prorated out of it

## 10. Required against expected pipeline, by quarter

One deterministic solve in quarter order; each quarter's pipeline is created evenly on every day from the day after the as-of date to its end (creation starts now), and meets that quarter's target given its actual bookings, the pipeline already open and what earlier quarters were assigned; an unreachable quarter is assigned nothing. Pipeline assigned to a later quarter is also created in the earlier quarters' months, so it can only add to them. Forward function: the capacity term. Cap: $729,997,731 (one cap across the quarters: three times the new-business pipeline created in the trailing 365 days, less what earlier quarters were assigned).

**The requirement.**

| Quarter | Target | Actual | Created between | Result | Cents booked in the quarter per dollar created | Bookings without own pipeline | Bookings under the completed schedule | Surplus over target |
|---|---|---|---|---|---|---|---|---|
| Q3FY26 | $17,000,000 | $7,528,814 | 2026-08-31 to 2026-10-31 | already covered | 0.39c | $18,021,297 | $18,079,240 | $1,079,240 |
| Q4FY26 | $20,000,000 | $0 | 2026-08-31 to 2027-01-31 | required: $36,979,070.55 | 5.69c | $17,897,482 | $20,000,000 | $0 |

**Against the team's record.** Everything created in the span includes what earlier quarters were assigned.

| Quarter | Extra pipeline required | Expected created | Earlier quarters' assignments in the span | Total created in the span | Per day | Against the team's best per day | Per ramped AE-month (the forecast's basis) | Against the team's best per ramped AE-month | Too late, and why |
|---|---|---|---|---|---|---|---|---|---|
| Q3FY26 | n/a | $54,157,915 | $0 | n/a | n/a | n/a | n/a | n/a | no |
| Q4FY26 | $36,979,071 | $143,078,682 | $0 | $180,057,753 | $1,176,848 | 1.85x | $1,017,995 | 0.98x | too late: total_rate |

Too late, as a rule: a quarter is too late to fund with new pipeline when its requirement is over the cap (or the cap is used up, or no pipeline created in time can book inside it), or when everything created in its span (expected, earlier quarters' assignments and its own requirement) per day is above the team's best four-quarter average of total created pipeline per day, or, only where capacity is the forecast's basis, when that total per ramped AE-month is above the team's best; the reason names exactly the legs that fired. Per-ramped-AE-month comparison applies: capacity is the forecast's basis, so the team's best per ramped AE-month is a third leg beside the cap and the total rate.

**Q4FY26: too late to fund with new pipeline: this quarter depends on the pipeline already open.** Why: needs $1,176,848.06 of pipeline created a day in total, above the team's best four-quarter average of $635,022.36 a day. The open pipeline ($67,888,501) is expected to book $10,086,970 inside the quarter; to close it, $12,189,489 of the open pipeline would have to book inside the quarter (18.0% of its dollars) against the 14.9% expected (arithmetic on the figures above, not a lever the model solves).

**Lead time: of a dollar of pipeline created next month (at its first recorded amount), the cents booked by the end of each of the next four quarters** (created 2026-08-31 to 2026-09-30; the production forward function's own timing, on a probe dollar-amount created evenly through the month; independent of the capacity decision. These are dollar yields, not probabilities: amounts change between creation and win, so they can exceed or fall short of what the deal counts imply and are not forced to sum to one).

| Quarter | Cents booked inside the quarter | Cents booked by its end |
|---|---|---|
| Q3FY26 | 0.79c | 0.79c |
| Q4FY26 | 13.19c | 13.98c |
| Q1FY27 | 6.81c | 20.79c |
| Q2FY27 | 2.09c | 22.88c |
| After the fourth quarter | 0.30c |  |

Count outcome, of the deals created, from the fit in use; counts, so these sum to one: 21.9% expected to win within the horizon, 78.1% not.

Fiscal year, pipeline to meet every remaining quarter's target: **$36,979,070.55 of extra pipeline to meet every remaining quarter's target; too late to fund with new pipeline: Q4FY26**. Section 5's pipeline to meet the fiscal-year total, spread evenly to year end (section 5): feasible: $32,444,653.50. Meeting every quarter's own target is stricter than meeting the year's total: a quarter that is ahead cannot lend its surplus to one that is behind, and pipeline created in a quarter mostly books after it.

The team's own record (10 complete quarters, created pipeline dollars per ramped AE-month): median $883,376, best four-quarter average $1,033,547; best four-quarter average of total created pipeline $635,022 a day. Observed over the complete fiscal quarters in the files, with today's roster and ramp; fewer than four quarters has no four-quarter average.

_'required' means achievable inside the model's bounds (fitted conversion and timing, the cap above), not operationally achievable. Expected pipeline is what the forward function in use creates; the ramped AE-months beside it are the roster's expected ones._

## 11. The plan

Plan file `engine/config/profiles/sapling-industries/plan.yaml`. Hires first, then programmes, each in the plan file's order; each contribution is the extra bookings from adding that item to everything above it, so they sum to the difference. Baseline: the roster as signed and nothing planned.

| Item | What |  | Adds, rest of fiscal year | Adds, next twelve months | Cash cost in twelve months |
|---|---|---|---|---|---|
| 2 mid_market hires from 2026-10 | 2 AE(s), segment mid_market, starting 2026-10-01 | valued | $76,526 | $1,191,484 | $296,014 |
| 1 enterprise hire from 2026-11 | 1 AE(s), segment enterprise, starting 2026-11-01 | valued | $12,822 | $482,884 | $135,057 |
| Partner referrals | $6,000,000 of created pipeline from 2026-10 | valued | $145,941 | $1,305,120 | $360,000 |

| Bookings | rest of fiscal year | next twelve months |
|---|---|---|
| Baseline | $28,389,964.29 | $76,673,006.81 |
| With the plan | $28,625,253.47 | $79,652,495.00 |
| Difference | $235,289.18 | $2,979,488.19 |
| Sum of the contributions | $235,289.18 | $2,979,488.19 |

Fiscal-year gap: $1,910,276 before the plan, **$1,674,987** with it (target $60,000,000, actual to date $29,699,760).

Twelve-month gap (against the quarters with a target that end in the window; later months are bookings alone): $1,081,222 before, **$845,933** with the plan.

Cash cost of the plan in the twelve months: $791,071 (hires at loaded cost per AE-month over expected months employed; programmes at their cost, paid in step with the pipeline they create (or on the plan's own payment schedule), counting only what falls inside the twelve months).

Bookings with the plan, simulated (unvalidated: these ranges include the plan and the capacity term; they have not been back-tested; 2000 draws, drawing deal outcomes, future departures, with the planned hires and programme pipeline in the scenario):

| Window | Median | 80% range | 95% range |
|---|---|---|---|
| rest of fiscal year | $28,388,272 | $23,017,221 to $34,689,106 | $20,371,999 to $38,373,386 |
| next twelve months | $79,366,302 | $68,152,070 to $91,075,753 | $62,832,308 to $98,109,085 |

Fiscal-year expected with the plan, 80% range: $52,716,981 to $64,388,866.

## 12. Two actions, compared

Two unit actions through the same forward function, the roster as signed: hire one AE starting 2026-09-01; add $1,000,000 of programme pipeline starting 2026-09-01. Gain per dollar is the bookings gained in the next twelve months over the cash cost inside the same twelve months. An action starts paying in the first month it adds at least 1% of its twelve-month gain. Programme shape: created from 2026-09 to the fiscal-year end, ramping up over the entered ramp (3 months unless capacity.yaml says otherwise).

| Action | Rank | Gains, rest of fiscal year | Gains, next twelve months | Starts paying | Cash cost inside the twelve months | Gain per dollar |
|---|---|---|---|---|---|---|
| Hire one AE starting 2026-09-01 | 1 | $78,243 | $717,971 | 2026-11 | $160,898 | 4.46 |
| Add $1,000,000 of programme pipeline starting 2026-09-01 | 2 | $42,072 | $220,271 | 2026-11 | $60,000 | 3.67 |

Closing the fiscal-year gap of $1,910,276: the baseline forecast (the roster as signed, nothing planned), each action alone.

- **Hires:** unreachable within the bound of 10 (the most the company has started in one fiscal quarter); the best case gives $58,872,158.
- **Programme pipeline:** feasible: $45,404,741.70 of created pipeline closes it (overshoot $0.00); cash cost $2,724,284; 4% of those dollars book by the fiscal-year end.

_'feasible' means achievable inside the model's bounds, not operationally achievable; that a new hire adds pipeline at the fitted rate is an assumption._
