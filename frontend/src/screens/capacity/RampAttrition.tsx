import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/** Ramp, attrition and the creation rate: each with where it came from (fitted, entered, default) and its sample. */
export function RampAttrition() {
  const ctx = useBindingContext();
  const rc = ctx.files.report.roster_capacity;
  const { ramp, attrition, creation_rate: creation } = rc;
  if (!ramp && !attrition && !creation) return null;
  const roster = rc.roster;
  return (
    <Card>
      <SectionHeader
        title="Ramp, attrition and the pipeline a rep creates"
        subtitle="Each rate says whether it was fitted from the history, entered by the company or left at a default, and what it rests on."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        {ramp ? (
          <section data-testid="ramp">
            <h3 className="text-sm font-semibold text-ft-brand">
              Ramp: <Bound binding={B.rampSource} />
            </h3>
            <p className="mt-1 text-xs text-slate-600">
              Sample: <Bound binding={B.rampSample} />
            </p>
            <p className="mt-1 text-xs text-slate-600"><Bound binding={B.rampDefinition} /></p>
            <p className="mt-1 text-xs text-slate-600">Afterwards: <Bound binding={B.rampAfter} /></p>
            {ramp.why_not_fitted !== "" ? (
              <p className="mt-1 text-xs text-slate-600">Why not fitted: <Bound binding={B.rampWhyNot} /></p>
            ) : null}
            {ramp.fitted_through !== null ? (
              <p className="mt-1 text-xs text-slate-600">Fitted through: <Bound binding={B.rampFittedThrough} /></p>
            ) : null}
            <p className="mt-1 text-xs text-slate-600">
              Deals left out: <Bound binding={B.rampLeftOut} />
              {ramp.deals_left_out.why !== null ? (
                <>
                  {" ("}
                  <Bound binding={B.rampLeftOutWhy} />
                  {")"}
                </>
              ) : null}
            </p>
            {ramp.limitation !== null ? (
              <p className="mt-2 border-l-2 border-amber-300 pl-3 text-xs text-slate-700">
                <Bound binding={B.rampLimitation} />
              </p>
            ) : null}
            <Table className={`${STACK.table} mt-3`}>
              <TableHead className={STACK.head}>
                <TableRow>
                  <TableHeaderCell>Tenure month</TableHeaderCell>
                  <TableHeaderCell className="text-right">Share of a tenured rep's pipeline</TableHeaderCell>
                  <TableHeaderCell className="text-right">95% range</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody className={STACK.body}>
                {ramp.weights.map((w, i) => {
                  const row = `${ROWS.weights}/${i}`;
                  return (
                    <TableRow key={i} className={STACK.row} data-testid="weight-row">
                      <TableCell className={STACK.cell} data-label="Tenure month"><Bound binding={B.wMonth} row={row} /></TableCell>
                      <TableCell className={STACK.cell} data-label="Share of a tenured rep's pipeline"><Bound binding={B.wWeight} row={row} /></TableCell>
                      <TableCell className={STACK.cell} data-label="95% range">
                        {Array.isArray(w.range95) ? (
                          <>
                            <Bound binding={B.wLow} row={row} /> to <Bound binding={B.wHigh} row={row} />
                          </>
                        ) : typeof w.range95 === "string" ? (
                          <Bound binding={B.wCeiling} row={row} />
                        ) : (
                          <Bound binding={B.wNoRange} row={row} />
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </section>
        ) : null}

        <div className="flex flex-col gap-6">
          {attrition ? (
            <section data-testid="attrition">
              <h3 className="text-sm font-semibold text-ft-brand">
                Attrition: <Bound binding={B.attritionSource} />
              </h3>
              <p className="mt-1 text-2xl font-semibold text-slate-900">
                <Bound binding={B.attritionRate} /> <span className="text-xs font-normal text-slate-500">per AE-month</span>
              </p>
              <p className="mt-1 text-xs text-slate-600">
                95% range: <Bound binding={B.attritionLow} />
                {attrition.range95 !== null ? (
                  <>
                    {" to "}
                    <Bound binding={B.attritionHigh} />
                  </>
                ) : null}
              </p>
              <p className="mt-1 text-xs text-slate-600">Sample: <Bound binding={B.attritionSample} /></p>
              {"unavailable" in roster ? null : (
                <p className="mt-1 text-xs text-slate-600">Departed to date: <Bound binding={B.departed} /></p>
              )}
              {attrition.why_not_fitted !== "" ? (
                <p className="mt-1 text-xs text-slate-600">Why not fitted: <Bound binding={B.attritionWhyNot} /></p>
              ) : null}
              <p className="mt-1 text-xs text-slate-500"><Bound binding={B.attritionForward} /></p>
            </section>
          ) : null}
          {creation ? (
            <section data-testid="creation-rate">
              <h3 className="text-sm font-semibold text-ft-brand">Deals created per ramped AE-month</h3>
              <p className="mt-1 text-2xl font-semibold text-slate-900"><Bound binding={B.creationRate} /></p>
              <p className="mt-1 text-xs text-slate-600">
                <Bound binding={B.creationDeals} /> deals over <Bound binding={B.creationMonths} /> ramped AE-months, <Bound binding={B.creationWindow} />
              </p>
            </section>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
