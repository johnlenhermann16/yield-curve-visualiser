# Architecture

## Projects
- Python backend: C:\Users\777\Documents\yield-curve-visualiser
  (this repo)
- React frontend: D:\yield-curve-react (separate repo/location, NOT
  inside this folder)
- Railway backend retired — https://efficient-nourishment-production.up.railway.app
  is dead. The frontend no longer calls it; it reads directly from
  Supabase (PostgREST REST API, tables yield_observations /
  spread_observations) via D:\yield-curve-react\src\api.js.
- GitHub: johnlenhermann16/yield-curve-visualiser (private, backend)
- GitHub: johnlenhermann16/yield-curve-react (frontend, pushed
  2026-07-31)
- Frontend is deployed to Vercel: https://yield-curve-react.vercel.app
  (env vars VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY set in the
  Vercel project). `npm run dev` at D:\yield-curve-react still works
  for local dev against the same Supabase project.

## Structure
- Backend: FastAPI (api/main.py), per-country fetch modules in data/
  (fetch_us.py, fetch_uk.py, fetch_germany.py, etc.), wired together via
  data/countries.py's COUNTRY_FETCHERS dict. The `Procfile` at repo root
  is not currently deployed anywhere — the backend's only live role is
  local dev of the fetch modules and running `seed_supabase.py` (repo
  root), which reuses that fetch logic to populate the Supabase tables
  the deployed frontend reads from.
- Frontend: React + Vite + Tailwind + Plotly, components in
  D:\yield-curve-react\src\components\
- Design system: Claude Design "Studio" aesthetic (redesigned 2026-07-31,
  replacing the old blueprint-card look) — #F6F6F8 background, white
  rounded 16px cards, dot-grid header panel with accent glow, pill chips,
  underline tabs, #5980a6 accent. Barlow / Barlow Condensed kept, IBM Plex
  Mono added for dates and range pills. Tokens live in :root in
  D:\yield-curve-react\src\index.css; every accent call site uses
  --color-accent / --color-accent-2 / --color-accent-soft /
  --color-accent-glow, so re-theming is a four-token swap.
  Source spec: Claude Design project cf12ad8c-1990-4e06-b0f3-91f23e3e9b09
  ("Yield Curve Redesign.dc.html" + handoff.md).
- The blueprint corner marks are gone. App.jsx's Corners() is now a no-op
  kept only so HistoricalContext/CurveExplainer keep their prop signature.
- Tailwind is installed and imported but zero utility classes are used —
  only its preflight is doing anything.

## Tech Stack
- Frontend libs: React, Vite, Tailwind, Plotly.js, axios
- Backend libs: fastapi, uvicorn, pandas, requests, fredapi, openpyxl
