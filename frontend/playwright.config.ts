import { defineConfig, devices } from "@playwright/test";

// Dedicated port — NOT vite's default 4173. The webServer healthcheck is
// identity-blind (any 2xx passes) and other apps' previews commonly squat 4173
// (empirically: agent-observatory, which the smoke suite then dutifully tested).
const PORT = 4179;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const visualEnabled = process.env.VISUAL === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  outputDir: "test-results",
  ignoreSnapshots: !visualEnabled,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: "disabled",
      maxDiffPixelRatio: 0,
    },
  },
  use: {
    baseURL: BASE_URL,
    colorScheme: "light",
    locale: "en-US",
    reducedMotion: "reduce",
    timezoneId: "America/Los_Angeles",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  webServer: {
    command: `npm run preview -- --host 127.0.0.1 --port ${PORT}`,
    url: `${BASE_URL}/bookings`,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
    timeout: 120_000,
  },
});
