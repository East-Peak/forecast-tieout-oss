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
  give in both as-of modes, with the semantic rules R1 to R9 that define them).
- `workload_b/`: the hand-computed workload; `contract/workload.py` loads it
  as a `Snapshot`. Arithmetic is in `ARITHMETIC.md`.

## Running

```
pip install -r engine/requirements-dev.txt
python -m pytest engine/harness/tests -n auto
ruff check engine/harness
ruff format --check engine/harness
```
