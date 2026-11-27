# Changelog

## Unreleased: the rebuild

The app now runs on a new calculation core, and the old engine is retired (git tag
`pre-rebuild` is the archive).

### Added
- `engine/tieout_core`: one core that reads a company's deals, stage history and roster and writes a tied-out `report.json` and `report.md`: reconciliation to the source files, a fitted forecast with 80% and 95% ranges against two baselines, a back-test, the gap to target, capacity, required pipeline, a hiring and programme plan, and two verdicts. Run it with `python -m engine.tieout_core report`.
- A declared report contract (`report.schema.json`, schema version 1.3.0) with cross-field rules, and generated TypeScript types.
- Four named scenarios per company (as signed, demo plan, hires only, programme only), each a complete report computed by the core, with a core-computed comparison file.
- `engine/scripts/generate_app_reports.py`, with `--verify` that compares every generated file byte for byte; `generate_data_v2.py` with rebuilt demo data with about two and a half years of history.
- Five screens in place of nine: Forecast, Capacity, Pipeline, Plan and Trust, each answering one question and showing its error or its limits beside its number.
- A binding component, tests that check every bound value against an independent expectation, a stray-digit rule, chart-series checks, mutation tests, and a gate that finds arithmetic in `frontend/src`.
- Redirects from the old addresses: `/bookings` to `/forecast`; `/scenario` and `/targets` to `/plan`; `/inventory` and `/funnel` to `/pipeline`; `/audit`, `/methodology` and `/export` to `/trust`; `/capacity` is replaced in place. The old `?profile=` is read as the company.
- New README screenshots and Open Graph image captured from the new screens (`npm run screenshots`).
- CI runs `npm run verify` and both `--verify` commands.

### Changed
- Company descriptions state the fiscal-year target, the expected total, the gap and what the report finds about headcount; a test checks each figure against the report.
- Demo company data is rebuilt (`engine/data-v2`); the demo companies remain synthetic.

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
