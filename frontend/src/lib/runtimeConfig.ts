const PROTECTED_DATA_MODE = "supabase-private";

function normalizeEnvValue(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : null;
}

export function getProtectedDataMode(): string | null {
  return normalizeEnvValue(import.meta.env.VITE_PROTECTED_DATA_MODE as string | undefined);
}

export function isProtectedDataModeEnabled(): boolean {
  return getProtectedDataMode() === PROTECTED_DATA_MODE;
}

export function getSupabaseUrl(): string | null {
  return normalizeEnvValue(import.meta.env.VITE_SUPABASE_URL as string | undefined);
}

export function getSupabaseAnonKey(): string | null {
  return normalizeEnvValue(import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined);
}

export function getProtectedArtifactBucket(): string {
  return (
    normalizeEnvValue(import.meta.env.VITE_SUPABASE_ARTIFACT_BUCKET as string | undefined) ??
    "forecast-data"
  );
}

export function getProtectedArtifactPrefix(): string {
  return normalizeEnvValue(
    import.meta.env.VITE_SUPABASE_ARTIFACT_PREFIX as string | undefined,
  ) ?? "";
}

export function isProtectedAuthConfigured(): boolean {
  return Boolean(getSupabaseUrl() && getSupabaseAnonKey());
}
