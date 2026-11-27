import { useMemo } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import { plotExtent, plotPoint } from "../../binding/chartData";
import { usePlot } from "../../binding/ChartKit";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, Text } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK_GRID as STACK } from "../../components/workbook/stack";
import type { TieoutReport } from "../../generated/report";
import { CHART_COLORS } from "../../lib/chartTheme";
import { AxisHeader, BarCell, direction } from "./BarCell";
import { BRIDGE_SERIES, STEP, WS, WS_ROWS } from "./worksheetBindings";

type Sheet = Exclude<TieoutReport["worksheet"], { unavailable: string }>;

const SPECS = [BRIDGE_SERIES.total, BRIDGE_SERIES.move, BRIDGE_SERIES.gap];
const KEYS = ["total", "move", "gap"] as const;

/** Totals are one neutral color; each item runs green or red by its direction; the remaining gap is the color of a shortfall. */
const fill = (key: string, value: unknown) => (key === "total" ? CHART_COLORS.slate : key === "gap" ? CHART_COLORS.negative : direction(value));

/**
 * "How this plan reconciles": from the roster as signed, through each item of the plan in its declared order, to the
 * working plan, and from there the remaining gap to the target. The steps are the report's own (each with its start
 * and end), drawn as floating bars on a scale that does not start at zero, so that the steps can be seen. With no
 * plan there is nothing to reconcile, and the section says so in a line instead of drawing an empty chart.
 */
export function Bridge({ sheet }: { sheet: Sheet }) {
  const { files } = useBindingContext();
  const { rows } = usePlot(SPECS);
  const domain = useMemo(() => plotExtent(rows, KEYS, { zero: false, padding: 0.08 }), [rows]);
  const target = useMemo(() => plotPoint(files.report, "/worksheet/bridge/target/value"), [files.report]);
  return (
    <Card className="p-4 sm:p-5" data-testid="bridge">
      <SectionHeader title="How this plan reconciles" subtitle={undefined} />
      {sheet.plan_in_force ? (
        <>
          <Text className="-mt-3 text-xs text-slate-600">
            Expected <Bound binding={WS.bridgeMeasure} />, from the roster as signed through each item of the plan to the working plan, then what is left to the target of{" "}
            <Bound binding={WS.bridgeTarget} />. The scale does not start at zero: read the bars as changes, not totals.
          </Text>
          <Table className={`${STACK.table} mt-3`} data-testid="bridge-table">
            <TableHead className={STACK.head}>
              <TableRow>
                <TableHeaderCell>Step</TableHeaderCell>
                <TableHeaderCell className="p-0"><AxisHeader domain={domain} /></TableHeaderCell>
                <TableHeaderCell className="text-right">Change</TableHeaderCell>
                <TableHeaderCell className="text-right">Amount</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody className={STACK.body}>
              {sheet.bridge.steps.map((step, i) => {
                const path = `${WS_ROWS.steps}/${i}`;
                return (
                  <TableRow key={`${step.kind}-${i}`} className={STACK.row} data-testid="bridge-row" data-kind={step.kind}>
                    <TableCell className={STACK.title}>
                      <Bound binding={STEP.label} row={path} />
                      {step.note === null ? null : <div className="text-xs font-normal text-slate-500"><Bound binding={STEP.note} row={path} /></div>}
                    </TableCell>
                    <TableCell className="hidden sm:relative sm:table-cell sm:w-[34%] sm:min-w-[200px] sm:p-0">
                      <BarCell row={rows[i]} keys={KEYS} domain={domain} label={step.label} fill={fill} reference={target} />
                    </TableCell>
                    <TableCell className={STACK.cell} data-label="Change">
                      {step.change === null ? <span aria-hidden="true">&mdash;</span> : <Bound binding={STEP.change} row={path} />}
                    </TableCell>
                    <TableCell className={STACK.cell} data-label="Amount">
                      <Bound binding={STEP.level} row={path} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <p className="mt-3 text-xs text-slate-500">
            <Bound binding={WS.bridgeOrder} /> The dashed line is the target.
          </p>
        </>
      ) : (
        <p className="-mt-3 text-xs text-slate-700" data-testid="bridge-no-plan">
          No plan is in force, so there is nothing to reconcile: the working plan is the roster as signed.
        </p>
      )}
    </Card>
  );
}
