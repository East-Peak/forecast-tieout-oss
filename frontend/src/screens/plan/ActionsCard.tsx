import { Bound, useBindingContext } from "../../binding/Bound";
import { Callout, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/**
 * The two unit actions through the same forward function, compared (a hire and a programme), and what each
 * would have to be to close the year's gap alone. An action that cannot be valued says why, in the report's words.
 */
export function ActionsCard() {
  const { files } = useBindingContext();
  const actions = files.report.actions;
  if ("unavailable" in actions) {
    return (
      <Callout color="amber" title="The two actions cannot be compared">
        <Bound binding={B.actionsUnavailable} />
      </Callout>
    );
  }
  const best = actions.comparison.findIndex((a) => a.rank === 1);
  const close = actions.close_the_fiscal_year_gap;
  const hires = close.hires;
  return (
    <>
      <Card>
        <SectionHeader title="One hire against one programme" subtitle="Each action alone, on the roster as signed: what it gains, what it costs, and when it starts to pay." />
        {best >= 0 ? (
          <p className="mb-3 text-sm text-slate-700" data-testid="better-per-dollar">
            <span className="font-semibold text-ft-brand">Better per dollar: </span>
            <Bound binding={B.bestAction} row={`${ROWS.actions}/${best}`} />, at <Bound binding={B.bestPerDollar} row={`${ROWS.actions}/${best}`} /> bookings gained per cash dollar.
          </p>
        ) : (
          <p className="mb-3 text-sm text-slate-700" data-testid="better-per-dollar">No action is ranked: the table says why.</p>
        )}
        <Table className={STACK.table}>
          <TableHead className={STACK.head}>
            <TableRow>
              <TableHeaderCell>Action</TableHeaderCell>
              <TableHeaderCell className="text-right">Rank</TableHeaderCell>
              <TableHeaderCell className="text-right">Gain, rest of year</TableHeaderCell>
              <TableHeaderCell className="text-right">Gain, next twelve months</TableHeaderCell>
              <TableHeaderCell className="text-right">Cash cost, next twelve months</TableHeaderCell>
              <TableHeaderCell className="text-right">Gain per dollar</TableHeaderCell>
              <TableHeaderCell className="text-right">Starts paying</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody className={STACK.body}>
            {actions.comparison.map((_, i) => {
              const row = `${ROWS.actions}/${i}`;
              return (
                <TableRow key={i} className={STACK.row} data-testid="action-row">
                  <TableCell className={STACK.title}>
                    <Bound binding={B.aAction} row={row} />
                    <div className="text-xs font-normal text-slate-500"><Bound binding={B.aStatus} row={row} /></div>
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="Rank"><Bound binding={B.aRank} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Gain, rest of year"><Bound binding={B.aRest} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Gain, next twelve months"><Bound binding={B.aNext} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Cash cost, next twelve months"><Bound binding={B.aCost} row={row} /></TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="Gain per dollar"><Bound binding={B.aPerDollar} row={row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Starts paying"><Bound binding={B.aStarts} row={row} /></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <p className="mt-3 text-xs text-slate-600"><Bound binding={B.actionsDefinition} /></p>
        <p className="mt-1 text-xs text-slate-500"><Bound binding={B.actionsShape} /></p>
        <p className="mt-1 text-xs text-slate-500"><Bound binding={B.actionsMeaning} /></p>
      </Card>

      <Card>
        <SectionHeader
          title="What closes the year's gap alone"
          subtitle="Each action on its own, to close the gap to the year's target; 'feasible' means inside the model's bounds, not operationally achievable."
        />
        <p className="mb-3 text-xs text-slate-600">
          The gap to close: <Bound binding={B.closeGap} />. Basis: <Bound binding={B.closeBasis} />.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <section data-testid="close-hires">
            <h3 className="text-sm font-semibold text-ft-brand">Hires</h3>
            <p className="mt-1 text-lg font-semibold text-slate-900"><Bound binding={B.hiresOutcome} /></p>
            {"bound" in hires ? (
              <ul className="mt-1 space-y-1 text-xs text-slate-600">
                <li>Hires needed: <Bound binding={B.hiresCount} /></li>
                <li>The most the company has started in a quarter: <Bound binding={B.hiresBound} /> (<Bound binding={B.hiresBoundBasis} />)</li>
                <li>Cash cost, next twelve months: <Bound binding={B.hiresCost} /></li>
              </ul>
            ) : (
              <p className="mt-1 text-xs text-slate-600"><Bound binding={B.hiresNote} /></p>
            )}
          </section>
          <section data-testid="close-programme">
            <h3 className="text-sm font-semibold text-ft-brand">Programme pipeline</h3>
            <p className="mt-1 text-lg font-semibold text-slate-900"><Bound binding={B.programmeOutcome} /></p>
            <ul className="mt-1 space-y-1 text-xs text-slate-600">
              <li>Pipeline needed: <Bound binding={B.programmeDollars} /></li>
              <li>
                {close.programme.needed_but_over_the_cap !== null ? (
                  <>
                    Over the cap: closing it would take <Bound binding={B.programmeOver} />, against a cap of <Bound binding={B.programmeCap} />
                  </>
                ) : (
                  <>
                    Within the cap of <Bound binding={B.programmeCap} />
                  </>
                )}
              </li>
              <li>Cash cost, next twelve months: <Bound binding={B.programmeCost} /></li>
            </ul>
          </section>
        </div>
      </Card>
    </>
  );
}
