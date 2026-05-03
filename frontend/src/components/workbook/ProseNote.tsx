import { Text } from "../ui";

export function ProseNote({ children }: { children: React.ReactNode }) {
  return <Text className="mb-4 text-sm text-slate-600">{children}</Text>;
}
