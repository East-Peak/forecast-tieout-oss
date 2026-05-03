import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, SupabaseClient, User } from "@supabase/supabase-js";
import { getSupabaseClient } from "../lib/supabase";

type AuthStatus =
  | "loading"
  | "unauthenticated"
  | "authorized"
  | "unauthorized"
  | "error";

interface AllowedUserRecord {
  email: string;
  active: boolean;
  role?: string | null;
}

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  session: Session | null;
  allowlistEntry: AllowedUserRecord | null;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function normalizeEmail(value: string | null | undefined): string | null {
  const trimmed = value?.trim().toLowerCase();
  return trimmed && trimmed.length > 0 ? trimmed : null;
}

/**
 * Domain allowlist for workspace email validation.
 * Set VITE_ALLOWED_EMAIL_DOMAINS to a comma-separated list of domains.
 * If unset, all authenticated emails are accepted.
 */
function getAllowedDomains(): string[] | null {
  const raw = import.meta.env.VITE_ALLOWED_EMAIL_DOMAINS as string | undefined;
  if (!raw || raw.trim().length === 0) return null;
  return raw
    .split(",")
    .map((d) => d.trim().toLowerCase())
    .filter((d) => d.length > 0);
}

function isAllowedWorkspaceEmail(value: string | null | undefined): boolean {
  const email = normalizeEmail(value);
  if (!email) return false;
  const allowedDomains = getAllowedDomains();
  if (!allowedDomains) return true; // No domain restriction configured
  const domain = email.split("@")[1];
  return allowedDomains.includes(domain);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [allowlistEntry, setAllowlistEntry] = useState<AllowedUserRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let client: SupabaseClient;
    try {
      client = getSupabaseClient();
    } catch (clientError) {
      setStatus("error");
      setError(
        clientError instanceof Error ? clientError.message : "Supabase auth is not configured.",
      );
      return;
    }
    let cancelled = false;

    async function resolveAuthorization(nextSession: Session | null) {
      if (cancelled) return;

      setSession(nextSession);
      const nextUser = nextSession?.user ?? null;
      setUser(nextUser);
      setAllowlistEntry(null);

      if (!nextUser) {
        setStatus("unauthenticated");
        setError(null);
        return;
      }

      const email = normalizeEmail(nextUser.email);
      if (!email || !isAllowedWorkspaceEmail(email)) {
        setStatus("unauthorized");
        setError("Your email domain is not authorized to access Forecast Tieout.");
        return;
      }

      setStatus("loading");
      setError(null);

      const { data, error: allowlistError } = await client
        .from("allowed_users")
        .select("email, active, role")
        .eq("email", email)
        .maybeSingle();

      if (cancelled) return;
      if (allowlistError) {
        setStatus("error");
        setError(allowlistError.message);
        return;
      }

      const allowedRow = (data as AllowedUserRecord | null) ?? null;

      if (!allowedRow?.active) {
        setStatus("unauthorized");
        setAllowlistEntry(allowedRow);
        setError("Your account is signed in, but it is not on the active Forecast Tieout allowlist.");
        return;
      }

      setAllowlistEntry(allowedRow);
      setStatus("authorized");
      setError(null);
    }

    client.auth
      .getSession()
      .then(({ data, error: sessionError }) => {
        if (cancelled) return;
        if (sessionError) {
          setStatus("error");
          setError(sessionError.message);
          return;
        }
        void resolveAuthorization(data.session);
      })
      .catch((sessionError) => {
        if (cancelled) return;
        setStatus("error");
        setError(sessionError instanceof Error ? sessionError.message : "Failed to resolve session.");
      });

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((_event, nextSession) => {
      void resolveAuthorization(nextSession);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      session,
      allowlistEntry,
      error,
      async signInWithGoogle() {
        let client: SupabaseClient;
        try {
          client = getSupabaseClient();
        } catch (clientError) {
          setStatus("error");
          setError(
            clientError instanceof Error
              ? clientError.message
              : "Supabase auth is not configured.",
          );
          return;
        }
        const redirectTo = window.location.href;
        const { error: signInError } = await client.auth.signInWithOAuth({
          provider: "google",
          options: {
            redirectTo,
          },
        });
        if (signInError) {
          setStatus("error");
          setError(signInError.message);
        }
      },
      async signOut() {
        let client: SupabaseClient;
        try {
          client = getSupabaseClient();
        } catch {
          return;
        }
        const { error: signOutError } = await client.auth.signOut();
        if (signOutError) {
          setStatus("error");
          setError(signOutError.message);
        }
      },
    }),
    [allowlistEntry, error, session, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Inert default for the unprotected demo: AuthProvider only mounts when
// VITE_PROTECTED_DATA_MODE is set, but Layout still calls useAuthContext to
// render the optional sign-out widget. Returning a no-op value lets Layout's
// existing `user?.email && ...` check skip the auth UI cleanly.
const ANONYMOUS_AUTH: AuthContextValue = {
  status: "unauthenticated",
  user: null,
  session: null,
  allowlistEntry: null,
  error: null,
  signInWithGoogle: async () => {},
  signOut: async () => {},
};

export function useAuthContext(): AuthContextValue {
  return useContext(AuthContext) ?? ANONYMOUS_AUTH;
}
