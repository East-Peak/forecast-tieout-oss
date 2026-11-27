import { Fragment, useState } from "react";
import { Bound, useBindingContext } from "../../binding/Bound";
import { Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { SectionHeader } from "../../components/workbook";
import { STACK } from "../../components/workbook/stack";
import { B, ROWS } from "./bindings";

/**
 * Quota against what was observed, for all reps and each segment, and the total quota over the target.
 * A row opens to the spread across reps (the spread is of attainment per rep, so a median can sit far from the total).
 */
export function QuotaCard() {
  const { files } = useBindingContext();
  const quota = files.report.quota_productivity;
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (row: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(row)) next.delete(row);
      else next.add(row);
      return next;
    });

  if ("unavailable" in quota) {
    return (
      <Card>
        <SectionHeader title="Quota against what was observed" />
        <p className="text-sm text-slate-700">
          Quota against attainment is unavailable: <Bound binding={B.quotaUnavailable} />
        </p>
      </Card>
    );
  }
  const groups: Array<{ name: string | null; row: string; spread: boolean }> = [
    { name: null, row: ROWS.allReps, spread: quota.all_reps.spread_across_reps !== null },
    ...Object.entries(quota.by_segment).map(([name, group]) => ({
      name,
      row: `${ROWS.bySegment}/${name}`,
      spread: group?.spread_across_reps !== null,
    })),
  ];
  return (
    <Card>
      <SectionHeader
        title="Quota against what was observed"
        subtitle="Wins credited to each owner over their quota, prorated by the days they were employed in the window."
      />
      <p className="mb-3 text-xs text-slate-600">
        <Bound binding={B.quotaDefinition} />. Window: <Bound binding={B.quotaWindow} />.
      </p>
      <Table className={STACK.table}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell>Group</TableHeaderCell>
            <TableHeaderCell className="text-right">Reps</TableHeaderCell>
            <TableHeaderCell className="text-right">Prorated quota</TableHeaderCell>
            <TableHeaderCell className="text-right">Wins credited</TableHeaderCell>
            <TableHeaderCell className="text-right">Attainment</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {groups.map((g) => {
            const expanded = open.has(g.row);
            return (
              <Fragment key={g.row}>
                <TableRow className={STACK.row} data-testid="quota-row">
                  <TableCell className={`${STACK.title} whitespace-nowrap`}>
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-label={`Show the spread across reps for ${g.name ?? "all reps"}`}
                      onClick={() => toggle(g.row)}
                      className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                    </button>
                    <span className="capitalize">{g.name === null ? "All reps" : g.name.split("_").join(" ")}</span>
                  </TableCell>
                  <TableCell className={STACK.cell} data-label="Reps"><Bound binding={B.gReps} row={g.row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Prorated quota"><Bound binding={B.gQuota} row={g.row} /></TableCell>
                  <TableCell className={STACK.cell} data-label="Wins credited"><Bound binding={B.gWins} row={g.row} /></TableCell>
                  <TableCell className={`${STACK.cell} font-medium`} data-label="Attainment"><Bound binding={B.gAttainment} row={g.row} /></TableCell>
                </TableRow>
                {expanded ? (
                  <TableRow className="block bg-slate-50 sm:table-row" data-testid="quota-detail">
                    <TableCell colSpan={5} className="block px-3 py-2 text-xs text-slate-600 sm:table-cell">
                      Reps in the spread: <Bound binding={B.gSpreadReps} row={g.row} />.{" "}
                      {g.spread ? (
                        <>
                          Attainment across reps: lowest <Bound binding={B.gMin} row={g.row} />, a quarter below{" "}
                          <Bound binding={B.gP25} row={g.row} />, median <Bound binding={B.gMedian} row={g.row} />, a quarter above{" "}
                          <Bound binding={B.gP75} row={g.row} />, highest <Bound binding={B.gMax} row={g.row} />.
                        </>
                      ) : (
                        <>
                          Attainment across reps: <Bound binding={B.gMedian} row={g.row} />.
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
      <div className="mt-4 grid gap-x-6 gap-y-2 text-xs text-slate-600 sm:grid-cols-2">
        <p>
          <span className="font-semibold text-ft-brand">Total quota over target: </span>
          <Bound binding={B.quotaAnnual} /> of full-ramp annual quota across <Bound binding={B.quotaPeople} /> people, against a target of{" "}
          <Bound binding={B.quotaTarget} />. <Bound binding={B.quotaNote} />
        </p>
        <p>
          <span className="font-semibold text-ft-brand">Where the wins went: </span>
          <Bound binding={B.winsCredited} /> credited of <Bound binding={B.winsInWindow} /> won in the window;{" "}
          <Bound binding={B.winsUnattributed} /> unattributed. <Bound binding={B.unattributedNote} />
        </p>
        <p>
          Reps without a quota: <Bound binding={B.repsWithoutQuota} />. A spread needs at least <Bound binding={B.spreadMinDays} /> days employed.
        </p>
      </div>
    </Card>
  );
}
