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
 * scroll inside its card). Written out in full, not derived from STACK: Tailwind only generates the classes
 * it finds as literal text in the source, and a derived string left every such table stacked at every width.
 */
export const STACK_LG = {
  table: "block lg:table",
  head: "hidden lg:table-header-group",
  body: "block lg:table-row-group",
  row: "block border-b border-slate-100 py-2 last:border-0 lg:table-row lg:border-b-0 lg:py-0",
  cell:
    "flex min-w-0 items-baseline justify-between gap-4 [overflow-wrap:anywhere] px-0 py-1 text-right before:text-left before:text-[11px] before:font-semibold before:uppercase before:text-ft-brand before:content-[attr(data-label)] lg:table-cell lg:px-3 lg:py-3 lg:before:hidden",
  /** a cell that carries no label of its own (the row's title) */
  title: "block px-0 py-1 font-medium lg:table-cell lg:px-3 lg:py-3",
} as const;

/**
 * The same stacking as STACK, but each stacked row is a two-column grid of small labeled values (the row's title across
 * both), so a table of many columns takes a third of the height on a phone. From the small breakpoint it is the table.
 */
export const STACK_GRID = {
  table: "block sm:table",
  head: "hidden sm:table-header-group",
  body: "block sm:table-row-group",
  row: "grid grid-cols-2 gap-x-4 gap-y-1 border-b border-slate-100 py-2 last:border-0 sm:table-row sm:py-0",
  cell:
    "flex min-w-0 flex-col [overflow-wrap:anywhere] !px-0 !py-0 text-left before:text-[10px] before:font-semibold before:uppercase before:text-ft-brand before:content-[attr(data-label)] sm:table-cell sm:!px-3 sm:!py-3 sm:text-right sm:before:hidden",
  /** a cell that carries no label of its own (the row's title) */
  title: "col-span-2 block !px-0 !py-0 font-medium sm:table-cell sm:!px-3 sm:!py-3",
} as const;
