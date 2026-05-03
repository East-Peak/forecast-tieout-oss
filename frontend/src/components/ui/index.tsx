import type {
  ComponentPropsWithoutRef,
  ElementType,
  HTMLAttributes,
  OptionHTMLAttributes,
  SelectHTMLAttributes,
} from "react";

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

type PolymorphicProps<T extends ElementType> = {
  as?: T;
  className?: string;
} & Omit<ComponentPropsWithoutRef<T>, "as" | "className">;

function createTextPrimitive<TDefault extends ElementType>(
  defaultTag: TDefault,
  baseClassName: string,
) {
  return function Primitive<TTag extends ElementType = TDefault>({
    as,
    className,
    ...props
  }: PolymorphicProps<TTag>) {
    const Component = (as ?? defaultTag) as ElementType;
    return <Component className={cx(baseClassName, className)} {...props} />;
  };
}

export const Text = createTextPrimitive("p", "text-sm text-slate-600");
export const Title = createTextPrimitive(
  "h3",
  "text-base font-semibold tracking-tight text-slate-900",
);
export const Metric = createTextPrimitive(
  "div",
  "text-3xl font-semibold tracking-tight text-slate-900",
);

export interface CardProps extends HTMLAttributes<HTMLDivElement> {}

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cx(
        "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export type BadgeColor =
  | "slate"
  | "gray"
  | "blue"
  | "emerald"
  | "amber"
  | "red"
  | "rose"
  | "purple";

const BADGE_STYLES: Record<BadgeColor, string> = {
  slate: "border-slate-200 bg-slate-50 text-slate-700",
  gray: "border-slate-200 bg-slate-50 text-slate-700",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  red: "border-red-200 bg-red-50 text-red-700",
  rose: "border-rose-200 bg-rose-50 text-rose-700",
  purple: "border-purple-200 bg-purple-50 text-purple-700",
};

export interface BadgeProps
  extends Omit<HTMLAttributes<HTMLSpanElement>, "color"> {
  color?: BadgeColor;
  size?: "xs" | "sm";
}

export function Badge({
  color = "slate",
  size = "sm",
  className,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full border font-medium leading-none",
        size === "xs" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        BADGE_STYLES[color],
        className,
      )}
      {...props}
    />
  );
}

export type DeltaType =
  | "increase"
  | "moderateIncrease"
  | "decrease"
  | "moderateDecrease"
  | "unchanged";

const DELTA_STYLES: Record<DeltaType, { color: BadgeColor; marker: string }> = {
  increase: { color: "emerald", marker: "▲" },
  moderateIncrease: { color: "blue", marker: "▲" },
  decrease: { color: "red", marker: "▼" },
  moderateDecrease: { color: "amber", marker: "▼" },
  unchanged: { color: "slate", marker: "•" },
};

export interface BadgeDeltaProps
  extends Omit<HTMLAttributes<HTMLSpanElement>, "color"> {
  deltaType?: DeltaType;
}

export function BadgeDelta({
  deltaType = "unchanged",
  className,
  children,
  ...props
}: BadgeDeltaProps) {
  const tone = DELTA_STYLES[deltaType];
  return (
    <Badge color={tone.color} className={cx("gap-1.5", className)} {...props}>
      <span aria-hidden="true">{tone.marker}</span>
      <span>{children}</span>
    </Badge>
  );
}

export interface TableProps extends HTMLAttributes<HTMLTableElement> {}

export function Table({ className, ...props }: TableProps) {
  return (
    <div className="overflow-x-auto">
      <table className={cx("min-w-full border-collapse", className)} {...props} />
    </div>
  );
}

export interface TableHeadProps
  extends HTMLAttributes<HTMLTableSectionElement> {}

export function TableHead({ className, ...props }: TableHeadProps) {
  return <thead className={cx("border-b border-slate-200", className)} {...props} />;
}

export interface TableBodyProps
  extends HTMLAttributes<HTMLTableSectionElement> {}

export function TableBody({ className, ...props }: TableBodyProps) {
  return <tbody className={cx("divide-y divide-slate-100", className)} {...props} />;
}

export interface TableRowProps extends HTMLAttributes<HTMLTableRowElement> {}

export function TableRow({ className, ...props }: TableRowProps) {
  return <tr className={cx("align-top", className)} {...props} />;
}

export interface TableHeaderCellProps
  extends HTMLAttributes<HTMLTableCellElement> {}

export function TableHeaderCell({
  className,
  ...props
}: TableHeaderCellProps) {
  return (
    <th
      className={cx(
        "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500",
        className,
      )}
      {...props}
    />
  );
}

export interface TableCellProps extends HTMLAttributes<HTMLTableCellElement> {}

export function TableCell({ className, ...props }: TableCellProps) {
  return (
    <td
      className={cx("px-3 py-3 text-sm text-slate-700", className)}
      {...props}
    />
  );
}

export interface CalloutProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  color?: Extract<BadgeColor, "red" | "emerald" | "amber" | "blue" | "slate">;
}

const CALLOUT_STYLES: Record<NonNullable<CalloutProps["color"]>, string> = {
  red: "border-red-200 bg-red-50/80 text-red-900",
  emerald: "border-emerald-200 bg-emerald-50/80 text-emerald-900",
  amber: "border-amber-200 bg-amber-50/80 text-amber-900",
  blue: "border-blue-200 bg-blue-50/80 text-blue-900",
  slate: "border-slate-200 bg-slate-50/80 text-slate-900",
};

export function Callout({
  title,
  color = "slate",
  className,
  children,
  ...props
}: CalloutProps) {
  return (
    <div
      className={cx(
        "rounded-xl border px-4 py-3 shadow-sm",
        CALLOUT_STYLES[color],
        className,
      )}
      {...props}
    >
      {title ? <div className="text-sm font-semibold">{title}</div> : null}
      <div className={cx("text-sm leading-6", title ? "mt-1" : undefined)}>{children}</div>
    </div>
  );
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange"> {
  onValueChange?: (value: string) => void;
}

export function Select({
  className,
  onValueChange,
  children,
  ...props
}: SelectProps) {
  return (
    <div className={cx("relative inline-flex w-full", className)}>
      <select
        className="w-full appearance-none rounded-lg border border-slate-300 bg-white px-3 py-2 pr-9 text-sm text-slate-900 shadow-sm transition outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
        onChange={(event) => onValueChange?.(event.target.value)}
        {...props}
      >
        {children}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-slate-400"
      >
        ▾
      </span>
    </div>
  );
}

export interface SelectItemProps
  extends OptionHTMLAttributes<HTMLOptionElement> {}

export function SelectItem(props: SelectItemProps) {
  return <option {...props} />;
}
