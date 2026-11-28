import type { ReactNode } from "react";
import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { Badge, Card, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui";
import { STACK } from "../../components/workbook/stack";
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

/**
 * One verdict: the question, the report's word, and its reason. With nothing beneath it, a verdict is a compact strip (the
 * question, the word and the reason on one line, wrapping on a phone); with evidence beneath it, the question, word and
 * reason stand beside that evidence from lg up and above it below.
 */
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
  const badge = (
    <Badge color={tone ?? toneOf(word)} className="text-sm">
      <Bound binding={verdict} />
    </Badge>
  );
  if (!children) {
    return (
      <Card className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3" data-testid="verdict-card">
        <p className="text-xs font-medium text-slate-500">{question}</p>
        {badge}
        <p className="min-w-0 text-xs leading-5 text-slate-600">
          <Bound binding={reason} />
        </p>
      </Card>
    );
  }
  return (
    <Card className="grid gap-x-8 gap-y-3 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]" data-testid="verdict-card">
      <div>
        <p className="text-xs font-medium text-slate-500">{question}</p>
        <div className="mt-2 flex items-center gap-2">{badge}</div>
        <p className="mt-2 text-xs leading-5 text-slate-600">
          <Bound binding={reason} />
        </p>
      </div>
      <div className="min-w-0">{children}</div>
    </Card>
  );
}

/** A baseline's error with, beneath it, the report's word for which of the two is lower. */
function Against({ label, error, outcome, row }: { label: string; error: Binding; outcome: Binding; row: string }) {
  const ctx = useBindingContext();
  return (
    <TableCell className={`${STACK.cell} sm:text-right sm:align-top`} data-label={label}>
      <span className="flex flex-col items-end gap-1">
        <Bound binding={error} row={row} />
        <Badge color={outcomeTone(String(readBinding(ctx, outcome, row)))} size="xs">
          <Bound binding={outcome} row={row} />
        </Badge>
      </span>
    </TableCell>
  );
}

const STAGE = "Stage-weighted pipeline";
const RUN_RATE = "Last twelve months' pace";

/**
 * The back-test errors the verdict rests on, for each horizon the rule uses; absent when there is no verdict.
 * Laid out like the app's other tables: columns from the small breakpoint up, and on a phone each horizon a
 * block of labeled lines, so no font's width can push it past the card.
 */
function Comparison() {
  const { files } = useBindingContext();
  const rows = files.report.verdicts.forecast_better_than_baselines.comparisons;
  if (rows.length === 0) return null;
  return (
    <>
      <p className="text-[11px] text-slate-500">Average miss in dollars on the past, lower is better.</p>
      <Table className={`${STACK.table} mt-1 text-xs`}>
        <TableHead className={STACK.head}>
          <TableRow>
            <TableHeaderCell className="px-1 py-1 text-left">Months ahead</TableHeaderCell>
            <TableHeaderCell className="px-1 py-1 text-right">Fitted model</TableHeaderCell>
            <TableHeaderCell className="px-1 py-1 text-right">{STAGE}</TableHeaderCell>
            <TableHeaderCell className="px-1 py-1 text-right">{RUN_RATE}</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody className={STACK.body}>
          {rows.map((_, i) => {
            const row = `${ROWS.betterComparisons}/${i}`;
            return (
              <TableRow key={i} className={STACK.row} data-testid="verdict-comparison-row">
                <TableCell className={`${STACK.cell} sm:text-left sm:align-top`} data-label="Months ahead">
                  <Bound binding={B.cmpMonths} row={row} />
                </TableCell>
                <TableCell className={`${STACK.cell} font-medium sm:align-top`} data-label="Fitted model">
                  <Bound binding={B.cmpModel} row={row} />
                </TableCell>
                <Against label={STAGE} error={B.cmpStage} outcome={B.cmpStageOutcome} row={row} />
                <Against label={RUN_RATE} error={B.cmpRunRate} outcome={B.cmpRunRateOutcome} row={row} />
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
  const compared = ctx.files.report.verdicts.forecast_better_than_baselines.comparisons.length > 0;
  return (
    <div className="flex flex-col gap-4">
      <Verdict question="Is the software correct?" verdict={B.softwareVerdict} reason={B.softwareSummary} />
      <Verdict
        question="Is the fitted forecast better than the baselines?"
        verdict={B.betterVerdict}
        reason={B.betterReason}
        tone={better === "no" ? "amber" : undefined}
      >
        {compared ? <Comparison /> : null}
      </Verdict>
    </div>
  );
}
