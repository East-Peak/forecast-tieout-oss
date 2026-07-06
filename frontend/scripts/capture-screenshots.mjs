#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { cp, mkdir } from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendRoot, "..");
const docsScreenshotDir = path.resolve(repoRoot, "docs/screenshots");
const publicScreenshotDir = path.resolve(frontendRoot, "public/docs/screenshots");
const fixedBrowserTime = new Date("2026-07-04T19:00:00-07:00");

const captures = [
  {
    file: "hero-bookings-sapling.png",
    route: "/bookings",
    profile: "sapling-industries",
    fullPage: true,
  },
  {
    file: "capacity-sapling.png",
    route: "/capacity",
    profile: "sapling-industries",
    fullPage: true,
  },
  {
    file: "funnel-mighty-oak.png",
    route: "/funnel",
    profile: "mighty-oak-holdings",
    fullPage: true,
  },
  {
    file: "targets-sprout.png",
    route: "/targets",
    profile: "sprout-labs",
    fullPage: true,
  },
  {
    file: "scenario-sapling.png",
    route: "/scenario",
    profile: "sapling-industries",
    fullPage: true,
  },
  {
    file: "picker-personas.png",
    route: "/bookings",
    profile: "sapling-industries",
    selector: ".sticky.top-0",
  },
];

const disableAnimationsCss = `
  *, *::before, *::after {
    animation-delay: 0s !important;
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    caret-color: transparent !important;
    scroll-behavior: auto !important;
    transition-delay: 0s !important;
    transition-duration: 0s !important;
  }
`;

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

async function main() {
  await mkdir(docsScreenshotDir, { recursive: true });
  await mkdir(publicScreenshotDir, { recursive: true });

  const preview = await resolvePreview();
  try {
    await captureAll(preview.baseUrl);
  } finally {
    preview.close();
  }
}

async function resolvePreview() {
  const explicitBaseUrl = process.env.SCREENSHOT_BASE_URL?.replace(/\/$/, "");
  if (explicitBaseUrl) {
    await waitForHealthy(explicitBaseUrl);
    return { baseUrl: explicitBaseUrl, close: () => {} };
  }

  run("npm", ["run", "build"]);

  const reusable = await findHealthyPreview();
  if (reusable) {
    return { baseUrl: reusable, close: () => {} };
  }

  const port = await findAvailablePort();
  const child = spawn(
    "npx",
    ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    {
      cwd: frontendRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  child.stdout.on("data", (chunk) => process.stdout.write(chunk));
  child.stderr.on("data", (chunk) => process.stderr.write(chunk));

  const baseUrl = `http://127.0.0.1:${port}`;
  await waitForHealthy(baseUrl, child);
  return {
    baseUrl,
    close: () => {
      if (!child.killed) child.kill("SIGTERM");
    },
  };
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: frontendRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit ${result.status}`);
  }
}

async function findHealthyPreview() {
  for (let port = 4173; port <= 4180; port += 1) {
    const baseUrl = `http://127.0.0.1:${port}`;
    if (await isHealthy(baseUrl)) return baseUrl;
  }
  return null;
}

async function findAvailablePort() {
  for (let port = 4173; port <= 4180; port += 1) {
    if (await isPortAvailable(port)) return port;
  }
  throw new Error("No available preview port found in 4173-4180.");
}

function isPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function waitForHealthy(baseUrl, child) {
  const deadline = Date.now() + 120_000;
  let exited = false;
  let exitCode = null;

  child?.once("exit", (code) => {
    exited = true;
    exitCode = code;
  });

  while (Date.now() < deadline) {
    if (await isHealthy(baseUrl)) return;
    if (exited) throw new Error(`vite preview exited before it was ready: ${exitCode}`);
    await delay(500);
  }

  throw new Error(`Timed out waiting for ${baseUrl}`);
}

async function isHealthy(baseUrl) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1_500);
  try {
    const response = await fetch(`${baseUrl}/bookings?profile=sapling-industries`, {
      signal: controller.signal,
    });
    if (!response.ok) return false;
    const body = await response.text();
    return body.includes("Forecast Tieout");
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function captureAll(baseUrl) {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({
      colorScheme: "light",
      deviceScaleFactor: 1,
      locale: "en-US",
      reducedMotion: "reduce",
      timezoneId: "America/Los_Angeles",
      viewport: { width: 1440, height: 900 },
    });

    for (const capture of captures) {
      const page = await context.newPage();
      await page.clock.setFixedTime(fixedBrowserTime);
      await page.goto(`${baseUrl}${capture.route}?profile=${capture.profile}`, {
        waitUntil: "networkidle",
      });
      await page.addStyleTag({ content: disableAnimationsCss });
      await page.evaluate(() => document.fonts?.ready);
      await page.locator("main").waitFor({ state: "visible" });
      await page.locator("#org-profile-selector").waitFor({ state: "visible" });

      const docsPath = path.join(docsScreenshotDir, capture.file);
      const publicPath = path.join(publicScreenshotDir, capture.file);

      if (capture.selector) {
        await page.locator(capture.selector).first().screenshot({
          animations: "disabled",
          path: docsPath,
        });
      } else {
        await page.screenshot({
          animations: "disabled",
          fullPage: capture.fullPage,
          path: docsPath,
        });
      }

      await cp(docsPath, publicPath);
      await page.close();
      console.log(`captured ${path.relative(repoRoot, docsPath)}`);
    }
  } finally {
    await browser.close();
  }
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
