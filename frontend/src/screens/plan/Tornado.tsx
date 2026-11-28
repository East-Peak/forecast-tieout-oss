import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import { plotExtent } from "../../binding/chartData";
import type { PlotRow } from "../../binding/chartData";
import { usePlot } from "../../binding/ChartKit";
import { Badge, Callout, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { Disclosure, SectionHeader } from "../../components/workbook";
import { STACK_GRID as STACK } from "../../components/workbook/stack";
import type { ActionDriver } from "../../editor/protocol";
import { useYourPlan } from "../../editor/YourPlanContext";
import { YOUR_PLAN } from "../../editor/yourPlan";
import type { TieoutReport } from "../../generated/report";
import { B, ROWS } from "./bindings";
import { Track } from "./Track";
import { ACTION, DRIVER, OBSERVATION, WINDOWS, WS, WS_ROWS, actionSeries, driverSeries } from "./worksheetBindings";
import type { Window } from "./worksheetBindings";

type Sheet = Exclude<TieoutReport["worksheet"], { unavailable: string }>;
type Driver = Sheet["drivers"][number];

/** The two windows the report carries, in words: the first is this fiscal year, the second the next twelve months. */
const WINDOW_WORDS: Record<Window, string> = { "rest of fiscal year": "This fiscal year", "next twelve months": "Next twelve months" };

/** The rows' order for a window: the report's own rank (1 is the largest change), rows with none last, ties in the report's order. Nothing is parsed or subtracted. */
function byRank(ranks: ReadonlyArray<number | null>): number[] {
  return ranks
    .map((_, i) => i)
    .sort((a, b) => {
      const x = ranks[a];
      const y = ranks[b];
      if (x === y) return a < b ? -1 : 1;
      if (x === null) return 1;
      if (y === null) return -1;
      return x < y ? -1 : 1;
    });
}

const caption = "text-[11px] font-semibold uppercase text-slate-500";
/** The row's two halves: the track and its name on the left, the quiet figures on the right, side by side from the extra-large breakpoint. */
const rowGrid = "xl:grid xl:grid-cols-[58%_1fr] xl:items-center xl:gap-6";

/**
 * "What moves the outcome": the change in expected bookings against the plan in force when one driver or one action is
 * changed alone. The bars are the chart: one track per driver, widest change first by the report's own rank for the
 * window, low-setting bar and high-setting bar on a zero line shared by every row, with the dollar change printed at the
 * end of each bar. Beside each track, quietly, what the driver is now, what it would need to be alone, and where that
 * stands against history. The actions are a second group on a scale of their own, and say so. A switch chooses which of
 * the report's two windows is drawn; it selects, it does not calculate.
 */
export function Tornado({ sheet }: { sheet: Sheet }) {
  const [window, setWindow] = useState<Window>(WINDOWS[0]);
  const driverSpecs = useMemo(() => driverSeries(window), [window]);
  const actionSpecs = useMemo(() => actionSeries(window), [window]);
  const drivers = usePlot(useMemo(() => [driverSpecs.low, driverSpecs.high], [driverSpecs]));
  const actions = usePlot(useMemo(() => [actionSpecs.gain], [actionSpecs]));
  const stacked = sheet.bridge.steps.some((step) => step.kind === "actions");
  const driverOrder = byRank(sheet.drivers.map((d) => d.rank[window]));
  const actionOrder = byRank(sheet.actions.rows.map((a) => a.rank[window]));
  // room beyond the longest bar for the figure printed at its end
  const domain = useMemo(() => plotExtent(drivers.rows, ["low", "high"], { zero: true, padding: 0.3 }), [drivers.rows]);
  const actionDomain = useMemo(() => plotExtent(actions.rows, ["gain"], { zero: true, padding: 0.3 }), [actions.rows]);
  const { files } = useBindingContext();
  const comparison = files.report.actions;

  return (
    <Card className="p-4 sm:p-5" data-testid="tornado" data-window={window}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader title="What moves the outcome" />
        <div role="group" aria-label="Window" className="flex gap-2">
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              aria-pressed={w === window}
              data-window-choice={w}
              onClick={() => setWindow(w)}
              className={`rounded-ft border px-3 py-1 text-sm transition-colors ${
                w === window ? "border-ft-accent bg-ft-accentSoft font-semibold text-ft-brand" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
              }`}
            >
              {WINDOW_WORDS[w]}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-slate-600" data-testid="tornado-line">
        <Bound binding={WS.definition} />
      </p>

      <section className="mt-5" aria-label="Operating assumptions">
        <h3 className="font-display text-sm font-semibold text-ft-brand">Operating assumptions</h3>
        <p className="text-xs text-slate-500">Widest change first. Each driver has two bars: its historical low setting and its historical high setting.</p>
        <div className={`mt-2 hidden border-b border-slate-200 pb-1 ${rowGrid}`} aria-hidden="true">
          <span className={`${caption} xl:block`}>Change in bookings</span>
          <span className="hidden grid-cols-[1fr_1fr_1fr] gap-3 xl:grid">
            <span className={caption}>Current</span>
            <span className={caption}>Needed alone</span>
            <span className={caption}>Against history</span>
          </span>
        </div>
        <div className="divide-y divide-slate-100 xl:[&>*:first-child]:mt-0" data-testid="driver-list">
          {driverOrder.map((i) => (
            <DriverRow key={sheet.drivers[i].driver} driver={sheet.drivers[i]} row={drivers.rows[i]} index={i} window={window} domain={domain} stacked={stacked} />
          ))}
        </div>
      </section>

      <section className="mt-6" aria-label="One more hire, one more program">
        <h3 className="font-display text-sm font-semibold text-ft-brand">One more hire, one more program</h3>
        <p className="text-xs text-slate-500">One unit each, on the roster as signed: one AE hired next month, or one million dollars of program pipeline added next month.</p>
        <p className="mt-1 text-xs font-medium text-slate-700" data-testid="actions-scale-note">Not on the same scale as the drivers above.</p>
        {"unavailable" in comparison ? (
          <Callout color="amber" title="The two actions cannot be compared">
            <Bound binding={B.actionsUnavailable} />
          </Callout>
        ) : null}
        <div className="mt-2 divide-y divide-slate-100" data-testid="action-list">
          {actionOrder.map((i) => (
            <ActionRow key={sheet.actions.rows[i].kind} action={sheet.actions.rows[i]} row={actions.rows[i]} index={i} window={window} domain={actionDomain} />
          ))}
        </div>
      </section>

      <div className="mt-6">
        <Disclosure title="How to read this">
          <div className="flex flex-col gap-2 text-xs text-slate-700" data-testid="worksheet-guardrails">
            <p>
              Measured around <Bound binding={WS.measuredAround} />. Green is more booked and red is less. The drivers share one scale, with room at each end for the
              figure printed there; the actions have a scale of their own, because one unit of an action is small beside a driver&apos;s whole historical swing.
            </p>
            <p><Bound binding={WS.historyNote} /></p>
            <p><Bound binding={WS.sensitivityNote} /></p>
            <p><Bound binding={WS.expectationNote} /></p>
            {"unavailable" in comparison ? null : <ActionSentences />}
          </div>
        </Disclosure>
      </div>
    </Card>
  );
}

/** The sentences the report gives for the two unit actions, and the gap each would have to close. */
function ActionSentences() {
  return (
    <>
      <p><Bound binding={B.actionsDefinition} /></p>
      <p><Bound binding={B.actionsShape} /></p>
      <p><Bound binding={B.actionsMeaning} /></p>
      <p>
        The gap to close: <Bound binding={B.closeGap} />. Basis: <Bound binding={B.closeBasis} />.
      </p>
    </>
  );
}

/** Where the editor can be opened (a wide screen), a click on a row opens it; a button inside the row keeps its own click. */
function useOpenEditor() {
  const { company, choose } = useBindingContext();
  const yourPlan = useYourPlan();
  const wide = yourPlan?.desktop === true;
  return {
    wide,
    onClick: wide ? () => choose?.(company, YOUR_PLAN) : undefined,
    clickable: wide ? "cursor-pointer hover:bg-slate-50" : "",
    addToPlan: (kind: "hire" | "program") => {
      yourPlan?.store.append(company, kind);
      choose?.(company, YOUR_PLAN);
    },
    /** a draft action on the company for that driver, at the favorable end of the worksheet's settings; the form shows it, nothing is applied */
    addAction: (driver: ActionDriver, target: string) => {
      yourPlan?.store.draftAction(company, { slice: "company", driver, target, origin: "tornado" });
      choose?.(company, YOUR_PLAN);
    },
  };
}

function Toggle({ open, onToggle, controls, children }: { open: boolean; onToggle: () => void; controls: string; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controls}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className="text-xs font-medium text-ft-brand underline"
    >
      {children}
    </button>
  );
}

function DriverRow({ driver, row, index, window, domain, stacked }: { driver: Driver; row: PlotRow; index: number; window: Window; domain: [number, number]; stacked: boolean }) {
  const [open, setOpen] = useState(false);
  const editor = useOpenEditor();
  const { files } = useBindingContext();
  const acted = "items" in files.report.driver_actions ? files.report.driver_actions.items.filter((a) => a.driver === driver.driver) : [];
  // where the plan's own actions on this driver sit against the worksheet: the core's evidence, which does not depend on a solve
  const placed = acted.filter((a) => a.evidence.position !== "none");
  const outsideByAction = placed.some((a) => a.evidence.position !== "inside");
  const scaled = acted.length > 0 && driver.driver !== "win_rate" && driver.limitation !== null;
  // the plan's actions sit on the win rate: the core solves for no setting, and says so in the driver's limitation
  const unsolved = stacked && driver.driver === "win_rate" && driver.needed_alone === null && driver.cannot_scale_because === null;
  // the three drivers an action can change have a favorable end, the high; the cycle (a longer one is worse) has none yet
  const actionDriver = driver.driver === "cycle_days" ? null : driver.driver;
  const favorable = actionDriver !== null && driver.historical !== null ? driver.historical.high.setting : null;
  const path = `${WS_ROWS.drivers}/${index}`;
  const { display } = driver;
  const needed = driver.needed_alone;
  const solves = needed !== null && needed.outcome === "solves";
  const settingMark = (word: string, setting: ReactNode) => (
    <span className="block text-[10px] font-normal text-slate-500">
      {word}, at {setting}
    </span>
  );
  const marks = driver.historical === null ? {} : {
    low: (
      <>
        <Bound binding={DRIVER.lowChange[window]} row={path} className="text-xs font-semibold text-slate-900" />
        {settingMark("low", <Bound binding={DRIVER.lowSetting[display]} row={path} />)}
      </>
    ),
    high: (
      <>
        <Bound binding={DRIVER.highChange[window]} row={path} className="text-xs font-semibold text-slate-900" />
        {settingMark("high", <Bound binding={DRIVER.highSetting[display]} row={path} />)}
      </>
    ),
  };
  return (
    <div className="py-3">
      <div className={`${rowGrid} ${editor.clickable} rounded-ft`} onClick={editor.onClick} data-testid="driver-row" data-driver={driver.driver}>
        <div className="flex flex-col gap-1 xl:flex-row xl:items-center xl:gap-3">
          <div className="xl:w-36 xl:shrink-0">
            <div className="text-sm font-medium text-slate-900"><Bound binding={DRIVER.label} row={path} /></div>
            <div className="text-xs text-slate-500"><Bound binding={DRIVER.unitLabel} row={path} /></div>
          </div>
          <div className="h-24 w-full min-w-0 xl:h-24 xl:flex-1">
            {driver.historical === null ? (
              <p className="text-xs text-slate-600" data-testid="history-unavailable">
                <Bound binding={DRIVER.unavailable} row={path} />
              </p>
            ) : (
              <Track row={row} keys={["low", "high"]} domain={domain} label={`${driver.label}: change in bookings at its historical low and high settings`} marks={marks} />
            )}
          </div>
        </div>
        <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600 xl:mt-0 xl:grid-cols-[1fr_1fr_1fr] xl:gap-x-3" data-testid="driver-quiet">
          <div>
            <span className={`${caption} xl:hidden`}>Current </span>
            <span className="text-slate-700">
              <Bound binding={DRIVER.current[display]} row={path} />
            </span>
          </div>
          <div>
            <span className={`${caption} xl:hidden`}>Needed alone </span>
            <span className="text-slate-700">
              {unsolved ? "Not solved with actions in the plan" : needed === null ? <Bound binding={DRIVER.neededNone} row={path} /> : solves ? <Bound binding={DRIVER.neededValue[display]} row={path} /> : <Bound binding={DRIVER.neededLabel} row={path} />}
            </span>
          </div>
          <div className="col-span-2 flex flex-wrap items-center gap-2 xl:col-span-1">
            {needed !== null && needed.inside_observed_range !== null ? (
              <Badge color={needed.inside_observed_range ? "emerald" : "amber"} size="xs">
                {needed.inside_observed_range ? "Within historical settings" : "Outside historical settings"}
              </Badge>
            ) : needed === null && placed.length > 0 ? (
              <span data-testid="driver-position-pill">
                <Badge color={outsideByAction ? "amber" : "emerald"} size="xs">
                  {outsideByAction ? "Outside historical settings" : "Within historical settings"}
                </Badge>
              </span>
            ) : null}
            {editor.wide && actionDriver !== null && favorable !== null ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  editor.addAction(actionDriver, favorable);
                }}
                className="rounded-ft border border-ft-accent bg-white px-3 py-1 text-xs font-semibold text-ft-accent hover:bg-ft-accentSoft"
              >
                Add to plan
              </button>
            ) : null}
            <Toggle open={open} onToggle={() => setOpen((v) => !v)} controls={`driver-detail-${driver.driver}`}>
              {open ? "Hide the quarters" : "Show the quarters"}
            </Toggle>
          </div>
        </div>
        {scaled ? (
          <p className="mt-1 text-xs text-slate-600 xl:col-span-2" data-testid="driver-scaled" data-driver={driver.driver}>
            <Bound binding={DRIVER.scaled} row={path} />
          </p>
        ) : null}
        {unsolved ? (
          <p className="mt-1 text-xs text-slate-600 xl:col-span-2" data-testid="needed-stacked">
            <Bound binding={DRIVER.neededStacked} row={path} />
          </p>
        ) : null}
      </div>
      {open ? (
        <div id={`driver-detail-${driver.driver}`} className="mt-2 flex flex-col gap-3 rounded-ft bg-slate-50 px-3 py-3 text-xs text-slate-700" data-testid="driver-detail">
          <p>
            This is an assumption to discuss
            {driver.driver !== "cycle_days" && editor.wide
              ? ": add it to the plan as an action to give it a start month, a ramp and a target of your own."
              : ": it cannot be added to the plan as an item yet."}{" "}
            <Bound binding={DRIVER.appliesTo} row={path} />
          </p>
          {needed === null || needed.history_label === null ? null : <p><Bound binding={DRIVER.history} row={path} /></p>}
          {solves ? <p><Bound binding={DRIVER.neededLabel} row={path} /></p> : null}
          {needed === null || needed.reason_label === null ? null : <p><Bound binding={DRIVER.neededReason} row={path} /></p>}
          {needed !== null && needed.overshoot !== null ? <p>Overshoot at that setting: <Bound binding={DRIVER.overshoot} row={path} /></p> : null}
          {needed === null || needed.precision_note === null ? null : <p><Bound binding={DRIVER.precision} row={path} /></p>}
          {driver.historical === null ? null : (
            <p>
              Observed range <Bound binding={DRIVER.minimum[display]} row={path} /> to <Bound binding={DRIVER.maximum[display]} row={path} />. <Bound binding={DRIVER.rule} row={path} />
            </p>
          )}
          <p>
            <Bound binding={DRIVER.gate} row={path} /> <Bound binding={DRIVER.eligible} row={path} /> of <Bound binding={DRIVER.required} row={path} /> required quarters count.
          </p>
          <Observations driver={driver} path={path} />
          {driver.limitation === null ? null : (
            <p className="font-medium text-slate-800">
              <Bound binding={DRIVER.limitation} row={path} />
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

/** Every past quarter the report holds for the driver, with its sample counts: what counted and what did not. */
function Observations({ driver, path }: { driver: Driver; path: string }) {
  const { display } = driver;
  return (
    <Table className={STACK.table} data-testid="observations">
      <TableHead className={STACK.head}>
        <TableRow>
          <TableHeaderCell>Quarter</TableHeaderCell>
          <TableHeaderCell className="text-right">Deals created</TableHeaderCell>
          <TableHeaderCell className="text-right">Wins</TableHeaderCell>
          <TableHeaderCell className="text-right">Observed value</TableHeaderCell>
          <TableHeaderCell>Counted</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody className={STACK.body}>
        {driver.evidence.quarters.map((q, j) => {
          const row = `${path}/evidence/quarters/${j}`;
          return (
            <TableRow key={q.quarter} className={STACK.row} data-testid="observation-row">
              <TableCell className={`${STACK.title} text-xs`}><Bound binding={OBSERVATION.quarter} row={row} /></TableCell>
              <TableCell className={`${STACK.cell} text-xs`} data-label="Deals created"><Bound binding={OBSERVATION.created} row={row} /></TableCell>
              <TableCell className={`${STACK.cell} text-xs`} data-label="Wins"><Bound binding={OBSERVATION.wins} row={row} /></TableCell>
              <TableCell className={`${STACK.cell} text-xs`} data-label="Observed value"><Bound binding={OBSERVATION.value[display]} row={row} /></TableCell>
              <TableCell className={`${STACK.cell} text-xs sm:text-left`} data-label="Counted">
                <Badge color={q.eligible ? "emerald" : "slate"} size="xs">{q.eligible ? "counted" : "not counted"}</Badge>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

type ActionRowData = Sheet["actions"]["rows"][number];

function ActionRow({ action, row, index, window, domain }: { action: ActionRowData; row: PlotRow; index: number; window: Window; domain: [number, number] }) {
  const [open, setOpen] = useState(false);
  const editor = useOpenEditor();
  const { files } = useBindingContext();
  const path = `${WS_ROWS.actions}/${index}`;
  const supported = action.bookings_gained.value !== null;
  const comparison = files.report.actions;
  return (
    <div className="py-3">
      <div className={`${rowGrid} ${editor.clickable} rounded-ft`} onClick={editor.onClick} data-testid="worksheet-action-row" data-kind={action.kind}>
        <div className="flex flex-col gap-1 xl:flex-row xl:items-center xl:gap-3">
          <div className="text-sm font-medium text-slate-900 xl:w-36 xl:shrink-0">
            <Bound binding={ACTION.name} row={path} />
          </div>
          <div className="h-12 w-full min-w-0 xl:flex-1">
            {supported ? (
              <Track
                row={row}
                keys={["gain"]}
                domain={domain}
                label="Change in bookings from one unit of this action"
                marks={{ gain: <Bound binding={ACTION.gain[window]} row={path} className="text-xs font-semibold text-slate-900" /> }}
              />
            ) : (
              <p className="text-xs text-slate-600">
                <Bound binding={ACTION.gain[window]} row={path} />
              </p>
            )}
          </div>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 xl:mt-0" data-testid="action-quiet">
          <Badge color={action.closes_alone_outcome.value === "feasible" ? "emerald" : "amber"} size="xs">
            <Bound binding={ACTION.outcome} row={path} />
          </Badge>
          {editor.wide ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                editor.addToPlan(action.kind === "hire" ? "hire" : "program");
              }}
              className="rounded-ft border border-ft-accent bg-white px-3 py-1 text-xs font-semibold text-ft-accent hover:bg-ft-accentSoft"
            >
              Add to plan
            </button>
          ) : null}
          <Toggle open={open} onToggle={() => setOpen((v) => !v)} controls={`action-detail-${action.kind}`}>
            {open ? "Hide the details" : "Show the details"}
          </Toggle>
        </div>
      </div>
      {open ? (
        <div id={`action-detail-${action.kind}`} className="mt-2 flex flex-col gap-2 rounded-ft bg-slate-50 px-3 py-3 text-xs text-slate-700" data-testid="action-detail">
          <p><Bound binding={ACTION.closes} row={path} /></p>
          {"unavailable" in comparison ? null : <ActionFigures kind={action.kind} index={index} />}
        </div>
      ) : null}
    </div>
  );
}

/** What the old comparison and closes-alone tables said about this action: rank, gains, cost, gain per dollar, when it pays, and what closing the gap alone would take. */
function ActionFigures({ kind, index }: { kind: "hire" | "program"; index: number }) {
  const { files } = useBindingContext();
  const actions = files.report.actions;
  if ("unavailable" in actions) return null;
  const row = `${ROWS.actions}/${index}`;
  const close = actions.close_the_fiscal_year_gap;
  const hires = close.hires;
  return (
    <>
      <ul className="space-y-1" data-testid="action-figures">
        <li>Status: <Bound binding={B.aStatus} row={row} /></li>
        <li>Rank per dollar: <Bound binding={B.aRank} row={row} /></li>
        <li>Gain, rest of year: <Bound binding={B.aRest} row={row} /></li>
        <li>Gain, next twelve months: <Bound binding={B.aNext} row={row} /></li>
        <li>Cash cost, next twelve months: <Bound binding={B.aCost} row={row} /></li>
        <li>Gain per dollar: <Bound binding={B.aPerDollar} row={row} /></li>
        <li>Starts paying: <Bound binding={B.aStarts} row={row} /></li>
      </ul>
      {kind === "hire" ? (
        <section data-testid="close-hires">
          <p className="font-semibold text-ft-brand">To close the gap alone with hires: <Bound binding={B.hiresOutcome} /></p>
          {"bound" in hires ? (
            <ul className="mt-1 space-y-1">
              <li>Hires needed: <Bound binding={B.hiresCount} /></li>
              <li>The most the company has started in a quarter: <Bound binding={B.hiresBound} /> (<Bound binding={B.hiresBoundBasis} />)</li>
              <li>Cash cost, next twelve months: <Bound binding={B.hiresCost} /></li>
            </ul>
          ) : (
            <p className="mt-1"><Bound binding={B.hiresNote} /></p>
          )}
        </section>
      ) : (
        <section data-testid="close-program">
          <p className="font-semibold text-ft-brand">To close the gap alone with program pipeline: <Bound binding={B.programOutcome} /></p>
          <ul className="mt-1 space-y-1">
            <li>Pipeline needed: <Bound binding={B.programDollars} /></li>
            <li>
              {close.program.needed_but_over_the_cap !== null ? (
                <>
                  Over the cap: closing it would take <Bound binding={B.programOver} />, against a cap of <Bound binding={B.programCap} />
                </>
              ) : (
                <>
                  Within the cap of <Bound binding={B.programCap} />
                </>
              )}
            </li>
            <li>Cash cost, next twelve months: <Bound binding={B.programCost} /></li>
          </ul>
        </section>
      )}
    </>
  );
}
