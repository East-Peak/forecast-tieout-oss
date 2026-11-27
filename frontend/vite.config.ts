/// <reference types="vitest" />
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** The folder `npm run editor:assets` wrote under public/editor/ (named by a hash of its contents), or "none". */
function editorAssetsDir(): string {
  const manifest = resolve(dirname(fileURLToPath(import.meta.url)), "public", "editor", "manifest.json");
  return existsSync(manifest) ? (JSON.parse(readFileSync(manifest, "utf8")) as { dir: string }).dir : "none";
}

function getPackageName(id: string): string | null {
  const marker = "node_modules/";
  const index = id.lastIndexOf(marker);
  if (index === -1) return null;

  const path = id.slice(index + marker.length);
  const parts = path.split("/");
  if (parts[0]?.startsWith("@")) {
    return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : parts[0] ?? null;
  }
  return parts[0] ?? null;
}

function manualChunks(id: string): string | undefined {
  const pkg = getPackageName(id);
  if (!pkg) return undefined;

  if (pkg === "react" || pkg === "react-dom" || pkg === "scheduler") {
    return "react-core";
  }

  if (pkg === "react-router" || pkg === "react-router-dom") {
    return "router";
  }

  if (
    pkg === "recharts" ||
    pkg === "recharts-scale" ||
    pkg === "victory-vendor" ||
    pkg === "react-smooth" ||
    pkg === "prop-types" ||
    pkg === "lodash" ||
    pkg.startsWith("d3-")
  ) {
    return "charts-vendor";
  }

  if (
    pkg.startsWith("@headlessui/") ||
    pkg.startsWith("@react-aria/") ||
    pkg.startsWith("@react-stately/") ||
    pkg.startsWith("@floating-ui/") ||
    pkg.startsWith("@tanstack/") ||
    pkg === "react-day-picker" ||
    pkg === "date-fns" ||
    pkg === "tailwind-merge" ||
    pkg === "clsx" ||
    pkg === "decimal.js-light" ||
    pkg === "eventemitter3" ||
    pkg === "fast-equals" ||
    pkg === "react-transition-state" ||
    pkg === "tiny-invariant"
  ) {
    return "ui-vendor";
  }

  return "vendor-misc";
}

export default defineConfig({
  plugins: [react()],
  define: { __EDITOR_DIR__: JSON.stringify(editorAssetsDir()) },
  server: {
    port: 3000,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  test: {
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    testTimeout: 30_000, // a ceiling for a test on a busy machine, not a delay
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost/" } },
  },
});
