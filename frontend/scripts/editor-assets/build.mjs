// Assembles what the plan editor loads in the browser, into one content-hashed folder under public/editor/:
//   pyodide/   Pyodide's own files (from the pinned npm package) and the wheels the core needs (checked
//              against the sha256 in the package's lock before they are used)
//   data/      core.zip (the Python core and its schema) and company-<id>.zip (that company's inputs)
// The folder's name is a hash of its contents, so every file in it can be cached forever. Nothing here is
// committed; the site's build writes it, and only Node is needed (no Python, no zip tool).
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { zip } from "./zip.mjs";

const PYODIDE_FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];
const PACKAGES = ["numpy", "pyyaml", "jsonschema"];

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

/** Every file under `dir` (as repo-relative names with `/`) that `keep` accepts, in name order. */
function walk(dir, root, keep) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "__pycache__") out.push(...walk(path, root, keep));
    } else if (keep(entry.name)) {
      out.push({ name: relative(root, path).split("\\").join("/"), data: readFileSync(path) });
    }
  }
  return out;
}

/** The lock's packages named, and everything they depend on, as the files to ship. */
function wheelsFor(lock, names) {
  const seen = new Map();
  const visit = (name) => {
    const key = name.toLowerCase().replace(/_/g, "-");
    const pkg = lock.packages[key] ?? lock.packages[name];
    if (!pkg) throw new Error(`pyodide-lock.json has no package ${name}`);
    if (seen.has(pkg.name)) return;
    seen.set(pkg.name, pkg);
    pkg.depends.forEach(visit);
  };
  names.forEach(visit);
  return [...seen.values()];
}

async function defaultFetchBytes(url) {
  let last;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return Buffer.from(await response.arrayBuffer());
    } catch (e) {
      last = e;
    }
  }
  throw new Error(`could not fetch ${url}: ${last instanceof Error ? last.message : String(last)}`);
}

async function wheel(pkg, version, cacheDir, fetchBytes) {
  const cached = join(cacheDir, pkg.file_name);
  if (existsSync(cached)) {
    const data = readFileSync(cached);
    if (sha256(data) === pkg.sha256) return data;
  }
  const data = await fetchBytes(`https://cdn.jsdelivr.net/pyodide/v${version}/full/${pkg.file_name}`);
  if (sha256(data) !== pkg.sha256) throw new Error(`${pkg.file_name}: the bytes fetched do not match the sha256 in pyodide-lock.json`);
  mkdirSync(cacheDir, { recursive: true });
  writeFileSync(cached, data);
  return data;
}

export async function buildEditorAssets({
  repoRoot,
  frontendRoot,
  pyodideDir,
  outRoot,
  cacheDir,
  packages = PACKAGES,
  fetchBytes = defaultFetchBytes,
}) {
  const version = JSON.parse(readFileSync(join(pyodideDir, "package.json"), "utf8")).version;
  const lock = JSON.parse(readFileSync(join(pyodideDir, "pyodide-lock.json"), "utf8"));
  /** @type {{ path: string, data: Buffer }[]} */
  const files = PYODIDE_FILES.map((f) => ({ path: `pyodide/${f}`, data: readFileSync(join(pyodideDir, f)) }));
  for (const pkg of wheelsFor(lock, packages)) {
    files.push({ path: `pyodide/${pkg.file_name}`, data: await wheel(pkg, version, cacheDir, fetchBytes) });
  }

  const core = walk(join(repoRoot, "engine", "tieout_core"), repoRoot, (n) => n.endsWith(".py") || n === "report.schema.json");
  files.push({ path: "data/core.zip", data: zip(core) });
  const index = JSON.parse(readFileSync(join(frontendRoot, "public", "data", "reports", "index.json"), "utf8"));
  for (const { id } of index.companies) {
    const entries = [
      ...walk(join(repoRoot, "engine", "data-v2", id), repoRoot, () => true),
      ...walk(join(repoRoot, "engine", "config", "profiles", id), repoRoot, () => true),
      // the committed plan basis (the goals): the worker proves the basis it computes is this file before it shows lanes
      ...walk(join(frontendRoot, "public", "data", "reports", id), repoRoot, (n) => n === "lanes-basis.json"),
    ];
    files.push({ path: `data/company-${id}.zip`, data: zip(entries) });
  }

  const hash = createHash("sha256");
  for (const f of [...files].sort((a, b) => (a.path < b.path ? -1 : 1))) hash.update(f.path).update("\0").update(sha256(f.data)).update("\0");
  const name = hash.digest("hex").slice(0, 16);
  const dir = join(outRoot, name);
  rmSync(outRoot, { recursive: true, force: true });
  for (const f of files) {
    mkdirSync(join(dir, f.path, ".."), { recursive: true });
    writeFileSync(join(dir, f.path), f.data);
  }
  writeFileSync(join(outRoot, "manifest.json"), JSON.stringify({ dir: name }));
  return { hash: name, dir, files: files.map((f) => ({ path: f.path, bytes: f.data.length })) };
}
