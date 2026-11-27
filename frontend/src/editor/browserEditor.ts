import { PlanEditorClient, TIMEOUTS, timeoutsFromSearch } from "./client";
import type { WorkerLike } from "./client";

/**
 * The page's one plan editor. Making it costs nothing: the worker, Pyodide and the core are fetched only
 * when a company is first opened in it, which only the "Your plan" choice does.
 */
export const browserEditor = new PlanEditorClient({
  createWorker: () => new Worker(new URL("./worker.ts", import.meta.url), { type: "module" }) as unknown as WorkerLike,
  assets: `${import.meta.env.BASE_URL}editor/${__EDITOR_DIR__}/`,
  timeouts: timeoutsFromSearch(window.location.search, TIMEOUTS),
});
