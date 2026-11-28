import { Bound } from "../binding/Bound";
import type { Binding } from "../binding/Bound";

/** A figure the committed list holds only where the file can have it: drawn through Bound where the list has it, and not at all otherwise (so a figure outside the list is never shown unbound). */
export function Maybe({ binding, row, className }: { binding: Binding | undefined; row?: string; className?: string }) {
  return binding ? <Bound binding={binding} row={row} className={className} /> : null;
}
