import type { ReactNode } from "react";
import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { Badge, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { B, ROWS } from "./bindings";

type Tone = "green" | "red" | "amber" | "slate";

/** The tone of a verdict is read from its words in the report; nothing is computed. */
function toneOf(verdict: string): Tone {
  if (verdict === "yes") return "green";
  if (verdict === "no") return "red";
  return "slate";
}

/** The tone of one comparison is read from the report's own outcome word. */
function outcomeTone(outcome: string): Tone {
  if (outcome === "model lower") return "green";
  if (outcome === "baseline lower") return "red";
  return "slate";
}

function Verdict({
  question,
  verdict,
  reason,
  tone,
  children,
}: {
  question: string;
  verdict: Binding;
  reason: Binding;
  tone?: Tone;
  children?: ReactNode;
}) {
  const ctx = useBindingContext();
  const word = String(readBinding(ctx, verdict));
  return (
    <Card className="p-4" data-testid="verdict-card">
      <p className="text-xs font-medium text-slate-500">{question}</p>
      <div className="mt-2 flex items-center gap-2">
        <Badge color={tone ?? toneOf(word)} className="text-sm">
          <Bound binding={verdict} />
        </Badge>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-600">
        <Bound binding={reason} />
      </p>
      {children}
    </Card>
  );
}

/** A baseline's error with, beneath it, the report's word for which of the two is lower. */
function Against({ error, outcome, row }: { error: Binding; outcome: Binding; row: string }) {
  const ctx = useBindingContext();
  return (
    <TableCell className="px-1 py-2 text-right align-top">
      <Bound binding={error} row={row} />
      <div className="mt-1">
        <Badge color={outcomeTone(String(readBinding(ctx, outcome, row)))} size="xs">
          <Bound binding={outcome} row={row} />
        </Badge>
      </div>
    </TableCell>
  );
}

/** The back-test errors the verdict rests on, for each horizon the rule uses; absent when there is no verdict. */
function Comparison() {
  const { files } = useBindingContext();
  const rows = files.report.verdicts.forecast_better_than_baselines.comparisons;
  if (rows.length === 0) return null;
  return (
    <>
      <p className="mt-3 text-[11px] text-slate-500">Average miss in dollars on the past, lower is better.</p>
      <Table className="mt-1 text-xs">
        <TableHead>
          <TableRow>
            <TableHeaderCell className="px-1 py-1 text-left">Months ahead</TableHeaderCell>
            <TableHeaderCell className="px-1 py-1 text-right">Fitted model</TableHeaderCell>
            <TableHeaderCell className="px-1 py-1 text-right">Stage-weighted pipeline</TableHeaderCell>
            <TableHeaderCell className="px-1 py-1 text-right">Last twelve months' pace</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((_, i) => {
            const row = `${ROWS.betterComparisons}/${i}`;
            return (
              <TableRow key={i} data-testid="verdict-comparison-row">
                <TableCell className="px-1 py-2 align-top">
                  <Bound binding={B.cmpMonths} row={row} />
                </TableCell>
                <TableCell className="px-1 py-2 text-right align-top font-medium">
                  <Bound binding={B.cmpModel} row={row} />
                </TableCell>
                <Against error={B.cmpStage} outcome={B.cmpStageOutcome} row={row} />
                <Against error={B.cmpRunRate} outcome={B.cmpRunRateOutcome} row={row} />
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </>
  );
}

export function Verdicts() {
  const ctx = useBindingContext();
  const better = String(readBinding(ctx, B.betterVerdict));
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Verdict question="Is the software correct?" verdict={B.softwareVerdict} reason={B.softwareSummary} />
      <Verdict
        question="Is the fitted forecast better than the baselines?"
        verdict={B.betterVerdict}
        reason={B.betterReason}
        tone={better === "no" ? "amber" : undefined}
      >
        <Comparison />
      </Verdict>
    </div>
  );
}
