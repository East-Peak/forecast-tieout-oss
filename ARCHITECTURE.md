# Architecture

Two parts joined by one set of files. The core turns a company's CSV files into a
report. The app draws the reports. Nothing else is in the path, and the app never
calculates a number.

```
engine/data-v2/<company>/*.csv  \
engine/config/profiles/<co>/     >-- engine/tieout_core --> report.json + report.md
        plan.yaml (optional)    /           |
                                            v
              engine/scripts/generate_app_reports.py
                                            |
                      frontend/public/data/reports/   (committed)
                                            |
                                            v
                      frontend/src  (five screens, static site)
```

## The core: `engine/tieout_core`

Typed records and pure functions. It reads no network and no clock: every calculation
takes its as-of date as an argument. Money is parsed straight into exact decimals and
written to the report as decimal strings.

Reading order of the report: reconcile the source files (every row included, or
excluded with a reason); fit stage win rates and close timing from monthly snapshots
of the history; forecast the rest of the year (a fitted model, plus two baselines that
are point forecasts); score all three on a back-test that sees only what was known at
each past date; compute the gap to the quarterly targets; read the roster for capacity
(ramp, attrition, created pipeline per ramped rep) and decide, by a rule declared
before scoring, whether headcount explains pipeline; solve for the pipeline or hires
that would close the gap; apply a plan if one is given. Ranges come from simulated draws
of deal outcomes at a fixed seed.

The report carries two verdicts. *Is the software correct* is a list of self-checks
(rows partition, bookings tie to source, pipeline flow, the solved levers agree with
the forward function, the simulation is centered on the expectation, and others); a
failed check makes the command exit 1. *Is the fitted forecast better than the
baselines* is a result, not a fault: it is often no.

`contract.py` holds the report's declared JSON Schema (`report.schema.json`) and its
cross-field rules (for example, ranges present exactly when a fit was used). Every
report the core's tests build is validated against it.

## The generators

- `engine/scripts/synth_history.py` and `generate_data_v2.py` write the three synthetic
  demo companies to `engine/data-v2/` from a fixed seed. `--verify` fails if a file is
  stale.
- `engine/scripts/generate_app_reports.py` runs the core for each company and each of
  four scenarios (as signed, demo plan, hires only, program only) and writes the
  reports, an `index.json`, a `comparison.json` per company, the scenario plan files, the
  JSON Schema and the TypeScript types into the repository. `--verify` regenerates all of
  it into a temporary directory and compares byte for byte. Paths inside the files are
  repo-relative and key order is fixed, so output is identical on every machine.

A company's one-line description in `index.json` is generated from its as-signed report
(`engine/tieout_core/company_line.py`): whether the year is short of, on or ahead of
target, whether headcount explains pipeline, and whether the fitted forecast beats the
simple baselines, each from a status in the report through one table of phrases. It holds
no figure, and a test checks that it agrees with the report's statuses.

## The app: `frontend/src`

A static React and Vite site with five screens (Forecast, Capacity, Pipeline, Plan,
Trust). It has no server and no arithmetic.

- `session/`: the company and scenario in the address (`?company=&scenario=`) decide
  which report file is loaded. A late answer for a previous choice is ignored, a report
  must be the one asked for, and a failed load is an error that names the file.
- `binding/`: the one component that renders a business value, given a scenario, a path
  into the report and a named format; and the adapter that builds chart series from
  declared paths. Report decimals are branded strings that only these two can parse.
- `screens/<name>/`: each screen is a list of bindings over the loaded report. Absent
  figures are shown in words with the report's reason, never as zero.
- `shell/`: the header, the five-screen navigation, and the redirects from the old
  app's addresses (`/bookings` to `/forecast`, and so on) with the old `?profile=`
  read as the company.
- `generated/`: types written from the report schema; not edited by hand.

## What keeps it honest

1. The binding rule: a number on a screen is a binding to a report path, or it is not on
   the screen. Tests fail on any digit outside a bound element (chart axis ticks and
   period labels excepted), on a chart whose drawn series differs from its bound series,
   and on a compiler-based scan of `frontend/src` that finds arithmetic.
2. Mutations: each screen's tests swap a path, a company, a scenario, a format or a sign
   and expect failure.
3. `generate_app_reports --verify`: the committed reports are exactly what the core
   writes today, they validate against the schema, and every report's own
   software-correct verdict is yes.
4. CI runs the Python tests, ruff on the core and the generators, both `--verify`
   commands, `tsc --noEmit`, `npm run verify` (knip dead-code check and the unit tests),
   the build, and a Playwright smoke run against the built site.

## Retired

The previous engine, its demo data, its snapshot bundles and its in-browser calculators
were retired at the git tag `pre-rebuild`.
