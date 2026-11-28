import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type { LanesLoaders } from "./types";

const LanesContext = createContext<LanesLoaders | null>(null);

/** Where the grid's files come from: the page's own fetches, or a test's files on disk. */
export function LanesProvider({ loaders, children }: { loaders: LanesLoaders; children: ReactNode }) {
  return <LanesContext.Provider value={loaders}>{children}</LanesContext.Provider>;
}

/** The grid's loaders, or null where none were given (the screens' own tests): the Plan screen then draws no grid. */
export function useLanesLoaders(): LanesLoaders | null {
  return useContext(LanesContext);
}
