import { useEffect, useState } from "react";

export type Loaded<T> = { status: "idle" } | { status: "loading" } | { status: "ready"; doc: T } | { status: "error"; error: string };

/**
 * One file, fetched when `key` names it and again when the key changes. What arrives is checked by `accept`, which
 * returns the reason it is the wrong file (or null); an answer for a key the visitor has already left is dropped.
 * A null `key` is nothing to load: the state is idle.
 */
export function useFile<T>(key: string | null, load: () => Promise<T>, accept: (doc: T) => string | null): Loaded<T> {
  const [state, setState] = useState<{ key: string | null; value: Loaded<T> }>({ key: null, value: { status: "idle" } });
  useEffect(() => {
    if (key === null) return undefined;
    let live = true;
    load().then(
      (doc) => {
        const wrong = accept(doc);
        if (live) setState({ key, value: wrong === null ? { status: "ready", doc } : { status: "error", error: wrong } });
      },
      (e: unknown) => {
        if (live) setState({ key, value: { status: "error", error: e instanceof Error ? e.message : String(e) } });
      },
    );
    return () => {
      live = false;
    };
    // the file is named by its key alone; `load` and `accept` are written fresh on every render
  }, [key]);
  if (key === null) return { status: "idle" };
  // the state of another key is stale: until this key's own answer arrives it is loading
  return state.key === key ? state.value : { status: "loading" };
}
