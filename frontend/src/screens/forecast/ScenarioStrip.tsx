import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Callout, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { B, ROWS } from "./bindings";

/** What the chosen scenario is and, for a plan, what it changes against the roster as signed (figures from comparison.json). */
export function ScenarioStrip() {
  const { files, scenario } = useBindingContext();
  const plan = files.report.plan;
  const isBaseline = files.comparison.baseline === scenario;
  return (
    <Card>
      <SectionHeader title="This scenario" />
      <p className="mb-3 text-sm text-slate-700">
        <span className="font-semibold text-ft-brand">
          <Bound binding={B.scenarioLabel} />
        </span>
        {": "}
        <Bound binding={B.scenarioDescription} />
      </p>
      {isBaseline ? (
        <p className="text-xs text-slate-500">
          Every figure above is for the roster as signed. Choose another scenario to see what a plan changes.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
            <Figure label="Expected year with the plan" binding={<Bound binding={B.cmpExpected} />} />
            <Figure label="Gap with the plan" binding={<Bound binding={B.cmpGap} />} />
            <Figure label="Gap changes by" binding={<Bound binding={B.cmpGapChange} />} />
            <Figure label="More booked, rest of year" binding={<Bound binding={B.cmpBookingsRest} />} />
            <Figure label="More booked, next twelve months" binding={<Bound binding={B.cmpBookingsNext} />} />
            <Figure label="Cash cost, next twelve months" binding={<Bound binding={B.cmpCost} />} />
          </dl>
          {plan && "unavailable" in plan ? (
            <Callout color="amber" className="mt-4">
              The plan cannot be valued: <Bound binding={B.planUnavailable} />
            </Callout>
          ) : plan ? (
            <div className="mt-4">
              <p className="mb-2 text-xs text-slate-500">
                <Bound binding={B.planDefinition} />
              </p>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Item</TableHeaderCell>
                    <TableHeaderCell className="text-right">More booked, rest of year</TableHeaderCell>
                    <TableHeaderCell className="text-right">Cash cost, next twelve months</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {plan.items.map((_, i) => {
                    const row = `${ROWS.planItem}/${i}`;
                    return (
                      <TableRow key={i} data-testid="plan-item-row">
                        <TableCell>
                          <div className="font-medium"><Bound binding={B.pItemLabel} row={row} /></div>
                          <div className="text-xs text-slate-500"><Bound binding={B.pItemDetail} row={row} /></div>
                        </TableCell>
                        <TableCell className="text-right"><Bound binding={B.pItemContribution} row={row} /></TableCell>
                        <TableCell className="text-right"><Bound binding={B.pItemCost} row={row} /></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function Figure({ label, binding }: { label: string; binding: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-medium uppercase text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-slate-900">{binding}</dd>
    </div>
  );
}
