# Roadmap

## Status (as of 2026-08-27)
- Railway→Supabase migration done: frontend reads Supabase directly
  (`src/api.js`), Railway backend retired.
- Frontend deployed to Vercel: https://yield-curve-react.vercel.app
- Supabase seeded and verified: yield_observations has data for all 9
  countries (US 147k rows down to France/Italy/Spain at 403 rows each,
  consistent with their 10Y-only fetch), spread_observations has data
  for US/UK/Germany (the only 3 in SPREAD_COUNTRIES). `seed_supabase.py`
  (repo root, untracked until this commit) is the seeding script — run
  it manually to re-seed after a fetch-module change.
- Backend FastAPI app (api/main.py) verified healthy locally
  (/api/health, /api/countries, /api/yields, /api/spread all return
  200s) but is not deployed anywhere live — see docs/architecture.md.

## Not Yet Done
- Fixing the full-curve Germany fetch (fetch_germany.py) to also use
  Bundesbank instead of the wrong ECB composite source
- Canada, Switzerland, Japan spread data
- Animated curve evolution, dynamic curve text, CSV/PNG export
