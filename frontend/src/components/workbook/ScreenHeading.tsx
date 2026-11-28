import type { ReactNode } from "react";
import { Text, Title } from "../ui";

interface Props {
  title: string;
  subtitle: string;
  /** What the screen's figures are of (the year, the as-of date, the measure): the screen's caption, directly under its title. */
  caption: ReactNode;
}

/** A screen's title, its question and its caption as one block; the column's gap sets the space below it. */
export function ScreenHeading({ title, subtitle, caption }: Props) {
  return (
    <div>
      <Title as="h2" className="font-display text-base font-semibold text-ft-brand">
        {title}
      </Title>
      <Text className="mt-1 text-xs text-slate-500">{subtitle}</Text>
      <Text className="mt-0.5 text-xs text-slate-500" data-testid="screen-caption">
        {caption}
      </Text>
    </div>
  );
}
