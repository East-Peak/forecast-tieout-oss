import { Bound, readBinding, useBindingContext } from "../../binding/Bound";
import type { Binding } from "../../binding/Bound";
import { Badge, Card } from "../../components/ui";
import { B } from "./bindings";

type Tone = "green" | "red" | "amber" | "slate";

/** The tone of a verdict is read from its words in the report; nothing is computed. */
function toneOf(verdict: string): Tone {
  if (verdict === "yes") return "green";
  if (verdict === "no") return "red";
  return "slate";
}

function Verdict({ question, verdict, reason, tone }: { question: string; verdict: Binding; reason: Binding; tone?: Tone }) {
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
    </Card>
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
      />
    </div>
  );
}
