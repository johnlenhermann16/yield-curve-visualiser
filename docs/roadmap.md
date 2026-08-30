# Roadmap

## Current State
- Frontend uses a light analytical dashboard theme (see docs/architecture.md
  for the design system details). Verified locally at desktop and mobile
  widths, with a stable request count at rest (no dependency-loop
  regressions — see docs/landmines.md). **The live Vercel deployment has
  only been checked via HTTP/data (200s, row counts) — not yet visually
  verified in a browser.**
- Backend: Railway retired, frontend reads Supabase directly. The FastAPI
  backend (api/main.py) is not deployed anywhere live — it exists for
  local fetch-module development and as the import path `seed_supabase.py`
  reuses. See docs/architecture.md.
- Data: Supabase seeded for all 9 countries' yield curves (US down to
  France/Italy/Spain, which are 10Y-only per their fetch coverage — see
  docs/countries.md) and 2Y10Y spread data for US/UK/Germany, the only
  countries currently in SPREAD_COUNTRIES.

## Known Issues
- **Germany's full-curve fetch is wrong.** `data/fetch_germany.py` uses
  the ECB euro-area AAA composite, confirmed off by up to +71bp against
  real German bunds during stress periods. The 2Y10Y spread fetch
  (`data/fetch_germany_spread.py`) correctly uses Bundesbank data instead.
  See the Germany note in CLAUDE.md and docs/landmines.md.
- **Japan's colour isn't colour-blind-safe.** The dataviz palette
  validator fails Japan `#c0392b` against Switzerland `#a15c2e` (ΔE 0.8
  under deuteranopia, 8.4 with normal colour vision, against a floor of
  15 — the two lines are genuinely hard to separate on screen).
  `charts/curve_utils.py` already uses a corrected teal (`#1a9c8f`), but
  `src/constants.js` in yield-curve-react and docs/countries.md still
  disagree. Unresolved because `#1a9c8f` would itself collide with the UI
  accent `#0e9a92` (ΔE 0.9) — this needs a colour decision across both
  repos, not a drive-by fix in one.
- Spain (`#eda100`, 2.11:1) and Canada (`#e87ba4`, 2.62:1) fall under 3:1
  contrast against white. Treated as acceptable for now since the legend
  and hover labels carry country identity in text.
- **Bundesbank's SDMX API has an uncertain long-term future.** It's the
  correct source for Germany's 2Y10Y spread, but its own documentation
  page currently 404s, suggesting a migration or retirement is underway.
  No confirmed shutdown date. See docs/landmines.md.
- **Canada, Switzerland, and Japan curve data hasn't been independently
  re-verified for correctness** since it was first added in an earlier
  session. See docs/countries.md.

## Not Yet Done
- Fix `data/fetch_germany.py` to source from Bundesbank instead of the
  ECB composite
- Canada, Switzerland, Japan 2Y10Y spread data
- Animated curve evolution, dynamic curve text, CSV/PNG export
- Visual verification of the Vercel deployment (only local dev has been
  checked in a browser so far)
