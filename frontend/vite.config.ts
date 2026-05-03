/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const protectedDataModeEnabled = process.env.VITE_PROTECTED_DATA_MODE === "supabase-private";

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
  publicDir: protectedDataModeEnabled ? false : "public",
  server: {
    port: 3000,
    proxy: {
      "/api/scenario": {
        target: "http://127.0.0.1:8010",
        changeOrigin: false,
      },
      "/api/healthz": {
        target: "http://127.0.0.1:8010",
        changeOrigin: false,
      },
    },
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
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    environmentMatchGlobs: [
      ["src/components/**", "jsdom"],
      ["src/pages/**", "jsdom"],
    ],
  },
});
