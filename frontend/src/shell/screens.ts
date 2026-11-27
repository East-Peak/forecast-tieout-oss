/** The five screens, each answering one question a planner asks (Goal 3's spec). */
export interface ScreenEntry {
  path: string;
  label: string;
  question: string;
}

export const SCREENS: readonly ScreenEntry[] = [
  { path: "/forecast", label: "Forecast", question: "Where does the year land, and how sure are we?" },
  { path: "/capacity", label: "Capacity", question: "Can this team carry the number?" },
  { path: "/pipeline", label: "Pipeline", question: "What must be created, by when, and is it too late?" },
  { path: "/plan", label: "Plan", question: "What do the actions buy, and which is cheaper?" },
  { path: "/trust", label: "Trust", question: "Why should anyone believe any of this?" },
] as const;
