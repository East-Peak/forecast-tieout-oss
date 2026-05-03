import type { Snapshot } from '../types/snapshot';

const SUPPORTED_SCHEMA_MAJOR = 1;

export type LoadResult =
  | { status: 'ok'; snapshot: Snapshot }
  | { status: 'stale'; snapshot: Snapshot; staleDays: number }
  | { status: 'schema_mismatch'; expected: number; actual: string }
  | { status: 'missing'; message: string }
  | { status: 'error'; message: string };

function resolveSnapshotUrl(): string {
  const explicit = import.meta.env.VITE_SNAPSHOT_URL;
  if (explicit) return explicit;
  const profileId = import.meta.env.VITE_PROFILE_ID || 'acme-saas';
  return `/data/profiles/${profileId}/snapshot.json`;
}

function checkStaleness(generatedAt: string): { isStale: boolean; isVeryStale: boolean; staleDays: number } {
  const generated = new Date(generatedAt);
  const now = new Date();
  const diffMs = now.getTime() - generated.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  return {
    isStale: diffDays > 1 && diffDays <= 3,
    isVeryStale: diffDays > 3,
    staleDays: Math.floor(diffDays),
  };
}

export async function loadSnapshot(): Promise<LoadResult> {
  const url = resolveSnapshotUrl();
  try {
    const headers: Record<string, string> = {};

    // If Supabase URL is configured, we need auth token
    // The auth gating happens in AuthContext before this is called
    // If we reach here with a Supabase URL, the session should already exist
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    if (supabaseUrl && url.includes('supabase')) {
      const token = sessionStorage.getItem('supabase-auth-token');
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    const resp = await fetch(url, { headers });
    if (!resp.ok) {
      if (resp.status === 404) {
        return {
          status: 'missing',
          message: `No snapshot found at ${url}. Run: python engine/scripts/generate_snapshot.py --profile <your-profile>`,
        };
      }
      if (resp.status === 401 || resp.status === 403) {
        return { status: 'error', message: 'Authentication required. Please sign in.' };
      }
      return { status: 'error', message: `Failed to load snapshot: HTTP ${resp.status}` };
    }
    const snapshot: Snapshot = await resp.json();

    // Schema version check
    const version = snapshot.schema_version || '0.0.0';
    const major = parseInt(version.split('.')[0], 10);
    if (major !== SUPPORTED_SCHEMA_MAJOR) {
      return { status: 'schema_mismatch', expected: SUPPORTED_SCHEMA_MAJOR, actual: version };
    }

    // Staleness check
    const { isStale, isVeryStale, staleDays } = checkStaleness(snapshot.generated_at);
    if (isStale || isVeryStale) {
      return { status: 'stale', snapshot, staleDays };
    }

    return { status: 'ok', snapshot };
  } catch (err) {
    return { status: 'error', message: `Failed to load snapshot: ${err}` };
  }
}
