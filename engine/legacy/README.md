# Engine Legacy Modules

Modules here are preserved for reference but are not on the active forecast
tieout runtime path.

- `monte_carlo.py` was moved here on 2026-07-04. Reachability triage found no
  active imports from snapshot generation, tieout workflows, tests, or scripts
  beyond the historical `gtm_model` package barrel re-export and its own usage
  example.
