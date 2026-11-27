import { createContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { YourPlanStore } from "./store";
import { DESKTOP_QUERY } from "./yourPlan";

interface Value {
  store: YourPlanStore;
  /** whether this screen is wide enough to edit a plan on (the choice is offered only then) */
  desktop: boolean;
}

const YourPlanContext = createContext<Value | null>(null);

export function YourPlanProvider({ store, desktop, children }: Value & { children: ReactNode }) {
  return <YourPlanContext.Provider value={{ store, desktop }}>{children}</YourPlanContext.Provider>;
}

/** True while the window is as wide as the editor needs; follows the window as it is resized. */
export function useDesktop(): boolean {
  const query = typeof window.matchMedia === "function" ? window.matchMedia(DESKTOP_QUERY) : null;
  const [wide, setWide] = useState(query?.matches ?? false);
  useEffect(() => {
    if (!query) return;
    const listen = () => setWide(query.matches);
    query.addEventListener("change", listen);
    return () => query.removeEventListener("change", listen);
  }, [query]);
  return wide;
}
