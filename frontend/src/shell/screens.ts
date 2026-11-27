/** The five screens, each answering one question a planner asks (Goal 3's spec). */
export interface ScreenEntry {
  path: string;
  label: string;
  question: string;
  /** "evidence": a screen that shows what the plan rests on, listed under that label in the navigation */
  group?: "evidence";
}

export const SCREENS: readonly ScreenEntry[] = [
  { path: "/plan", label: "Plan", question: "What moves the outcome, and which plan do we choose?" },
  { path: "/forecast", label: "Forecast", question: "Where does the year land, and how sure are we?", group: "evidence" },
  { path: "/capacity", label: "Capacity", question: "Can this team carry the number?", group: "evidence" },
  { path: "/pipeline", label: "Pipeline", question: "What must be created, by when, and is it too late?", group: "evidence" },
  { path: "/trust", label: "Trust", question: "Why should anyone believe any of this?", group: "evidence" },
] as const;

/** The landing screen: the address `/` and any unknown address lead here. */
export const LANDING = SCREENS[0].path;
