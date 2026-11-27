# Frontend developer notes

The app reads only `public/data/reports/`, which `python -m engine.scripts.generate_app_reports`
writes (see the repository README). `npm run dev`, `build` and `preview` first check that
`index.json` is there (`scripts/sync-data.mjs`).

## Browser smoke

Runs against the built app through `vite preview`:

```bash
npm run test:e2e
```

It covers all five screens for the three companies and four scenarios, the old app's
addresses, hover tooltips, scenario switching on Plan and phone-width overflow. It fails on
console errors, visible `NaN` or `undefined`, digits outside a bound element and charts that
draw no geometry.

## Other commands

```bash
npm run verify        # knip dead-code check, then vitest
npm run screenshots   # rewrites docs/screenshots and public/docs/screenshots from the built app
```
