import type { ReactNode } from "react";
import { useAuthContext } from "../../context/AuthContext";

function FullscreenMessage({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-6">
      <div className="w-full max-w-lg rounded-3xl border border-border bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-text-secondary">{body}</p>
        {children ? <div className="mt-6">{children}</div> : null}
      </div>
    </div>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { status, user, error, signInWithGoogle, signOut } = useAuthContext();

  if (status === "loading") {
    return (
      <FullscreenMessage
        title="Loading Access"
        body="Resolving your Google session and forecast access."
      />
    );
  }

  if (status === "unauthenticated") {
    return (
      <FullscreenMessage
        title="Sign In Required"
        body="Forecast Tieout requires an approved Google Workspace account."
      >
        <button
          className="rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white"
          onClick={() => void signInWithGoogle()}
          type="button"
        >
          Sign in with Google
        </button>
      </FullscreenMessage>
    );
  }

  if (status === "unauthorized") {
    return (
      <FullscreenMessage
        title="Not Authorized"
        body={
          error ??
          "Your Google account is signed in, but it does not have active access to Forecast Tieout."
        }
      >
        <div className="flex gap-3">
          <button
            className="rounded-full border border-border px-5 py-3 text-sm font-medium text-text-primary"
            onClick={() => void signOut()}
            type="button"
          >
            Sign out
          </button>
          <div className="self-center text-xs text-text-muted">
            {user?.email ?? ""}
          </div>
        </div>
      </FullscreenMessage>
    );
  }

  if (status === "error") {
    return (
      <FullscreenMessage
        title="Access Check Failed"
        body={error ?? "Protected access could not be verified."}
      >
        <div className="flex gap-3">
          <button
            className="rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white"
            onClick={() => window.location.reload()}
            type="button"
          >
            Reload
          </button>
          <button
            className="rounded-full border border-border px-5 py-3 text-sm font-medium text-text-primary"
            onClick={() => void signOut()}
            type="button"
          >
            Sign out
          </button>
        </div>
      </FullscreenMessage>
    );
  }

  return <>{children}</>;
}
