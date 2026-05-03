import "@testing-library/jest-dom";

// ResizeObserver is not available in jsdom. Polyfill it so recharts
// ResponsiveContainer (which calls new ResizeObserver) doesn't throw.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
