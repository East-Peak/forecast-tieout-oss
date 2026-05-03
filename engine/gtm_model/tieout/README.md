# gtm_model/tieout — Revenue Planning Engine

The tieout engine computes a full-funnel revenue forecast by combining warehouse actuals, observed AE productivity, MQL trends, and pipeline rollforward into a quarterly bookings projection.

## Package Structure

```
tieout/
├── __init__.py          # Public API: PlanningTieout, TieoutResult, etc.
├── engine.py            # PlanningTieout class — main entry point
├── types.py             # TieoutResult, ScenarioResult, QuarterTieout dataclasses
├── runtime/             # Signal & rate resolution
│   ├── resolver.py      # TieoutRuntimeResolver facade
│   ├── rates.py         # Conversion rate resolution (registry, observed, config)
│   ├── observed.py      # Observed signals (AE productivity, ramp curves, MQLs)
│   ├── velocity.py      # Stage velocity from deal history
│   ├── snapshot.py      # RuntimeSnapshot — build once, share everywhere
│   └── env.py           # Environment detection, config loading, Snowflake session
├── scenarios/           # Scenario computation
│   ├── compute.py       # TieoutScenarioComputer — trajectory + plan orchestration
│   ├── assembly.py      # Quarter assembly, monthly capacity
│   ├── archived_plan.py # Config-driven plan scenario
│   ├── projection.py    # Pipeline rollforward projection
│   └── support.py       # Three-source pipeline, expansion engine wrappers
├── targets/             # Top-down target resolution
│   ├── targets.py       # TieoutTargetResolver
│   ├── derivation.py    # Weekly target derivation from quarterly
│   └── rebalance.py     # Pipeline rebalancing across streams
├── views/               # Presentation layer
│   ├── view_models.py   # Bookings bridge, funnel pacing, SE capacity models
│   ├── scorecard.py     # Semantic scorecard for review
│   └── recommendations.py # Gap-closing recommendations, format_money
└── infra/               # Infrastructure & wiring
    ├── api.py           # TieoutPublicApi — compute_full orchestration
    ├── wiring.py        # Dependency injection / component construction
    ├── bootstrap.py     # Constructor helpers
    ├── connectors.py    # Warehouse/CRM connector gateway
    ├── data_access.py   # Roster, inventory, bookings data access
    ├── baseline.py      # Persisted baseline snapshot (pickle + Snowflake)
    ├── plan_config.py   # Plan-case YAML loading
    ├── profile.py       # Performance profiling harness
    ├── health.py        # Data health checks
    └── version.py       # CACHE_VERSION
```

## Data Flow

```
Connectors (warehouse/CRM)
  → Runtime (observed signals, rates, velocity)
    → Scenarios (trajectory, archived plan)
      → TieoutResult (quarters, monthly detail, provenance)
```

## Quick Start

```python
from gtm_model.tieout import PlanningTieout, TieoutResult

tieout = PlanningTieout()
result = tieout.compute_full()
print(result.primary_scenario.name)
```

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Architecture

See the repo-root `ARCHITECTURE.md` for the engine's pluggability story
(ConnectorInterface, ProfileBackend, derived analytics).

Key design decisions baked into this package:
- Two-scenario architecture: trajectory (data-driven projection) plus
  archived plan (config-driven baseline) computed side-by-side
- AE productivity drives pipeline creation — pipeline coverage falls out
  of capacity, not the other way around
- Actuals-spliced rolling horizon — locked actuals replace projections
  for completed months; projections continue from there
- Conservative flat carry — without recent observation, hold the most
  recent rate flat rather than extrapolate
