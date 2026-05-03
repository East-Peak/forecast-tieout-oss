interface Props {
  status: "missing" | "schema_mismatch" | "error";
  message?: string;
  expected?: number;
  actual?: string;
}

export function SnapshotError({ status, message, expected, actual }: Props) {
  if (status === "missing") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <div className="max-w-md text-center">
          <p className="mb-2 text-sm font-medium text-text-primary">
            No snapshot found
          </p>
          <p className="mb-4 text-xs text-text-muted">
            {message ?? "The snapshot file does not exist."}
          </p>
          <p className="text-xs text-text-secondary">
            Run the engine to generate a snapshot:
          </p>
          <pre className="mt-2 rounded bg-surface-raised px-3 py-2 text-left text-xs text-text-primary">
            python engine/scripts/generate_snapshot.py --profile &lt;your-profile&gt;
          </pre>
        </div>
      </div>
    );
  }

  if (status === "schema_mismatch") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <div className="max-w-md text-center">
          <p className="mb-2 text-sm font-medium text-yellow-500">
            Snapshot version mismatch
          </p>
          <p className="mb-4 text-xs text-text-muted">
            The snapshot was generated with schema version{" "}
            <code className="rounded bg-surface-raised px-1 py-0.5 font-mono">
              {actual ?? "unknown"}
            </code>
            , but the frontend expects major version{" "}
            <code className="rounded bg-surface-raised px-1 py-0.5 font-mono">
              {expected ?? "unknown"}
            </code>
            .
          </p>
          <p className="text-xs text-text-secondary">
            Upgrade instructions: regenerate the snapshot with a compatible version of
            the engine, or update the frontend to match the snapshot schema.
          </p>
          <pre className="mt-2 rounded bg-surface-raised px-3 py-2 text-left text-xs text-text-primary">
            python engine/scripts/generate_snapshot.py --profile &lt;your-profile&gt;
          </pre>
        </div>
      </div>
    );
  }

  // Generic error
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <div className="text-center">
        <p className="mb-1 text-sm font-medium text-red-400">
          Failed to load snapshot
        </p>
        <p className="text-xs text-text-muted">{message ?? "Unknown error"}</p>
      </div>
    </div>
  );
}
