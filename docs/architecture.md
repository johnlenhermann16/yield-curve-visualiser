# Architecture

## Projects
- Python backend: C:\Users\777\Documents\yield-curve-visualiser
  (this repo)
- React frontend: D:\yield-curve-react (separate repo/location, NOT
  inside this folder)
- Live backend: https://efficient-nourishment-production.up.railway.app
- GitHub: johnlenhermann16/yield-curve-visualiser (private, backend)
- GitHub: johnlenhermann16/yield-curve-react (frontend, pushed
  2026-07-31)
- Frontend is on GitHub but NOT yet deployed to Vercel — runs locally
  only via `npm run dev` at D:\yield-curve-react

## Structure
- Backend: FastAPI (api/main.py), per-country fetch modules in data/
  (fetch_us.py, fetch_uk.py, fetch_germany.py, etc.), wired together via
  data/countries.py's COUNTRY_FETCHERS dict
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
