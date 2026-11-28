import type { Status } from "./types";

/** What a cell's status looks like. The file's status decides alone: behind is red, on track is green, none has no color. Classes are written out whole so the build sees them. */
export type Tone = "red" | "green" | "none";

export const toneOf = (status: Status): Tone => (status === "behind" ? "red" : status === "on_track" ? "green" : "none");

export const TEXT: Record<Tone, string> = { red: "text-red-600", green: "text-green-700", none: "text-slate-500" };

/** A bar: the solid layer and the lighter layer, for the browser's own progress element. */
export const SOLID: Record<Tone, string> = {
  red: "[&::-webkit-progress-value]:bg-red-600 [&::-moz-progress-bar]:bg-red-600",
  green: "[&::-webkit-progress-value]:bg-green-700 [&::-moz-progress-bar]:bg-green-700",
  none: "[&::-webkit-progress-value]:bg-slate-500 [&::-moz-progress-bar]:bg-slate-500",
};
export const LIGHT: Record<Tone, string> = {
  red: "[&::-webkit-progress-value]:bg-red-300 [&::-moz-progress-bar]:bg-red-300",
  green: "[&::-webkit-progress-value]:bg-green-300 [&::-moz-progress-bar]:bg-green-300",
  none: "[&::-webkit-progress-value]:bg-slate-300 [&::-moz-progress-bar]:bg-slate-300",
};

/** A mark on a strip: the actual solid, the forecast a ring. */
export const MARK_FILL: Record<Tone, string> = { red: "bg-red-600", green: "bg-green-700", none: "bg-slate-500" };
export const MARK_RING: Record<Tone, string> = { red: "border-red-600", green: "border-green-700", none: "border-slate-500" };
