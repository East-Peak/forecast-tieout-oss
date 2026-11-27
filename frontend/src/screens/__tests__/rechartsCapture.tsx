/**
 * Test-only. recharts is wrapped, not replaced: ResponsiveContainer is given a size (jsdom has none) and
 * ComposedChart records the data and the series elements it is handed before drawing them. What a test then
 * checks is what the chart component received, not a copy serialized beside it.
 */
import { Children, Fragment, cloneElement, createElement, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import type { CapturedChart } from "../../binding/__tests__/harness";

type Recharts = typeof import("recharts");

export function withCapture(actual: Recharts, captured: unknown[]): Recharts {
  const flatten = (node: ReactNode): ReactElement[] =>
    Children.toArray(node).flatMap((child) =>
      isValidElement(child)
        ? child.type === Fragment
          ? flatten((child.props as { children?: ReactNode }).children)
          : [child as ReactElement]
        : [],
    );
  const nameOf = (el: ReactElement) => (el.type as { displayName?: string }).displayName ?? "";
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) => cloneElement(children, { width: 900, height: 320 } as object),
    ComposedChart: (props: { data: unknown; children: ReactNode }) => {
      const parts = flatten(props.children);
      captured.push({
        data: props.data,
        xKey: (parts.find((p) => nameOf(p) === "XAxis")?.props as { dataKey?: string } | undefined)?.dataKey,
        series: parts
          .filter((p) => ["Bar", "Area", "Line"].includes(nameOf(p)))
          .map((p) => ({ type: nameOf(p), dataKey: (p.props as { dataKey: string }).dataKey, stackId: (p.props as { stackId?: unknown }).stackId })),
        referenceX: parts.filter((p) => nameOf(p) === "ReferenceLine").map((p) => String((p.props as { x: unknown }).x)),
      } satisfies CapturedChart);
      return createElement(actual.ComposedChart, props as never);
    },
  } as Recharts;
}
