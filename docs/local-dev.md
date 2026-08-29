# Local Dev Setup

The frontend reads Supabase directly, so **the backend is not required to
run the app** — only the frontend + a populated `.env.local` are needed
for day-to-day frontend dev. Run the backend when you're working on the
fetch modules themselves or re-seeding Supabase (`seed_supabase.py`
imports from `data/`, same venv).

## Frontend
```bash
cd path/to/yield-curve-react
npm run dev
```
Runs on http://localhost:5173 (Vite picks the next free port if that one's
taken, e.g. 5174/5175). Open the app at whatever URL it prints.

## Backend (only needed for fetch-module dev / re-seeding Supabase)
```bash
cd path/to/yield-curve-visualiser   # this repo
source .venv/bin/activate
uvicorn api.main:app --reload
```
Runs on http://localhost:8000. Not deployed anywhere as a live service —
see docs/architecture.md.

## .env.local
`yield-curve-react/.env.local` must contain:
```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
```
The frontend no longer calls the Python backend at all — `src/api.js`
reads directly from Supabase's PostgREST REST API (tables
`yield_observations` / `spread_observations`). If `.env.local` is missing
or empty the app will fail to fetch data outright rather than silently
falling back to anything.

## Credentials
- FRED API key: stored in this repo's `.env` as `FRED_API_KEY` (used by
  the per-country fetch modules and `seed_supabase.py`). See
  `.env.example` for the required keys.
- Supabase service credentials: stored in this repo's `.env` as
  `SUPABASE_URL` / `SUPABASE_KEY` — required to run `seed_supabase.py`,
  which populates the Supabase tables the deployed frontend reads from
