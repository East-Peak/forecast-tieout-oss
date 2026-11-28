/**
 * The width policy. The screens' content is one column, centered, no wider than 1552px (1600 less the 24px gutters); below
 * that it fills the window. The header and the screens' nav take the same side padding, so at every width the column's edges
 * are the header's content edges and no empty band opens beside it. Prose is held to a readable measure where it is written
 * (the chart notes, the description), not by narrowing the page. Written out in full: Tailwind generates only what it finds as
 * literal text in the source.
 */
export const COLUMN = "mx-auto flex w-full max-w-[1552px] flex-col gap-6";

/** The header's and the nav's side padding: the page gutter, growing once the window is wider than the column. */
export const GUTTER = "px-4 sm:px-[max(1.5rem,calc((100%-1552px)/2))]";
