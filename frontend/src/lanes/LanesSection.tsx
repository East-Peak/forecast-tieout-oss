import { Fragment, useCallback, useEffect, useId, useRef, useState } from "react";
import { BindingProvider, Bound, useBindingContext } from "../binding/Bound";
import { YOUR_PLAN } from "../editor/yourPlan";
import { BASIS, COLUMNS, FRAME, HEAD, LANE } from "./bindings";
import type { CellSource } from "./bindings";
import { GridCell } from "./Cell";
import { useLanesLoaders } from "./LanesContext";
import { CellPanel } from "./Panel";
import type { BasisFile, ColumnKey, LanesFile, LanesLoaders, OwnersFile, RecordsFile, Row } from "./types";
import { useFile } from "./useFile";
import type { Loaded } from "./useFile";

/** The scenario whose lanes are drawn: the visitor's own plan has none yet, so it shows the plan as signed. */
const AS_SIGNED = "as-signed";

/** One row of the grid as drawn: where it is read from and what names it. */
interface Shown {
  source: CellSource;
  /** the row's path in the file, joined by "/": `total`, `segment/enterprise`, `segment/enterprise/owner/AE-010` */
  id: string;
  row: Row;
  pointer: string;
  /** the segment the owner rows under it belong to */
  slug?: string;
}

interface Selected {
  id: string;
  column: ColumnKey;
}

const idOf = (path: readonly string[]) => path.join("/");
/** A row's id as an element id: a segment is named by its name in the file, which may hold a space. */
const domId = (id: string) => id.replace(/[^A-Za-z0-9_-]/g, "_");

function Chevron({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 10 10" className={`h-2.5 w-2.5 ${open ? "rotate-90" : ""}`} fill="currentColor" aria-hidden="true">
      <path d="M3 1.5 7.5 5 3 8.5z" />
    </svg>
  );
}

function Legend() {
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500" data-testid="legend">
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-1.5 w-6 overflow-hidden rounded-full bg-slate-200"><span className="block h-full w-2/5 bg-slate-500" /></span>
        solid to the actual, lighter to the forecast, ending at the goal
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-slate-500" /> actual
        <span className="ml-1 inline-block h-2.5 w-2.5 rounded-full border-2 border-slate-500 bg-white" /> forecast
        <span className="ml-1 inline-block h-3 w-0.5 bg-slate-700" /> goal, on a strip for a rate, a duration or a size
      </span>
    </p>
  );
}

/** The one-line caveat and the disclosure that holds the rest of the file's caveats and the schedule beside the targets. */
function Honesty({ lanes, basis, owners }: { lanes: LanesFile; basis: Loaded<BasisFile>; owners: boolean }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  return (
    <div className="space-y-1 text-xs text-slate-600">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>
          <span className="font-medium text-slate-800">Upstream goals. </span>
          <span data-testid="benchmark-note">These goals are derived benchmarks, not a reconciled operating plan.</span>
        </span>
        <button type="button" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((v) => !v)} className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:border-slate-300">
          How the goals are made {open ? "▴" : "▾"}
        </button>
      </p>
      {owners ? (
        <p data-testid="owner-note">Owner goals are allocated goals, shares of the segment's goal. Quota and segment are today's values, standing in for the plan date.</p>
      ) : null}
      {open ? (
        <div id={panel} className="mt-2 grid items-start gap-x-8 gap-y-4 rounded-ft border border-slate-200 bg-white p-4 leading-snug text-slate-700 shadow-ft lg:grid-cols-2" data-testid="basis-detail">
          <ul className="space-y-3">
            {(["caveatBenchmarks", "caveatWinRate", "caveatPooled"] as const).slice(0, lanes.caveats.length).map((key) => (
              <li key={key}><Bound binding={FRAME[key]} /></li>
            ))}
          </ul>
          <div>
            <h4 className="text-xs font-semibold text-ft-brand">The frozen schedule beside the targets</h4>
            {basis.status === "ready" ? (
              <table className="mt-2 w-full max-w-md text-left tabular-nums">
                <thead className="text-slate-500">
                  <tr>
                    <th scope="col" className="py-0.5 font-medium">Quarter</th>
                    <th scope="col" className="py-0.5 text-right font-medium">Schedule bookings</th>
                    <th scope="col" className="py-0.5 text-right font-medium">Target</th>
                  </tr>
                </thead>
                <tbody>
                  {basis.doc.schedule.map((q, i) => (
                    <tr key={q.quarter} className="border-t border-slate-100">
                      <th scope="row" className="py-0.5 font-normal"><Bound binding={BASIS.scheduleQuarter} row={`/schedule/${i}`} /></th>
                      <td className="py-0.5 text-right"><Bound binding={BASIS.scheduleBookings} row={`/schedule/${i}`} /></td>
                      <td className="py-0.5 text-right"><Bound binding={BASIS.scheduleTarget} row={`/schedule/${i}`} /></td>
                    </tr>
                  ))}
                  <tr className="border-t border-slate-200 font-medium">
                    <th scope="row" className="py-0.5">Year</th>
                    <td className="py-0.5 text-right"><Bound binding={BASIS.totalBookings} row="/schedule_total" /></td>
                    <td className="py-0.5 text-right"><Bound binding={BASIS.totalTarget} row="/schedule_total" /></td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <p className="mt-2 text-slate-500">{basis.status === "error" ? "The goal basis could not be loaded." : "Loading the goal basis."}</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

interface BodyProps {
  loaders: LanesLoaders;
  lanes: LanesFile;
  basis: Loaded<BasisFile>;
  ownerPaths: Record<string, string | undefined>;
  recordsPath: string | null;
  company: string;
}

/** The grid, its toolbar and its panel, for one company's one scenario. */
function Body({ loaders, lanes, basis, ownerPaths, recordsPath, company }: BodyProps) {
  const ctx = useBindingContext();
  const [period, setPeriod] = useState(0);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [owners, setOwners] = useState<Record<string, Loaded<OwnersFile>>>({});
  const [selected, setSelected] = useState<Selected | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const gridId = useId();

  // the records are fetched when the first cell is opened, and kept
  const [wantRecords, setWantRecords] = useState(false);
  const records = useFile<RecordsFile>(
    wantRecords && recordsPath ? recordsPath : null,
    () => loaders.records(recordsPath!),
    (doc) => (doc.company === company ? null : `${recordsPath} is the records of ${doc.company}, not of ${company}`),
  );

  const loadOwners = useCallback(
    (slug: string) => {
      const path = ownerPaths[slug];
      if (!path) {
        setOwners((o) => ({ ...o, [slug]: { status: "error", error: "the index lists no owners file for this segment" } }));
        return;
      }
      setOwners((o) => ({ ...o, [slug]: { status: "loading" } }));
      loaders.owners(path).then(
        (doc) =>
          setOwners((o) => ({
            ...o,
            [slug]:
              doc.company !== company || doc.segment !== slug || doc.scenario !== lanes.scenario
                ? { status: "error", error: `${path} holds the ${doc.segment} owners of ${doc.company} (${doc.scenario}), not the ${slug} owners of ${company} (${lanes.scenario})` }
                : { status: "ready", doc },
          })),
        (e: unknown) => setOwners((o) => ({ ...o, [slug]: { status: "error", error: e instanceof Error ? e.message : String(e) } })),
      );
    },
    [loaders, ownerPaths, company, lanes.scenario],
  );

  const toggle = (slug: string) => {
    const next = new Set(expanded);
    if (next.has(slug)) {
      next.delete(slug);
      if (selected?.id.startsWith(`segment/${slug}/`)) setSelected(null);
    } else {
      next.add(slug);
      if (!owners[slug] || owners[slug].status === "error") loadOwners(slug);
    }
    setExpanded(next);
  };

  const periodRows = lanes.periods[period].rows;
  const periodKey = lanes.periods[period].key;
  const ownersOpen = [...expanded].some((slug) => owners[slug]?.status === "ready");

  /** every row on the page, in order, so the panel can find the one it is open on */
  const shownRows: Shown[] = periodRows.flatMap((row, index) => {
    const slug = row.kind === "segment" ? row.path[1] : undefined;
    const head: Shown = { source: "lanes", id: idOf(row.path), row, pointer: `/periods/${period}/rows/${index}` };
    const state = slug !== undefined && expanded.has(slug) ? owners[slug] : undefined;
    if (slug === undefined || state?.status !== "ready") return [head];
    const p = state.doc.periods.findIndex((x) => x.key === periodKey);
    return [
      head,
      ...state.doc.periods[p].rows.map((o, i): Shown => ({ source: "owners", id: idOf(o.path), row: o, pointer: `/periods/${p}/rows/${i}`, slug })),
    ];
  });
  const target = selected ? shownRows.find((r) => r.id === selected.id) : undefined;

  const close = useCallback(() => {
    setSelected(null);
    const cell = opener.current;
    if (cell?.isConnected) cell.focus();
  }, []);

  useEffect(() => {
    // a panel whose row has gone (a segment folded) is closed
    if (selected && !target) setSelected(null);
  }, [selected, target]);

  const open = (id: string, column: ColumnKey, button: HTMLElement) => {
    opener.current = button;
    setWantRecords(true);
    setSelected({ id, column });
    // the cell stays in view beside the docked panel, or above the sheet below it (the cell's own scroll margins say where)
    requestAnimationFrame(() => button.scrollIntoView?.({ block: "nearest", inline: "nearest" }));
  };

  const panelOwners = target?.source === "owners" && target.slug ? owners[target.slug] : undefined;
  const files = { ...ctx.files, lanes, basis: basis.status === "ready" ? basis.doc : undefined, records: records.status === "ready" ? records.doc : undefined };

  return (
    <BindingProvider company={ctx.company} scenario={ctx.scenario} files={files} choose={ctx.choose}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2" role="toolbar" aria-label="Grid controls">
        <div className="inline-flex flex-wrap rounded-ft border border-slate-200 bg-white p-0.5 shadow-ft" role="group" aria-label="Period">
          {lanes.periods.map((p, i) => (
            <button
              key={p.key}
              type="button"
              data-testid={`period-${p.key}`}
              aria-pressed={i === period}
              onClick={() => setPeriod(i)}
              className={`rounded px-3 py-1 text-sm ${i === period ? "bg-ft-accentSoft font-medium text-ft-brand" : "text-slate-600 hover:text-slate-900"}`}
            >
              <Bound binding={FRAME.periodKey} row={`/periods/${i}`} />
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-600">
          <Bound binding={FRAME.periodStart} row={`/periods/${period}`} /> to <Bound binding={FRAME.periodEnd} row={`/periods/${period}`} />{" "}
          <span className="text-slate-500">(<Bound binding={FRAME.periodStanding} row={`/periods/${period}`} />)</span>
        </p>
      </div>
      <Honesty lanes={lanes} basis={basis} owners={ownersOpen} />
      <Legend />
      <div data-testid="lanes-body" className={`xl:flex xl:items-start xl:gap-4 ${selected ? "pb-[55vh] lg:pb-0" : ""}`}>
        <div className="min-w-0 flex-1">
          <div data-testid="grid-scroll" className={`overflow-x-auto rounded-ft border border-slate-200 bg-white shadow-ft ${selected ? "lg:max-xl:pr-[440px]" : ""} lg:max-h-[calc(100vh-var(--ft-header-height,0px)-24px)] lg:min-h-[300px] lg:overflow-auto`}>
            <table className="w-full min-w-[1170px] border-separate border-spacing-0 text-left" data-testid="lanes-grid">
              <thead>
                <tr>
                  <th scope="col" className="sticky left-0 top-0 z-30 w-[116px] min-w-[116px] border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 sm:w-[168px] sm:min-w-[168px]">
                    Lane
                  </th>
                  {lanes.columns.map((c) => (
                    <th key={c.key} id={`${gridId}-c-${c.key}`} scope="col" data-col={c.key} className="sticky top-0 z-20 min-w-[124px] border-b border-l border-slate-200 bg-slate-50 px-2.5 py-2 align-bottom">
                      <Bound binding={HEAD.title} row={`/columns/{key=${c.key}}`} className="block text-xs font-semibold text-slate-800" />
                      <Bound binding={HEAD.unit} row={`/columns/{key=${c.key}}`} className="block text-[10px] font-normal uppercase text-slate-500" />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {periodRows.map((row, index) => {
                  const slug = row.kind === "segment" ? row.path[1] : undefined;
                  const state = slug !== undefined && expanded.has(slug) ? owners[slug] : undefined;
                  const head: Shown = { source: "lanes", id: idOf(row.path), row, pointer: `/periods/${period}/rows/${index}` };
                  return (
                    <Fragment key={head.id}>
                      <GridRow shown={head} role={row.kind === "company" ? "total" : "segment"} gridId={gridId} selected={selected} onOpen={open} toggle={slug === undefined ? undefined : { open: expanded.has(slug), busy: state?.status === "loading", flip: () => toggle(slug) }} />
                      {state?.status === "loading" ? (
                        <tr>
          <th scope="row" className="sticky left-0 z-10 border-b border-r border-slate-200 bg-white" />
          <td colSpan={COLUMNS.length} className="border-b border-slate-200 px-3 py-2 text-xs text-slate-500" role="status">Loading the owners.</td>
        </tr>
                      ) : null}
                      {state?.status === "error" ? (
                        <tr>
          <th scope="row" className="sticky left-0 z-10 border-b border-r border-slate-200 bg-white" />
          <td colSpan={COLUMNS.length} className="border-b border-slate-200 px-3 py-2 text-xs text-red-700" role="alert">The owners could not be loaded: {state.error}</td>
        </tr>
                      ) : null}
                      {state?.status === "ready" ? (
                        <OwnerRows doc={state.doc} slug={slug!} periodKey={periodKey} gridId={gridId} selected={selected} onOpen={open} />
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        {selected && target ? (
          <BindingProvider company={ctx.company} scenario={ctx.scenario} files={{ ...files, owners: panelOwners?.status === "ready" ? panelOwners.doc : undefined }} choose={ctx.choose}>
            <CellPanel
              source={target.source}
              lanes={lanes}
              basis={basis}
              records={records}
              row={target.row}
              rowPointer={target.pointer}
              periodIndex={period}
              column={selected.column}
              onClose={close}
            />
          </BindingProvider>
        ) : null}
      </div>
    </BindingProvider>
  );
}

function OwnerRows({ doc, slug, periodKey, gridId, selected, onOpen }: { doc: OwnersFile; slug: string; periodKey: string; gridId: string; selected: Selected | null; onOpen: (id: string, column: ColumnKey, button: HTMLElement) => void }) {
  const ctx = useBindingContext();
  const p = doc.periods.findIndex((x) => x.key === periodKey);
  return (
    <BindingProvider company={ctx.company} scenario={ctx.scenario} files={{ ...ctx.files, owners: doc }} choose={ctx.choose}>
      {doc.periods[p].rows.map((o, i) => (
        <GridRow key={idOf(o.path)} shown={{ source: "owners", id: idOf(o.path), row: o, pointer: `/periods/${p}/rows/${i}`, slug }} role="owner" gridId={gridId} selected={selected} onOpen={onOpen} />
      ))}
    </BindingProvider>
  );
}

function GridRow({
  shown,
  role,
  gridId,
  selected,
  onOpen,
  toggle,
}: {
  shown: Shown;
  role: "total" | "segment" | "owner";
  gridId: string;
  selected: Selected | null;
  onOpen: (id: string, column: ColumnKey, button: HTMLElement) => void;
  toggle?: { open: boolean; busy: boolean; flip: () => void };
}) {
  const own = LANE[shown.source];
  const rowHead = `${gridId}-r-${domId(shown.id)}`;
  const verb = `${rowHead}-verb`;
  const tint = role === "total" ? "bg-slate-50" : "bg-white";
  return (
    <tr data-testid={`row-${shown.id}`} data-role={role}>
      <th scope="row" id={rowHead} className={`sticky left-0 z-10 w-[116px] min-w-[116px] border-b border-r border-slate-200 px-2 py-2 text-left align-middle font-normal sm:w-[168px] sm:min-w-[168px] sm:px-3 ${tint}`}>
        <div className={`flex items-center gap-1.5 ${role === "owner" ? "pl-5" : ""}`}>
          {toggle ? (
            <button
              type="button"
              data-testid={`expand-${shown.id}`}
              aria-expanded={toggle.open}
              aria-busy={toggle.busy}
              aria-labelledby={`${verb} ${rowHead}-label`}
              onClick={toggle.flip}
              className="-ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-500 hover:bg-slate-100"
            >
              <span id={verb} className="sr-only">{toggle.open ? "Collapse" : "Expand"}</span>
              <Chevron open={toggle.open} />
            </button>
          ) : null}
          <span id={`${rowHead}-label`} className={`min-w-0 flex-1 text-sm ${role === "owner" ? "text-slate-700" : "font-semibold text-slate-900"}`}>
            <Bound binding={own.label} row={shown.pointer} />
          </span>
        </div>
      </th>
      {COLUMNS.map((column) => (
        <td key={column} className={`border-b border-l border-slate-200 p-0 align-top ${tint}`}>
          <GridCell
            source={shown.source}
            rowPointer={shown.pointer}
            rowId={shown.id}
            headIds={`${rowHead}-label ${gridId}-c-${column}`}
            column={column}
            cell={shown.row.cells[column]}
            selected={selected?.id === shown.id && selected.column === column}
            onOpen={(button) => onOpen(shown.id, column, button)}
          />
        </td>
      ))}
    </tr>
  );
}

/** The swimlane grid on the Plan screen: a lane for the company, each segment and, opened, each owner, against the plan's links. */
export default function LanesSection() {
  const loaders = useLanesLoaders();
  if (!loaders) return null;
  return <Section loaders={loaders} />;
}

function Section({ loaders }: { loaders: LanesLoaders }) {
  const ctx = useBindingContext();
  const entry = ctx.files.index.companies.find((c) => c.id === ctx.company);
  const own = ctx.scenario === YOUR_PLAN;
  const scenario = entry?.scenarios.find((s) => s.id === (own ? AS_SIGNED : ctx.scenario));
  const lanesPath = scenario?.lanes ?? null;
  const key = `${ctx.company}/${scenario?.id ?? ""}`;

  const lanes = useFile(
    lanesPath === null ? null : key,
    () => loaders.lanes(lanesPath!),
    (doc) => {
      if (doc.company !== ctx.company) return `${lanesPath} is the lanes of ${doc.company}, not of ${ctx.company}`;
      if ("unavailable" in doc) return null;
      return doc.scenario === scenario?.id ? null : `${lanesPath} is the lanes of ${doc.scenario}, not of ${scenario?.id}`;
    },
  );
  const basisPath = entry?.lanes_basis ?? null;
  const basis = useFile<BasisFile>(
    lanes.status === "ready" && basisPath !== null && !("unavailable" in lanes.doc) ? `${key}/basis` : null,
    () => loaders.basis(basisPath!),
    (doc) => (doc.company === ctx.company ? null : `${basisPath} is the basis of ${doc.company}, not of ${ctx.company}`),
  );

  return (
    <section data-testid="lanes" aria-labelledby="lanes-title" className="flex w-full min-w-0 scroll-mt-[var(--ft-header-height,0px)] flex-col gap-3">
      <div>
        <h2 id="lanes-title" className="font-display text-base font-semibold text-ft-brand">
          Lanes
        </h2>
        <p className="mt-1 text-xs text-slate-500">Where the year is weaker than plan: which link, which segment, which owner.</p>
        {lanes.status === "ready" && !("unavailable" in lanes.doc) ? (
          <p className="mt-1 text-xs text-slate-600" data-testid="plan-basis">
            <BindingProvider company={ctx.company} scenario={ctx.scenario} files={{ ...ctx.files, lanes: lanes.doc }} choose={ctx.choose}>
              <span className="font-semibold text-slate-800"><Bound binding={FRAME.basisLabel} /></span> <span className="text-slate-500">· data as of <Bound binding={FRAME.asOf} /></span>
            </BindingProvider>
          </p>
        ) : null}
      </div>
      {own ? (
        <p className="rounded-ft border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900" role="note" data-testid="your-plan-note">
          The lanes do not yet reflect your edited plan: this grid is the plan as signed, so its forecasts are the as-signed forecasts. Actuals and goals do not depend on the plan.
        </p>
      ) : null}
      {lanesPath === null ? (
        <p className="text-sm text-slate-600" role="status">No lanes are published for this scenario.</p>
      ) : lanes.status === "error" ? (
        <p className="text-sm text-red-700" role="alert">The lanes could not be loaded: {lanes.error}</p>
      ) : lanes.status !== "ready" ? (
        <p className="text-sm text-slate-500" role="status">Loading the lanes.</p>
      ) : "unavailable" in lanes.doc ? (
        <BindingProvider company={ctx.company} scenario={ctx.scenario} files={{ ...ctx.files, lanes: lanes.doc }} choose={ctx.choose}>
          <p className="text-sm text-slate-700" data-testid="lanes-unavailable"><Bound binding={FRAME.unavailable} /></p>
        </BindingProvider>
      ) : (
        <Body
          key={key}
          loaders={loaders}
          lanes={lanes.doc}
          basis={basis}
          ownerPaths={scenario?.lanes_owners ?? {}}
          recordsPath={entry?.lanes_records ?? null}
          company={ctx.company}
        />
      )}
    </section>
  );
}
