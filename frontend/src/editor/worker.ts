/// <reference lib="webworker" />
// The plan editor's worker: Pyodide running the same Python core that wrote the committed reports. It is
// started by the client, never by the page loading. Everything it fetches is a file of this site.
import type { PyodideInterface } from "pyodide";
import type { FromWorker, ToWorker } from "./protocol";

type PyProxyLike = { toJs(): unknown; destroy(): void; open(company: string): string; apply(plan: string): PyProxyLike };

let py: PyodideInterface | null = null;
let session: PyProxyLike | null = null;
const unpacked = new Set<string>();

const say = (m: FromWorker) => postMessage(m);

async function fetchBytes(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.arrayBuffer();
}

async function start(id: string, assets: string): Promise<PyodideInterface> {
  if (py) return py;
  say({ type: "progress", id, text: "Loading Python" });
  const { loadPyodide } = (await import(/* @vite-ignore */ `${assets}pyodide/pyodide.mjs`)) as typeof import("pyodide");
  const pyodide = await loadPyodide({ indexURL: `${assets}pyodide/` });
  say({ type: "progress", id, text: "Loading the numerical libraries" });
  await pyodide.loadPackage(["numpy", "pyyaml", "jsonschema"]);
  say({ type: "progress", id, text: "Loading the core" });
  pyodide.FS.mkdirTree("/work");
  pyodide.unpackArchive(await fetchBytes(`${assets}data/core.zip`), "zip", { extractDir: "/work" });
  pyodide.runPython(
    "import os, sys\nos.chdir('/work')\nsys.path.insert(0, '/work')\nfrom engine.tieout_core.editor import EditorSession\nSESSION = EditorSession()",
  );
  session = pyodide.globals.get("SESSION") as PyProxyLike;
  py = pyodide;
  return pyodide;
}

async function open(id: string, company: string, assets: string) {
  const pyodide = await start(id, assets);
  if (!unpacked.has(company)) {
    say({ type: "progress", id, text: "Loading this company's files" });
    pyodide.unpackArchive(await fetchBytes(`${assets}data/company-${company}.zip`), "zip", { extractDir: "/work" });
    unpacked.add(company);
  }
  say({ type: "progress", id, text: "Preparing the company: fitting the model and running the back-test" });
  say({ type: "opened", id, facts: session!.open(company) });
}

function apply(id: string, plan: string) {
  if (!session) throw new Error("no company is open");
  const answer = session.apply(plan);
  const [report, meta] = answer.toJs() as [string, string];
  answer.destroy();
  say({ type: "applied", id, report, meta });
}

// One request at a time, in the order sent: a slow download for one company must not finish after, and
// replace, the company a later request opened.
let queue: Promise<void> = Promise.resolve();

onmessage = (event: MessageEvent<ToWorker>) => {
  const m = event.data;
  const run = (queue = queue.then(() => (m.type === "open" ? open(m.id, m.company, m.assets) : apply(m.id, m.plan))));
  run.catch((e: unknown) => say({ type: "failed", id: m.id, error: e instanceof Error ? e.message : String(e) }));
};
