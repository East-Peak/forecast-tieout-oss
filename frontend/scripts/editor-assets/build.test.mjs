import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { buildEditorAssets } from "./build.mjs";

const sha = (buf) => createHash("sha256").update(buf).digest("hex");
const write = (root, rel, text) => {
  const path = join(root, rel);
  mkdirSync(join(path, ".."), { recursive: true });
  writeFileSync(path, text);
};

const WHEELS = {
  "alpha-1.0-py3-none-any.whl": "alpha wheel bytes",
  "beta-2.0-py3-none-any.whl": "beta wheel bytes",
  "unused-9.0-py3-none-any.whl": "never asked for",
};

/** A repository, a pyodide package and a network, all small and made here. */
function world() {
  const root = mkdtempSync(join(tmpdir(), "editor-assets-"));
  const repo = join(root, "repo");
  const pyodide = join(root, "node_modules", "pyodide");
  for (const f of ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip"]) write(pyodide, f, `core file ${f}`);
  write(pyodide, "package.json", JSON.stringify({ version: "9.9.9" }));
  const lock = { packages: {} };
  for (const [file, text] of Object.entries(WHEELS)) {
    const name = file.split("-")[0];
    lock.packages[name] = { name, file_name: file, sha256: sha(Buffer.from(text)), depends: name === "alpha" ? ["beta"] : [] };
  }
  write(pyodide, "pyodide-lock.json", JSON.stringify(lock));
  write(repo, "engine/tieout_core/__init__.py", "");
  write(repo, "engine/tieout_core/report.py", "x = 1\n");
  write(repo, "engine/tieout_core/report.schema.json", "{}");
  write(repo, "engine/tieout_core/__pycache__/report.cpython-312.pyc", "junk");
  write(repo, "engine/data-v2/acme/deals.csv", "id\n1\n");
  write(repo, "engine/config/profiles/acme/plan.yaml", "hires: []\n");
  write(repo, "engine/config/profiles/other/plan.yaml", "hires: []\n");
  write(repo, "frontend/public/data/reports/acme/lanes-basis.json", "{}");
  write(repo, "frontend/public/data/reports/acme/as-signed.json", "{}");
  write(repo, "frontend/public/data/reports/index.json", JSON.stringify({ companies: [{ id: "acme" }] }));
  const fetched = [];
  const fetchBytes = async (url) => {
    fetched.push(url);
    const file = url.split("/").pop();
    if (!(file in WHEELS)) throw new Error(`404 ${url}`);
    return Buffer.from(WHEELS[file]);
  };
  const options = (extra = {}) => ({
    repoRoot: repo,
    frontendRoot: join(repo, "frontend"),
    pyodideDir: pyodide,
    outRoot: join(root, "out"),
    cacheDir: join(root, "cache"),
    packages: ["alpha"],
    fetchBytes,
    ...extra,
  });
  return { root, repo, pyodide, fetched, options };
}

describe("the editor's assets", () => {
  let w;
  beforeEach(() => {
    w = world();
  });

  it("puts Pyodide's files, the wheels the packages need, the core and one zip per company under a content-hashed folder", async () => {
    const built = await buildEditorAssets(w.options());
    const files = (dir) => readdirSync(join(built.dir, dir)).sort();
    expect(files("pyodide")).toEqual(
      ["alpha-1.0-py3-none-any.whl", "beta-2.0-py3-none-any.whl", "pyodide-lock.json", "pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide.mjs", "python_stdlib.zip"].sort(),
    );
    expect(files("data")).toEqual(["company-acme.zip", "core.zip"]);
    expect(built.dir).toBe(join(w.options().outRoot, built.hash));
    expect(JSON.parse(readFileSync(join(w.options().outRoot, "manifest.json"), "utf8"))).toEqual({ dir: built.hash });
    expect(w.fetched.every((u) => u.startsWith("https://cdn.jsdelivr.net/pyodide/v9.9.9/full/"))).toBe(true);
    expect(w.fetched.some((u) => u.includes("unused"))).toBe(false);
  });

  it("takes the core's Python and schema, the named company's files and its committed plan basis, and nothing else", async () => {
    const built = await buildEditorAssets(w.options());
    const names = (zip) => {
      const buf = readFileSync(join(built.dir, "data", zip));
      const eocd = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
      let at = buf.readUInt32LE(eocd + 16);
      const out = [];
      for (let i = 0; i < buf.readUInt16LE(eocd + 10); i++) {
        const n = buf.readUInt16LE(at + 28);
        out.push(buf.subarray(at + 46, at + 46 + n).toString());
        at += 46 + n + buf.readUInt16LE(at + 30) + buf.readUInt16LE(at + 32);
      }
      return out;
    };
    expect(names("core.zip")).toEqual(["engine/tieout_core/__init__.py", "engine/tieout_core/report.py", "engine/tieout_core/report.schema.json"]);
    // the committed plan basis rides with the company: the worker proves the goals it computes are that file's
    expect(names("company-acme.zip")).toEqual(["engine/config/profiles/acme/plan.yaml", "engine/data-v2/acme/deals.csv", "frontend/public/data/reports/acme/lanes-basis.json"]);
  });

  it("names the folder by what is in it: the same inputs, the same folder; one changed line, another", async () => {
    const a = await buildEditorAssets(w.options());
    const b = await buildEditorAssets(w.options());
    expect(b.hash).toBe(a.hash);
    write(w.repo, "engine/tieout_core/report.py", "x = 2\n");
    const c = await buildEditorAssets(w.options());
    expect(c.hash).not.toBe(a.hash);
    expect(existsSync(a.dir)).toBe(false); // an older folder is not left behind
  });

  it("refuses a wheel whose bytes are not the ones the lock names", async () => {
    const tampered = w.options({ fetchBytes: async () => Buffer.from("not the wheel") });
    await expect(buildEditorAssets(tampered)).rejects.toThrow(/alpha-1\.0-py3-none-any\.whl.*sha256/);
  });

  it("reuses a checked wheel from the cache instead of fetching it again, and distrusts a damaged one", async () => {
    await buildEditorAssets(w.options());
    const first = w.fetched.length;
    await buildEditorAssets(w.options());
    expect(w.fetched.length).toBe(first);
    write(join(w.root, "cache"), "alpha-1.0-py3-none-any.whl", "damaged");
    await buildEditorAssets(w.options());
    expect(w.fetched.length).toBe(first + 1);
  });
});
