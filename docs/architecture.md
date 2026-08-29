# Architecture

## Projects
- Python backend: ~/Projects/yield-curve-visualiser
  (this repo)
- React frontend: ~/Projects/yield-curve-react (separate repo/location, NOT
  inside this folder)
- Railway backend retired — https://efficient-nourishment-production.up.railway.app
  is dead. The frontend no longer calls it; it reads directly from
  Supabase (PostgREST REST API, tables yield_observations /
  spread_observations) via ~/Projects/yield-curve-react/src/api.js.
- GitHub: johnlenhermann16/yield-curve-visualiser (public, backend)
- GitHub: johnlenhermann16/yield-curve-react (frontend, pushed
  2026-07-31)
- Frontend is deployed to Vercel: https://yield-curve-react.vercel.app
  (env vars VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY set in the
  Vercel project). `npm run dev` at ~/Projects/yield-curve-react still works
  for local dev against the same Supabase project.

## Structure
- Backend: FastAPI (api/main.py), per-country fetch modules in data/
  (fetch_us.py, fetch_uk.py, fetch_germany.py, etc.), wired together via
  data/countries.py's COUNTRY_FETCHERS dict. The `Procfile` at repo root
  is not currently deployed anywhere — the backend's only live role is
  local dev of the fetch modules and running `seed_supabase.py` (repo
  root), which reuses that fetch logic to populate the Supabase tables
  the deployed frontend reads from.
- Frontend: React + Vite + Plotly, components in
  ~/Projects/yield-curve-react/src/components/
- Design system: light analytical dashboard (redesigned 2026-08-29,
  replacing the dark trading-panel theme). #f7f8fa page, white 10px-radius
  cards with a soft shadow, #0e9a92 teal accent, hairline #eceef2
  dividers. Inter Tight for everything, IBM Plex Mono for figures only.
  Tokens live in :root in ~/Projects/yield-curve-react/src/index.css and
  every call site reads them, so re-theming is still a token swap — note
  --color-accent-2 now means the DARKER hover tint, the inverse of what it
  meant on dark.
- Motion is press feedback only: scale(0.97) on every pressable element,
  a sliding tab underline, a 1px hover lift on cards. All of it is gated
  behind prefers-reduced-motion, and the hover lift additionally behind
  (hover: hover) so a tap can't latch it.
- Layout: one sticky top header carrying just the wordmark and the ONLY
  tab rail (Yield Curve / 2Y10Y Spread). There is no sidebar and no
  landing page any more — Dashboard is mounted at `/`, with `/app` kept on
  the same element so previously shared /app?countries=…&dates=… links
  still resolve.
- There is no Share button. It was removed 2026-08-29 along with the
  `{country} · {date}` meta beside it. The URL→state sync in Dashboard.jsx
  is untouched, so the address bar still carries the full selection and is
  still copy-pasteable — only the convenience button is gone.
- Tailwind is gone (it was imported but zero utility classes ever used);
  index.css carries its own small reset in place of the preflight.

## Tech Stack
- Frontend libs: React, Vite, Plotly.js
- Backend libs: fastapi, uvicorn, pandas, requests, fredapi, openpyxl
