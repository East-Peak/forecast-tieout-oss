// Writes the plan editor's static assets to public/editor/ (not committed; see scripts/editor-assets/build.mjs).
// Run by `npm run build`, `npm run dev` and `npm run preview`, so the site's one build command makes them.
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildEditorAssets } from "./editor-assets/build.mjs";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const started = performance.now();
const built = await buildEditorAssets({
  repoRoot: resolve(frontendRoot, ".."),
  frontendRoot,
  pyodideDir: resolve(frontendRoot, "node_modules", "pyodide"),
  outRoot: resolve(frontendRoot, "public", "editor"),
  cacheDir: resolve(frontendRoot, "node_modules", ".cache", "editor-wheels"),
});
const bytes = built.files.reduce((sum, f) => sum + f.bytes, 0);
console.log(
  `[editor:assets] ${built.files.length} files, ${(bytes / 1e6).toFixed(1)} MB, public/editor/${built.hash}/ (${((performance.now() - started) / 1000).toFixed(1)} s)`,
);
