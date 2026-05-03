import { Text, Title } from "../ui";

interface Props {
  title: string;
  subtitle?: string;
  caption?: string;
}

export function SectionHeader({ title, subtitle, caption }: Props) {
  return (
    <div className="mb-4">
      <Title className="text-sm font-semibold text-slate-800" style={{ letterSpacing: "-0.01em" }}>
        {title}
      </Title>
      {subtitle && <Text className="mt-1 text-xs text-slate-500">{subtitle}</Text>}
      {caption && (
        <Text className="mt-1 text-xs text-slate-500">{caption}</Text>
      )}
    </div>
  );
}
