import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import { plotExtent } from "../../binding/chartData";
import { usePlot } from "../../binding/ChartKit";
import { Badge, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, Text } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { useYourPlan } from "../../editor/YourPlanContext";
import { YOUR_PLAN } from "../../editor/yourPlan";
import { STACK, STACK_XL } from "../../components/workbook/stack";
import type { TieoutReport } from "../../generated/report";
import { AxisHeader, BarCell } from "./BarCell";
import { ACTION, DRIVER, OBSERVATION, WINDOWS, WS, WS_ROWS, actionSeries, driverSeries } from "./worksheetBindings";
import type { Window } from "./worksheetBindings";

type Sheet = Exclude<TieoutReport["worksheet"], { unavailable: string }>;
type Driver = Sheet["drivers"][number];

/** The two windows the report carries, in words: the first is this fiscal year, the second the next twelve months. */
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

const WINDOW_WORDS: Record<Window, string> = { "rest of fiscal year": "This fiscal year", "next twelve months": "Next twelve months" };

/**
 * "What moves the outcome": the change in expected bookings against the plan in force when one driver or one action
 * is changed alone. Two groups, each with its own heading and never ranked together: the operating assumptions (two
 * bars each, at the company's own historical low and high settings) and the actions (one bar each). A switch chooses
 * which of the report's two windows is drawn; it selects, it does not calculate. Every bar is drawn from the report's
 * figure; the table beside each bar carries the figure, the setting, what is needed alone and where history stands.
 */
export function Tornado({ sheet }: { sheet: Sheet }) {
  const [window, setWindow] = useState<Window>(WINDOWS[0]);
  const driverSpecs = useMemo(() => driverSeries(window), [window]);
  const actionSpecs = useMemo(() => actionSeries(window), [window]);
  const drivers = usePlot(useMemo(() => [driverSpecs.low, driverSpecs.high], [driverSpecs]));
  const actions = usePlot(useMemo(() => [actionSpecs.gain], [actionSpecs]));
  const driverOrder = byRank(sheet.drivers.map((d) => d.rank[window]));
  const actionOrder = byRank(sheet.actions.rows.map((a) => a.rank[window]));
  // one scale for both groups and every bar, so that a bar's length means the same dollars wherever it is drawn
  const domain = useMemo(() => plotExtent([...drivers.rows, ...actions.rows], ["low", "high", "gain"], { zero: true, padding: 0.04 }), [drivers.rows, actions.rows]);

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
      <Text className="mt-1 text-xs text-slate-600">
        <Bound binding={WS.definition} /> Measured around <Bound binding={WS.measuredAround} />.
      </Text>
      <p className="mt-3 text-xs text-slate-500">
        The bars show the change in bookings against the plan in force, on one scale for both groups: green is more booked, red is less. A single unit of an action is small
        beside a driver's whole historical swing, so its bar is short; its figure is beside it. Each driver has two bars, the upper at its historical low setting and the lower at its historical high setting.
      </p>

      <Group title="Operating assumptions" subtitle="Each driver is changed alone, for deals created after the as-of date.">
        <Table className={STACK_XL.table} data-testid="driver-table">
          <TableHead className={STACK_XL.head}>
            <TableRow>
              <TableHeaderCell>Driver</TableHeaderCell>
              <TableHeaderCell className="p-0"><AxisHeader domain={domain} /></TableHeaderCell>
              <TableHeaderCell>Current</TableHeaderCell>
              <TableHeaderCell>Historical low to high</TableHeaderCell>
              <TableHeaderCell>Needed alone</TableHeaderCell>
              <TableHeaderCell>Inside history</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK_XL.body}>
            {driverOrder.map((i) => (
              <DriverRow key={sheet.drivers[i].driver} driver={sheet.drivers[i]} row={drivers.rows[i]} index={i} window={window} domain={domain} />
            ))}
          </TableBody>
        </Table>
      </Group>

      <Group title="Actions" subtitle="One unit each, on the roster as signed: one AE hired next month, or one million dollars of program pipeline added next month.">
        <Table className={STACK_XL.table} data-testid="action-table">
          <TableHead className={STACK_XL.head}>
            <TableRow>
              <TableHeaderCell>Action</TableHeaderCell>
              <TableHeaderCell className="p-0"><AxisHeader domain={domain} /></TableHeaderCell>
              <TableHeaderCell>Change in bookings</TableHeaderCell>
              <TableHeaderCell>Closes the gap alone</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK_XL.body}>
            {actionOrder.map((i) => (
              <ActionRow key={sheet.actions.rows[i].kind} row={actions.rows[i]} index={i} window={window} domain={domain} kind={sheet.actions.rows[i].kind} supported={sheet.actions.rows[i].bookings_gained.value !== null} />
            ))}
          </TableBody>
        </Table>
      </Group>
      <div className="mt-6 rounded-ft border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700" data-testid="worksheet-guardrails">
        <p><Bound binding={WS.historyNote} /></p>
        <p className="mt-1"><Bound binding={WS.sensitivityNote} /></p>
        <p className="mt-1"><Bound binding={WS.expectationNote} /></p>
      </div>
    </Card>
  );
}

/** Where the editor can be opened (a wide screen), a click on a row or its bar opens it; a button inside the row keeps its own click. */
function useOpenEditor() {
  const { company, choose } = useBindingContext();
  const yourPlan = useYourPlan();
  const wide = yourPlan?.desktop === true;
  return {
    wide,
    rowProps: wide
      ? { onClick: () => choose?.(company, YOUR_PLAN), className: "cursor-pointer hover:bg-slate-50", title: "Open the editor" }
      : { className: "" },
    addToPlan: (kind: "hire" | "program") => {
      yourPlan?.store.append(company, kind);
      choose?.(company, YOUR_PLAN);
    },
  };
}

function Group({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="mt-6" aria-label={title}>
      <h3 className="font-display text-sm font-semibold text-ft-brand">{title}</h3>
      <p className="mb-2 text-xs text-slate-500">{subtitle}</p>
      {children}
    </section>
  );
}

function DriverRow({ driver, row, index, window, domain }: { driver: Driver; row: Parameters<typeof BarCell>[0]["row"]; index: number; window: Window; domain: [number, number] }) {
  const [open, setOpen] = useState(false);
  const path = `${WS_ROWS.drivers}/${index}`;
  const { display } = driver;
  const editor = useOpenEditor();
  const needed = driver.needed_alone;
  const solves = needed !== null && needed.outcome === "solves";
  return (
    <>
      <TableRow className={`${STACK_XL.row} ${editor.rowProps.className}`} onClick={editor.rowProps.onClick} data-testid="driver-row" data-driver={driver.driver}>
        <TableCell className={STACK_XL.title}>
          <div className="font-medium"><Bound binding={DRIVER.label} row={path} /></div>
          <div className="text-xs font-normal text-slate-500"><Bound binding={DRIVER.unitLabel} row={path} /></div>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={`driver-detail-${driver.driver}`}
            onClick={(e) => {
              e.stopPropagation();
              setOpen((v) => !v);
            }}
            className="mt-1 text-xs font-medium text-ft-brand underline"
          >
            {open ? "Hide the quarters" : "Show the quarters"}
          </button>
        </TableCell>
        <TableCell className="block px-0 py-1 xl:relative xl:table-cell xl:w-[26%] xl:min-w-[220px] xl:p-0">
          {driver.historical === null ? (
            <p className="text-xs text-slate-600 xl:px-3 xl:py-3" data-testid="history-unavailable">
              <Bound binding={DRIVER.unavailable} row={path} />
            </p>
          ) : (
            <BarCell row={row} keys={["low", "high"]} domain={domain} label={`${driver.label}: change in bookings at its historical low and high settings`} />
          )}
        </TableCell>
        <TableCell className={STACK_XL.cell} data-label="Current">
          <span>
            <Bound binding={DRIVER.current[display]} row={path} />
          </span>
        </TableCell>
        <TableCell className={STACK_XL.cell} data-label="Historical low to high">
          {driver.historical === null ? (
            <span className="text-xs text-slate-600">no historical setting</span>
          ) : (
            <span className="flex flex-col gap-1 xl:text-left">
              <span className="text-xs">
                <span className="text-slate-500">Low </span>
                <Bound binding={DRIVER.lowSetting[display]} row={path} /> <span className="text-slate-500">moves bookings by</span>{" "}
                <Bound binding={DRIVER.lowChange[window]} row={path} className="font-medium" />
              </span>
              <span className="text-xs">
                <span className="text-slate-500">High </span>
                <Bound binding={DRIVER.highSetting[display]} row={path} /> <span className="text-slate-500">moves bookings by</span>{" "}
                <Bound binding={DRIVER.highChange[window]} row={path} className="font-medium" />
              </span>
            </span>
          )}
        </TableCell>
        <TableCell className={STACK_XL.cell} data-label="Needed alone">
          <span className="text-xs xl:text-sm">
            {needed === null ? <Bound binding={DRIVER.neededNone} row={path} /> : solves ? <Bound binding={DRIVER.neededValue[display]} row={path} /> : <Bound binding={DRIVER.neededLabel} row={path} />}
          </span>
        </TableCell>
        <TableCell className={STACK_XL.cell} data-label="Inside history">
          <span className="text-xs">
            <Bound binding={DRIVER.history} row={path} />
          </span>
        </TableCell>
      </TableRow>
      {open ? (
        <TableRow className={`${STACK_XL.row} bg-slate-50`} data-testid="driver-detail">
          <TableCell colSpan={6} className="block px-3 py-3 xl:table-cell">
            <div id={`driver-detail-${driver.driver}`} className="flex flex-col gap-3 text-xs text-slate-700">
              <p>
                This is an assumption to discuss: it cannot be added to the plan as an item yet. <Bound binding={DRIVER.appliesTo} row={path} />
              </p>
              {solves ? <p><Bound binding={DRIVER.neededLabel} row={path} /></p> : null}
              {needed === null || needed.reason_label === null ? null : <p><Bound binding={DRIVER.neededReason} row={path} /></p>}
              {needed !== null && needed.overshoot !== null ? (
                <p>Overshoot at that setting: <Bound binding={DRIVER.overshoot} row={path} /></p>
              ) : null}
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
          </TableCell>
        </TableRow>
      ) : null}
    </>
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

function ActionRow({ row, index, window, domain, kind, supported }: { row: Parameters<typeof BarCell>[0]["row"]; index: number; window: Window; domain: [number, number]; kind: string; supported: boolean }) {
  const path = `${WS_ROWS.actions}/${index}`;
  const editor = useOpenEditor();
  return (
    <TableRow className={`${STACK_XL.row} ${editor.rowProps.className}`} onClick={editor.rowProps.onClick} data-testid="worksheet-action-row" data-kind={kind}>
      <TableCell className={STACK_XL.title}>
        <Bound binding={ACTION.name} row={path} />
      </TableCell>
      <TableCell className="block px-0 py-1 xl:relative xl:table-cell xl:w-[26%] xl:min-w-[220px] xl:p-0">
        {supported ? (
          <BarCell row={row} keys={["gain"]} domain={domain} label="Change in bookings from one unit of this action" />
        ) : (
          <p className="text-xs text-slate-600 xl:px-3 xl:py-3">
            <Bound binding={ACTION.gain[window]} row={path} />
          </p>
        )}
      </TableCell>
      <TableCell className={STACK_XL.cell} data-label="Change in bookings">
        {supported ? <Bound binding={ACTION.gain[window]} row={path} /> : <span aria-hidden="true">&mdash;</span>}
      </TableCell>
      <TableCell className={STACK_XL.cell} data-label="Closes the gap alone">
        <span className="text-xs"><Bound binding={ACTION.closes} row={path} /></span>
        {editor.wide ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              editor.addToPlan(kind === "hire" ? "hire" : "program");
            }}
            className="mt-2 block rounded-ft border border-ft-accent bg-white px-3 py-1 text-xs font-semibold text-ft-accent hover:bg-ft-accentSoft"
          >
            Add to plan
          </button>
        ) : null}
      </TableCell>
    </TableRow>
  );
}
