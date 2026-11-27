import "@testing-library/jest-dom";

// ResizeObserver is not available in jsdom. Polyfill it so recharts
// ResponsiveContainer (which calls new ResizeObserver) doesn't throw.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Node 25+ ships an experimental global `localStorage` that, without --localstorage-file,
// is undefined and shadows jsdom's. Stand jsdom's sessionStorage in for it so tests see a
// real Storage whichever Node runs them.
if (typeof localStorage === "undefined") {
  Object.defineProperty(globalThis, "localStorage", { value: window.sessionStorage, configurable: true });
}
