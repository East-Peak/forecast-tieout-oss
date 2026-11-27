/**
 * Class names that let one table read as a table from the small breakpoint up and as stacked rows
 * (each cell its own labeled line, from the cell's data-label) on a phone, so nothing scrolls sideways.
 * One DOM, two layouts: the bound figures are in the page once.
 */
export const STACK = {
  table: "block sm:table",
  head: "hidden sm:table-header-group",
  body: "block sm:table-row-group",
  row: "block border-b border-slate-100 py-2 last:border-0 sm:table-row sm:border-b-0 sm:py-0",
  cell:
    "flex min-w-0 items-baseline justify-between gap-4 [overflow-wrap:anywhere] px-0 py-1 text-right before:text-left before:text-[11px] before:font-semibold before:uppercase before:text-ft-brand before:content-[attr(data-label)] sm:table-cell sm:px-3 sm:py-3 sm:before:hidden",
  /** a cell that carries no label of its own (the row's title) */
  title: "block px-0 py-1 font-medium sm:table-cell sm:px-3 sm:py-3",
} as const;

/**
 * The same stacking, but the columns appear only from the large breakpoint: for tables with so many columns
 * that they cannot fit a tablet's width in any font (a wider font or looser spacing must never make one
 * scroll inside its card). Derived from STACK so the two cannot drift apart.
 */
export const STACK_LG = Object.fromEntries(
  Object.entries(STACK).map(([name, classes]) => [name, classes.replace(/sm:/g, "lg:")]),
) as unknown as typeof STACK;
