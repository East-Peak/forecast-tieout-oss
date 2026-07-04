# Frontend Developer Notes

## Playwright Browser Gates

Smoke runs against the built Vite app through `vite preview`:

```bash
npm run test:e2e
```

The smoke suite covers all 9 routes across the 3 public personas. It fails on
browser console errors or warnings, visible degenerate render text, missing
headline metrics, missing chart containers, all-zero chart series, or chart
containers that do not draw SVG path/rect geometry.

Visual comparison is gated behind `VISUAL=1` so local macOS runs do not create
or compare against non-Linux snapshots:

```bash
npm run test:visual
```

Baselines must be generated on Linux after an approved UI. Use the GitHub
Actions `workflow_dispatch` input `generate_visual_baselines=true`; that job
runs `npm run test:visual:update` on `ubuntu-latest` and uploads the generated
`frontend/e2e/*-snapshots/` PNGs as an artifact. Download the artifact, place
the snapshot folders under `frontend/e2e/`, then commit them. Once those PNGs
exist in the repo, the normal browser CI job runs visual comparison on every
commit.
