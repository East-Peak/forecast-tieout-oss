/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#ffffff',
          raised: '#f6f8fa',
          overlay: '#f0f2f5',
        },
        border: {
          DEFAULT: '#d0d7de',
        },
        text: {
          primary: '#1f2328',
          secondary: '#656d76',
          muted: '#8c959f',
        },
        accent: {
          blue: '#0969da',
          green: '#1a7f37',
          orange: '#d29922',
          red: '#cf222e',
          purple: '#8250df',
        },
      },
    },
  },
  safelist: [
    // Recharts series colors are generated dynamically and JIT misses them
    ...['blue', 'emerald', 'red', 'orange', 'gray', 'indigo', 'amber', 'cyan', 'violet', 'green', 'yellow', 'rose', 'slate', 'zinc', 'neutral', 'stone', 'sky', 'teal', 'lime', 'fuchsia', 'pink', 'purple'].flatMap((color) => [
      `bg-${color}-500`, `bg-${color}-400`, `bg-${color}-600`,
      `fill-${color}-500`, `fill-${color}-400`, `fill-${color}-600`,
      `stroke-${color}-500`, `stroke-${color}-400`, `stroke-${color}-600`,
      `text-${color}-500`, `text-${color}-400`, `text-${color}-600`,
      `bg-${color}-500/20`, `bg-${color}-500/30`, `bg-${color}-500/40`,
    ]),
  ],
  plugins: [],
}
