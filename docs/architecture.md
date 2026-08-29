# Architecture

## Projects
- Python backend: this repo (yield-curve-visualiser).
- React frontend: [yield-curve-react](https://github.com/johnlenhermann16/yield-curve-react)
  — a separate repo, not nested inside this one. Clone it wherever you like;
  nothing here assumes a fixed relative path between the two.
- Railway backend retired. The frontend no longer calls it; it reads
  directly from Supabase (PostgREST REST API, tables yield_observations /
  spread_observations) via `src/api.js` in yield-curve-react.
- GitHub: johnlenhermann16/yield-curve-visualiser (this repo)
- GitHub: johnlenhermann16/yield-curve-react (frontend)
- Frontend is deployed to Vercel: https://yield-curve-react.vercel.app
  (env vars VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY set in the
  Vercel project). `npm run dev` in yield-curve-react also works for
  local dev against the same Supabase project.

## Structure
- Backend: FastAPI (api/main.py), per-country fetch modules in data/
  (fetch_us.py, fetch_uk.py, fetch_germany.py, etc.), wired together via
  data/countries.py's COUNTRY_FETCHERS dict. There is no deploy config
  for it (no Procfile, no Railway/Heroku buildpack file) — the backend's
  only live role is local dev of the fetch modules and running
  `seed_supabase.py` (repo root), which reuses that fetch logic to
  populate the Supabase tables the deployed frontend reads from.
- Frontend: React + Vite + Plotly, components in
  yield-curve-react's src/components/.
- Design system: light analytical dashboard theme. #f7f8fa page, white
  10px-radius cards with a soft shadow, #0e9a92 teal accent, hairline
  #eceef2 dividers. Inter Tight for everything, IBM Plex Mono for figures
  only. Tokens live in :root in yield-curve-react's src/index.css and
  every call site reads them, so re-theming is still a token swap — note
  --color-accent-2 means the darker hover tint on this light theme.
- Motion is press feedback only: scale(0.97) on every pressable element,
  a sliding tab underline, a 1px hover lift on cards. All of it is gated
  behind prefers-reduced-motion, and the hover lift additionally behind
  (hover: hover) so a tap can't latch it.
- Layout: one sticky top header carrying just the wordmark and the ONLY
  tab rail (Yield Curve / 2Y10Y Spread). There is no sidebar and no
  landing page — Dashboard is mounted at `/`, with `/app` kept on the same
  element so previously shared /app?countries=…&dates=… links still
  resolve.
- There is no Share button — removed along with the `{country} · {date}`
  meta beside it. The URL→state sync in Dashboard.jsx is untouched, so the
  address bar still carries the full selection and is still
  copy-pasteable — only the convenience button is gone.
- Tailwind is not used (it was imported but zero utility classes were
  ever used); index.css carries its own small reset in place of the
  preflight.

## Tech Stack
- Frontend libs: React, Vite, Plotly.js
- Backend libs: fastapi, uvicorn, pandas, requests, fredapi, openpyxl
