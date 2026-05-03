import {
  Badge,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../ui";
import type { ScenarioQuarterKey } from "../../engine/scenario";
import type { ScenarioQuarterSummaryRow } from "../../lib/scenarioPlanner";
import { formatMoney, formatSignedMoney } from "../../lib/scenarioPlanner";

interface MonthlyRow {
  month: string;
  basis: string;
  existing: number;
  future: number;
  uncapped: number;
  capped: number;
  capacity: number;
  overflow: number;
}

interface Props {
  quarterRows: ScenarioQuarterSummaryRow[];
  activeQuarter: ScenarioQuarterKey;
  monthlyRows: MonthlyRow[];
}

export function ScenarioSummaryTables({
  quarterRows,
  activeQuarter,
  monthlyRows,
}: Props) {
  return (
    <>
      <Card className="mb-6 p-5">
        <h3 className="text-sm font-semibold text-slate-900">Quarter Summary</h3>
        <p className="mt-1 text-xs text-slate-500">
          Locked quarters are baked-in actuals. Editable quarters only move when the active scenario departs from the saved trajectory.
        </p>
        <div className="mt-4">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Quarter</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell className="text-right">Plan Target</TableHeaderCell>
                <TableHeaderCell className="text-right">Baseline Forecast</TableHeaderCell>
                <TableHeaderCell className="text-right">Scenario Forecast</TableHeaderCell>
                <TableHeaderCell className="text-right">Scenario Uncapped</TableHeaderCell>
                <TableHeaderCell className="text-right">Gap To Plan</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {quarterRows.map((row) => (
                <TableRow
                  key={row.quarter}
                  className={
                    row.quarter === activeQuarter
                      ? "bg-blue-50/50 ring-1 ring-inset ring-blue-100"
                      : undefined
                  }
                >
                  <TableCell>
                    <div>
                      <div className="font-medium text-slate-900">{row.quarter}</div>
                      <div className="text-xs text-slate-500">
                        {row.monthRange}
                        {row.quarter === activeQuarter ? " · editing" : ""}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      color={
                        row.status === "Locked"
                          ? "emerald"
                          : row.status === "Override"
                            ? "blue"
                            : "gray"
                      }
                    >
                      {row.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {typeof row.planTarget === "number" ? formatMoney(row.planTarget) : "\u2014"}
                  </TableCell>
                  <TableCell className="text-right">{formatMoney(row.baselineCapped)}</TableCell>
                  <TableCell className="text-right font-medium">{formatMoney(row.scenarioCapped)}</TableCell>
                  <TableCell className="text-right">{formatMoney(row.scenarioExpected)}</TableCell>
                  <TableCell
                    className={`text-right font-medium ${
                      row.gapToPlan === null
                        ? "text-slate-500"
                        : row.gapToPlan >= 0
                          ? "text-emerald-600"
                          : "text-red-600"
                    }`}
                  >
                    {typeof row.gapToPlan === "number" ? formatSignedMoney(row.gapToPlan) : "\u2014"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-900">Monthly Breakdown</h3>
        <p className="mt-1 text-xs text-slate-500">
          Monthly uncapped demand, capped forecast, and overflow are shown directly from the
          trajectory model.
        </p>
        <div className="mt-4">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Month</TableHeaderCell>
                <TableHeaderCell>Basis</TableHeaderCell>
                <TableHeaderCell className="text-right">Existing</TableHeaderCell>
                <TableHeaderCell className="text-right">Future</TableHeaderCell>
                <TableHeaderCell className="text-right">Uncapped</TableHeaderCell>
                <TableHeaderCell className="text-right">Capped</TableHeaderCell>
                <TableHeaderCell className="text-right">Capacity</TableHeaderCell>
                <TableHeaderCell className="text-right">Overflow</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {monthlyRows.map((row) => (
                <TableRow key={row.month}>
                  <TableCell className="font-medium text-slate-900">{row.month}</TableCell>
                  <TableCell>
                    <Badge color={row.basis === "Actual" ? "emerald" : "gray"}>{row.basis}</Badge>
                  </TableCell>
                  <TableCell className="text-right">{formatMoney(row.existing)}</TableCell>
                  <TableCell className="text-right">{formatMoney(row.future)}</TableCell>
                  <TableCell className="text-right">{formatMoney(row.uncapped)}</TableCell>
                  <TableCell className="text-right font-medium">{formatMoney(row.capped)}</TableCell>
                  <TableCell className="text-right">{formatMoney(row.capacity)}</TableCell>
                  <TableCell className="text-right">{formatMoney(row.overflow)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </>
  );
}
