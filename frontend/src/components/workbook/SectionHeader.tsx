import { Text, Title } from "../ui";

interface Props {
  title: string;
  subtitle?: string;
  caption?: string;
}

export function SectionHeader({ title, subtitle, caption }: Props) {
  return (
    <div className="mb-4">
      <Title as="h2" className="font-display text-base font-semibold text-ft-brand">
        {title}
      </Title>
      {subtitle && <Text className="mt-1 text-xs text-slate-500">{subtitle}</Text>}
      {caption && (
        <Text className="mt-1 text-xs text-slate-500">{caption}</Text>
      )}
    </div>
  );
}
