# Forecast Tieout harness

Backend for the forecast tie-out harness. Design:
`docs/specs/2026-11-28-forecast-tieout-harness-backend-design.md` in the
private workspace. This directory is built beside the old `tieout_core` and does
not touch it.

## Packages

| Package | Owns |
|---|---|
| `contract/` | Raw record schemas (one JSON Lines file per object), the extract manifest and its validator, canonical table keys, the `Snapshot` and `DealObservations` types, and the golden fixtures. The interface every other package builds against. |
| `synth/` | The seeded generator and plan writer. Writes extracts that validate against `contract/`. |
| `evidence/` | Loads extracts into assertions and canonical tables, answers as-of queries (DuckDB). Builds a `Snapshot`. |
| `catalog/` | Catalog YAML format, validation, compilation to queries. |
| `planning/` | Estimation, forecast, solve, tie-out, bridge. Typed inputs and results, numpy only. |
| `adapters/` | Per-estate mapping files. |
| `tests/` | Cross-package tests (import rules). Each package's own tests also live here, named by package. |

## Import rules (enforced by `tests/test_import_rules.py`)

- `contract/` and `planning/` never import `duckdb`.
- `synth/` never imports `planning/` (the generator shares no code with the model).
- Dependencies: standard library, `duckdb`, `pyyaml`, `numpy`. Nothing else.

## Conventions

- All data is fabricated: fake names, `@example.com` emails.
- Measured money is integer cents. Raw Salesforce `Amount` is a JSON number in
  dollars with at most two decimals, converted once by the loader.
- Timestamps are UTC ISO 8601 with a trailing `Z`; dates are `YYYY-MM-DD`.
- American English.

## Golden fixtures (`contract/fixtures/`)

- `estate_a/`: two extracts of a tiny estate (a late amount edit, a close date
  entered in arrears, a deleted record, a field with no history), `estate.yaml`
  (field coverage), and `expected.yaml` (the answers an evidence engine must
  give in both as-of modes, with the semantic rules R1 to R8 that define them).
- `workload_b/`: the hand-computed workload (eight months, arrivals stop after July); `contract/workload.py` loads it
  as a `Snapshot`. Arithmetic is in `ARITHMETIC.md`.

## Notes for the generator builder

- Emit each system's extract with `build_manifest` and check it with `validate_extract`; `extract_id` is derived from system and time.
- Write history rows only when a field changes (the first row carries all fields) and keep history append-only across extracts. A deleted record's history drops out of later extracts.
- An extracted but empty object is an empty file listed with count 0; an object not extracted has no file and no manifest entry.
- Demand: set `Lead.Sales_Offered_Date__c` for every offer (marketing and outbound alike) and track it in `LeadHistory`. A re-offer writes a new value plus resets of `Disposition__c` and `Disposition_Reason__c` to null. `MQL_Date__c` is optional. `Disposition__c` is Admitted, Rejected or Expired, null while open.
- A close date can be set in arrears and corrected later; stage transitions are observed at the history row time. Reopening is a closed-to-open stage move. Deleting a record drops it from later snapshots.
- `Account.BillingCountry` is free text (names and codes both occur); `BillingCountryCode` is optional.
- Match `User.Email` to `people.email`. Reproduce fixture B with `contract/workload.py` and `flow_check`.

## Notes for the evidence builder

- `expected.yaml` is the executable spec; read rules R1 to R8 first. The oracle in `tests/test_estate_a_fixture.py` is brute force over the raw rows, not production code.
- Two questions, never mixed: `stage_at(T)` is operational (observed transitions, effective at the row time), `open_at(T)` is commercial (known, created, not deleted, not closed by effective CloseDate, with reopening starting a new spell). Measures over closed deals restate from the latest value recorded by K (R3).
- A record is known from its earliest history row, else its first extract. Snapshot differences emit assertions only for fields with no history; history wins.
- Deletion: `_deleted` is effective and recorded at the first extract lacking the record, flagged `deletion_time_upper_bound`. Earlier existence, bookings and workload stand; the terminal outcome is `deleted` (censored, not lost).
- `Snapshot` money is int64 cents and missing cells hold 0. `flow_check` must report no violations on any Snapshot you build; cells it cannot check come back as `unavailable` with a reason. Mark demand `lower_bound` where dispositions do not reconcile. `outstanding_episodes` must reproduce `queue_end` at the last month.
- `DealObservations`: filter predictors by `*_recorded` <= the landmark; win, loss and deleted labels use the observed closing time, bookings month uses the spell's CloseDate. Lane membership is a history.

## Running

```
pip install -r engine/requirements-dev.txt
python -m pytest engine/harness/tests -n auto
ruff check engine/harness
ruff format --check engine/harness
```
