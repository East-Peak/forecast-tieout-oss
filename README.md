# Forecast Tieout

Reconcile the revenue plan against pipeline reality.

## What this is

A full-stack GTM planning tool that surfaces the gap between your top-down
revenue plan and bottoms-up pipeline data. A Python engine reads deal,
team, and stage-history data (CSV today; bring your own backend for
Salesforce, Snowflake, or anything else), runs the tieout calculations,
and writes a versioned `snapshot.json`. A React dashboard reads the
snapshot and renders nine views: bookings bridge, pipeline inventory,
funnel health, capacity, scenario planning, audit readiness, export,
methodology, target setter.

Built for B2B SaaS running quarterly direct-sales motions. The public
demo ships three personas: Sprout Labs ($10M early PMF), Sapling
Industries ($100M scale-up), and Mighty Oak Holdings ($800M mature
enterprise). Acme SaaS remains as the CSV-ingestion engine and CI fixture
for the "bring your own CRM export" path.

## Quick Start

```bash
git clone <repo-url>
cd forecast-tieout/frontend
npm install
npm run dev
# http://localhost:3000
```

## Pages

| Page | Description |
|------|-------------|
| **Bookings Bridge** | Plan-to-pipeline waterfall by quarter |
| **Pipeline Inventory** | Monthly pipeline detail showing current inventory conversion and future S2+ generation |
| **Funnel Health** | Stage conversion + cycle time; highlights stalls |
| **Capacity & Headcount** | Quota capacity, ramp-adjusted targets, coverage ratio |
| **Scenario Planner** | Client-side what-if — win rates, deal sizes, rep count |
| **Audit Readiness** | Missing close dates, stale stages, no-amount deals |
| **Export Pack** | XLSX workbook with all tieout tables and formulas |
| **Methodology** | Calculation logic for every metric |
| **Target Setter** | Inverse-waterfall solver: given a quarterly bookings target, computes required MQL volume by working back through win rates, segment splits, ACVs, and funnel conversion rates. Reachable at `/targets`. |

## Connect Your Data

Profiles declare their backend in `profile.yaml`:

```yaml
data_access:
  type: csv
  params:
    path: engine/data/your-profile
```

### CSV

Drop these into `engine/data/your-profile/`:

```
deals.csv          # required
team_members.csv   # required
stage_history.csv  # optional — enables velocity metrics
companies.csv      # optional
contacts.csv       # optional
```

Then:

```bash
pip install -r engine/requirements.txt
python -m engine.scripts.validate_profile --profile your-profile
python -m engine.scripts.generate_snapshot --profile-id your-profile
# --as-of YYYY-MM-DD for deterministic runs
```

### Salesforce, Snowflake, custom sources

The engine ships CSV as the working reference backend. To add another
source: implement `ConnectorInterface` (`engine/connectors/interface.py`),
register a backend with the factory (`engine/profile_backend/factory.py`),
and declare the type in your `profile.yaml`. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the extension pattern; `engine/connectors/csv_connector.py` and
`engine/profile_backend/csv_backend.py` are the reference implementations
to model from.

### Create your own profile

Copy any demo profile under `engine/config/profiles/` as a starting
point, edit the YAMLs for your fiscal calendar, stages, targets, and
roster, then validate.

> Real CSVs and custom profiles are gitignored by default. The three
> public persona profiles are explicitly allowlisted for the static demo;
> Acme SaaS is allowlisted only as the engine/CI CSV fixture. Anything
> else under `engine/data/`, `engine/config/profiles/`, or
> `frontend/public/data/profiles/` stays out of git unless you deliberately
> commit it.

## Deploy

### Vercel static demo

The portfolio demo is Vercel-first and needs zero environment variables.
`frontend/public/data` is bundled into the static build, and `vercel.json`
already contains the SPA rewrite needed for direct route loads.

```bash
cd frontend
npm install
npm run build
```

If you host the static data somewhere other than `/data`, set
`VITE_DATA_BASE_URL` to that base URL at build time. The frontend reads
`profiles/index.json` from that base and resolves profile snapshots and
plan manifests relative to it.

### Advanced deployment

Docker remains available for self-hosting:

```bash
docker compose up
# Dashboard at http://localhost:8080. Set PROFILE_ID in docker-compose.yml.
```

For protected real-data deployments, schedule the engine via your CI of
choice to regenerate snapshots and publish them to private artifact
storage. The Supabase protected mode path uses `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`, and the storage artifact settings in
`.env.example`; leave those unset for the public static demo.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). The engine talks to a
`ProfileBackend` Protocol; CSV ships as a reference implementation,
forkers add their own backends. Snapshot is the contract; schema in
`schema/snapshot.schema.json`.

## Configuration

| File | Controls |
|------|----------|
| `profile.yaml` | Fiscal calendar, `data_access` backend |
| `targets.yaml` | Quarterly + annual targets, beginning ARR |
| `stages.yaml` | Stage names, order, closed-won flags |
| `slip_rates.yaml` | Historical close-date slip probabilities |
| `assumptions.yaml` | Default win rates, deal sizes, ramp curves |
| `roster.yaml` | Reps with segments, start dates, quotas |
| `field_mappings.yaml` | Source field → domain field; stage normalization |

## Adding a Backend

Two extension points:

**`ConnectorInterface`** — for any data source. Return `Deal`,
`TeamMember`, `StageTransition` dataclasses; the engine derives analytics.
Reference: `engine/connectors/csv_connector.py`.

**`ProfileBackend`** — for sources with source-specific fast paths (e.g.
SQL pre-aggregation). Subclass `ProfileBackendBase`, override the
relevant `compute_*` method, return the same dataclass shape the default
returns. Reference: `engine/profile_backend/csv_backend.py`. Register
custom types via `register_backend("your-type", builder_fn)`.

## Security

Snapshots contain deal data. Treat them accordingly.

- Bundled demo snapshots are synthetic and safe to serve publicly.
- For real data: use protected artifact storage such as Supabase with RLS,
  plus lifecycle policies for retention.
- Source credentials for whatever backend you wire up go in env vars or
  CI secrets, never committed.

## License

Apache 2.0. See [LICENSE](LICENSE).
