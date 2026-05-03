import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getProtectedArtifactBucket,
  getProtectedArtifactPrefix,
  getProtectedDataMode,
  getSupabaseAnonKey,
  getSupabaseUrl,
  isProtectedAuthConfigured,
  isProtectedDataModeEnabled,
} from "../runtimeConfig";

describe("runtimeConfig", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to public/static mode", () => {
    expect(getProtectedDataMode()).toBeNull();
    expect(isProtectedDataModeEnabled()).toBe(false);
    expect(isProtectedAuthConfigured()).toBe(false);
    expect(getProtectedArtifactBucket()).toBe("forecast-data");
    expect(getProtectedArtifactPrefix()).toBe("");
  });

  it("enables protected mode only for the explicit private mode token", () => {
    vi.stubEnv("VITE_PROTECTED_DATA_MODE", "supabase-private");
    vi.stubEnv("VITE_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("VITE_SUPABASE_ANON_KEY", "anon-key");
    vi.stubEnv("VITE_SUPABASE_ARTIFACT_BUCKET", "private-forecast");
    vi.stubEnv("VITE_SUPABASE_ARTIFACT_PREFIX", "prod/data");

    expect(getProtectedDataMode()).toBe("supabase-private");
    expect(isProtectedDataModeEnabled()).toBe(true);
    expect(isProtectedAuthConfigured()).toBe(true);
    expect(getSupabaseUrl()).toBe("https://example.supabase.co");
    expect(getSupabaseAnonKey()).toBe("anon-key");
    expect(getProtectedArtifactBucket()).toBe("private-forecast");
    expect(getProtectedArtifactPrefix()).toBe("prod/data");
  });
});
