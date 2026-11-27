# Changelog

## Unreleased: the rebuild

The app now runs on a new calculation core, and the old engine is retired (git tag
`pre-rebuild` is the archive).

### Added
- `engine/tieout_core`: one core that reads a company's deals, stage history and roster and writes a tied-out `report.json` and `report.md`: reconciliation to the source files, a fitted forecast with 80% and 95% ranges against two baselines, a back-test, the gap to target, capacity, required pipeline, a hiring and program plan, and two verdicts. Run it with `python -m engine.tieout_core report`.
- A declared report contract (`report.schema.json`, schema version 2.0.0) with cross-field rules, and generated TypeScript types.
- Four named scenarios per company (as signed, demo plan, hires only, program only), each a complete report computed by the core, with a core-computed comparison file.
- `engine/scripts/generate_app_reports.py`, with `--verify` that compares every generated file byte for byte; `generate_data_v2.py` with rebuilt demo data with about two and a half years of history.
- Five screens in place of nine: Forecast, Capacity, Pipeline, Plan and Trust, each answering one question and showing its error or its limits beside its number.
- A binding component, tests that check every bound value against an independent expectation, a stray-digit rule, chart-series checks, mutation tests, and a gate that finds arithmetic in `frontend/src`.
- Redirects from the old addresses: `/bookings` to `/forecast`; `/scenario` and `/targets` to `/plan`; `/inventory` and `/funnel` to `/pipeline`; `/audit`, `/methodology` and `/export` to `/trust`; `/capacity` is replaced in place. The old `?profile=` is read as the company.
- New README screenshots and Open Graph image captured from the new screens (`npm run screenshots`).
- CI runs `npm run verify` and both `--verify` commands.
- Ranges that hold what they claim (Goal 2D, schema version 2.3.0): the simulated 80% and 95% ranges can be stretched away from their median by a lower and an upper factor per tested horizon, each the smallest that would have put at least 90% of the eligible past forecasts inside on that side. A fold is eligible only once its whole horizon had ended; a back-test fold is scored with the factors known at its own date. The thresholds and the adoption rule were committed before any demo company was scored: Mighty Oak Holdings adopts it (pooled 80% coverage 39% simulated, 89% stretched); Sprout Labs and Sapling Industries do not (89% either way). Every range carries a label naming the factor horizon and whether its window was a tested shape (otherwise "extrapolated"); the report gives the decision, the scored dates, what the rule accepted (one-sided, six-month fold counts, floored at zero) and the method. With-plan ranges and every non-range figure are unchanged.
- The Forecast screen shows the label beside each range and how the ranges were checked; the Trust screen shows the decision with its evidence. Browser tests check that the wide tables render as tables at desktop widths.

### Changed
- American English throughout. The report contract changes with it (schema version 2.0.0): every key, plan file and the scenario id now say `program` (scenario `program-only`); no figure changed (every report compared before and after under the same renaming). Tests keep the old spellings out.
- The line under each company's name is generated from its as-signed report's statuses (year short of, on or ahead of target; whether headcount explains pipeline; whether the fitted forecast beats the simple baselines), in words with no figures; profiles carry no hand-written description.
- The "Is the fitted forecast better than the baselines?" card gives its reason in words and compares the back-test errors at one and three months for the fitted model and each baseline, with which is lower decided in the report (schema version 2.1.0). The report's own sentence stays in `report.json` and `report.md`.
- Demo company data is rebuilt (`engine/data-v2`); the demo companies remain synthetic.
- The two range cards on Forecast keep their figure on one line at desktop widths, and the tables meant to stack only below the large breakpoint lay out as tables from it (their classes were never generated).
- The shared test setup waits up to twenty seconds for asynchronous screens, so a busy machine no longer fails the first test that opens a screen.

### Removed from the app
- The in-browser scenario planner and target-setter solver, the Excel export, the funnel and MQL views and the ARR bridge. Funnel and MQL return with the inbound motion.

## v0.3.0 — 2026-05-XX

### Added
- **TargetSetter page** at `/targets` — inverse-waterfall solver from quarterly bookings target back to required MQL count, with adjustable scenarios + segment splits + per-stage rate provenance display.
- Engine: optional `engine/config/profiles/<id>/scenarios.yaml` with description block for alternative scenarios.
- Profile: optional `assumptions.yaml::target_setter_defaults` (engine-only — feeds runtime-baked observed scenario).
- Snapshot: optional `target_setter.observed_scenario` (engine-baked) and `target_setter.scenarios` (passthrough).
- Schema: validates new optional fields with strict inner shapes (rate bounds 0..1, ACV>0, additionalProperties:false on Scenario items).
- Engine helpers: `monthsForQuarter`, `lastMonthOfQuarter`, `daysUntilQuarterEnd`, `allQuartersFromSnapshot` (snapshot-driven, no fiscal-calendar literals in lib code).
- Validator: catches malformed scenarios.yaml + target_setter_defaults (missing fields, key parity, numeric bounds, root-key typos).

### Demo data
- Acme demo profile ships with `marketing-led` alternative scenario + `target_setter_defaults` for observed scenario.
- Other demo profiles (Sprout, Sapling, Mighty Oak) gracefully render the page with empty state when no TargetSetter config is present.

## v0.2.0 — 2026-05-02
Initial OSS release. Pluggable forecast engine with snapshot-based contract.
