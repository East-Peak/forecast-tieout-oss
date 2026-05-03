# Architecture

Three abstractions keep the engine pluggable.

**Raw data in, analytics out.** `ConnectorInterface` returns domain-neutral
dataclasses — Deals, TeamMembers, StageTransitions. The engine derives ARR
snapshots, finance summaries, monthly actuals, and stage velocity from those
raw inputs. Source-specific aggregation (e.g. SQL pre-agg) is an optional
backend override, not a requirement.

`engine/connectors/interface.py`, `engine/gtm_model/derived/*`

**ProfileBackend is the wiring seam.** The engine never talks to specific
data sources directly. It consumes a `ProfileBackend` Protocol — a connector
plus optional health checks and analytics methods with sensible Python
defaults. Forking is one Protocol implementation.

`engine/profile_backend/protocol.py`. CSV ships as a working reference.

**Stages normalize at the boundary.** The engine speaks one vocabulary:
`S0`–`S5`, `Won`, `Lost`. Each profile's `field_mappings.yaml` declares
source stages and how they map. Connectors translate in `fetch_deals()` so
the engine sees one shape regardless of source.

Profiles wire it up declaratively:

```yaml
# profile.yaml
data_access:
  type: csv
  params: { path: engine/data/your-profile }
```

That's the architecture.
