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
of deal outcomes at a fixed seed. The simulation cannot see a shift common to every stage,
so a declared rule (`stretch_rules.py`, committed before it was scored) decides, per
company, whether the ranges are stretched away from their median by factors learned from the
model's own past misses at 1, 3 and 6 months, using only back-test forecasts whose whole
horizon had ended by the date being forecast. When it is adopted, every range carries a
label naming the horizon whose factors it uses and whether its shape was one that was
tested; with-plan ranges are never stretched. The report states the decision, the evidence
per horizon (scored dates with the factors used then), what the rule accepted and how the
factors are chosen, and the validator recomputes the decision and checks the evidence
against the back-test fold by fold.

The report carries two verdicts. *Is the software correct* is a list of self-checks
(rows partition, bookings tie to source, pipeline flow, the solved levers agree with
the forward function, the simulation is centered on the expectation, and others); a
failed check makes the command exit 1. *Is the fitted forecast better than the
baselines* is a result, not a fault: it is often no.

`contract.py` holds the report's declared JSON Schema (`report.schema.json`) and its
cross-field rules (for example, ranges present exactly when a fit was used). Every
report the core's tests build is validated against it.

The `worksheet` section (what moves the outcome) is written by `finish` for every scenario from
`Prepared` and the plan in force, in `worksheet.py`. Its rules are `worksheet_rules.py`
(definitions and gates, fixed before any company was scored) and its evidence
`worksheet_evidence.py` (a company's past by fiscal creation quarter, computed once in `prepare`).
A driver is a pure function from the fitted records to an adjusted copy (`worksheet_drivers.py`:
nothing in `Prepared` is touched, so one prepared company serves any number of worksheets, and the
same functions can carry a visitor's own assumption into a plan later). A figure that exists
elsewhere in the report is carried as `{value, source}` with a JSON pointer, and
`worksheet_contract.py` checks that the value is what the pointer finds.

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

## The plan editor (desktop only)

The same core runs in the browser. `report.build_report` is `prepare` (everything a plan
does not change: the fit, back-test, forecasts, ranges, gap, capacity, actions) and
`finish` (the plan section, the self-checks, the assembly), joined by a typed `Prepared`
record; `finish` changes nothing in it, so one preparation serves any number of plans.
`tieout_core/editor.py` is the entry: `open_company` prepares a company, `apply_plan`
takes a plan as parsed data (never a path), finishes it, validates the report against the
contract in Python, and returns the report text exactly as the generator serializes it,
the contract's findings and the comparison row against as-signed from `comparison.py`.
The generator's constants and serializer live there too.

`npm run build` first runs `scripts/build-editor-assets.mjs` (Node only, no Python):
Pyodide's files from the pinned `pyodide` package, the wheels the core needs (sha256-checked
against the package's lock), `core.zip` and one zip per company's inputs, written to
`public/editor/<content hash>/` (ignored by git; cached for a year by `vercel.json` because
the folder is named by its contents). `src/editor/worker.ts` loads them from the site itself
and is started by `PlanEditorClient` only when "Your plan" is first opened and the window
is at least as wide as the large breakpoint. A failed download never rejects and a dead worker
never answers, so the client bounds start-up (60 s) and each Apply (30 s), fails the request in
hand, ends the worker and starts a new one for the next request; answers carry request ids and a
stale one is ignored. `?editorTimeout=short` is a test hook that lets the first start-up take
three seconds. The session treats scenario `your-plan` like any other (same identity and schema
checks; the core's comparison row joins the file's rows), the visitor's plan is kept in memory
only, and the choice is never remembered for the next visit.

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
   the build (which also writes the plan editor's assets), and a Playwright smoke run against the built
   site, including the plan editor in a real browser: its reports are byte for byte the committed ones
   for the demo plan's items and equal to a native run for an edited plan (`generate_editor_fixture`).

## Retired

The previous engine, its demo data, its snapshot bundles and its in-browser calculators
were retired at the git tag `pre-rebuild`.
