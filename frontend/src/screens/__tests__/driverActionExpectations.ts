/**
 * Test-only. What the Actions block must show for a report, written by hand as typed accessors on the generated
 * report types; texts come from independent.ts. The ids the form shows beside an action (the worksheet's figures and the
 * core's evidence for an applied action) are read where the form is drawn, and are held by the form's own tests; they are
 * named here so the committed list and these expectations stay in step.
 */
import type { TieoutReport } from "../../generated/report";
import { BLOCK, DRIVER_ACTION_BINDINGS } from "../plan/driverActionBindings";
import * as fmt from "./independent";
import type { kit } from "./expectKit";

type Section = Extract<TieoutReport["driver_actions"], { joint_gain: unknown }>;
type Put = Pick<ReturnType<typeof kit>, "many" | "when">;

const REST = "rest of fiscal year";
const TWELVE = "next twelve months";

export function driverActionExpectations(r: TieoutReport, { many, when }: Put): string[] {
  const section: Section | null = "joint_gain" in r.driver_actions ? r.driver_actions : null;
  const items = section?.items ?? [];
  const rows = items.map((_, i) => `/driver_actions/items/${i}`);

  when(section !== null, BLOCK.definition.id, () => section!.definition);
  when(section !== null, BLOCK.removalLabel.id, () => section!.removal_label, 2);
  many(BLOCK.name.id, items.map((a) => a.name), rows);
  many(BLOCK.affects.id, items.map((a) => a.affects), rows);
  many(BLOCK.removedRest.id, items.map((a) => fmt.usdShort(a.removal_value[REST])), rows);
  many(BLOCK.removedNext.id, items.map((a) => fmt.usdShort(a.removal_value[TWELVE])), rows);

  when(section !== null, BLOCK.jointRest.id, () => fmt.usdShort(section!.joint_gain[REST]));
  when(section !== null, BLOCK.jointNext.id, () => fmt.usdShort(section!.joint_gain[TWELVE]));
  // the reconciliation line is said only for a window where it is not zero, with the core's sentence for it
  const off = (window: string) => section !== null && Number(section.reconciliation.values[window as typeof REST]) !== 0;
  when(off(REST), BLOCK.reconRest.id, () => fmt.usdShort(section!.reconciliation.values[REST]));
  when(off(REST), BLOCK.reconSentenceRest.id, () => section!.reconciliation.sentences[REST]);
  when(off(TWELVE), BLOCK.reconNext.id, () => fmt.usdShort(section!.reconciliation.values[TWELVE]));
  when(off(TWELVE), BLOCK.reconSentenceNext.id, () => section!.reconciliation.sentences[TWELVE]);

  // the same plan without its actions, and with them: the year and the next twelve months
  when(section !== null, BLOCK.withYear.id, () => fmt.usdShort(section!.with_actions.expected_fiscal_year));
  when(section !== null, BLOCK.withNext.id, () => fmt.usdShort(section!.with_actions.bookings[TWELVE]));
  when(section !== null, BLOCK.withoutYear.id, () => fmt.usdShort(section!.without_actions.expected_fiscal_year));
  when(section !== null, BLOCK.withoutNext.id, () => fmt.usdShort(section!.without_actions.bookings[TWELVE]));
  when(section !== null, BLOCK.removalNote.id, () => section!.removal_note);
  when(section !== null, BLOCK.rangeNote.id, () => section!.range_note);
  when(section !== null, BLOCK.roundingNote.id, () => section!.rounding_note);

  // the form's own figures are read where the form is drawn (the form's tests); they are named here so the one list holds them all
  return DRIVER_ACTION_BINDINGS.map((b) => b.id);
}
