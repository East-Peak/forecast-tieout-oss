# Changelog

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
