import type { Snapshot } from "../../types/snapshot";

export function SnapshotFooter({ snapshot }: { snapshot: Snapshot }) {
  return (
    <p className="mt-8 border-t border-slate-100 pt-4 text-xs text-slate-400">
      Data as of {snapshot.as_of} · Snapshot generated{" "}
      {new Date(snapshot.generated_at).toLocaleString()} · Git{" "}
      {snapshot.git_sha?.slice(0, 7) ?? "--"}
    </p>
  );
}
