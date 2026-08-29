# Roadmap

## Status (as of 2026-08-29)
- **Frontend redesigned to a light theme.** Dark trading-panel theme
  replaced by a light analytical dashboard: #f7f8fa page, white 10px
  cards, #0e9a92 teal, Inter Tight + IBM Plex Mono, press-feedback
  motion, one top header with the only tab rail. Sidebar and landing
  page deleted; Tailwind and axios removed as unused. Details in
  docs/architecture.md; new traps in docs/landmines.md. Design canvas:
  https://claude.ai/code/artifact/f0cbe41e-0ffe-4049-8188-5c86dd0163fd
- Browser verification now DONE for local dev (was the outstanding item
  below): both tabs render, 1440px and phone widths checked, console
  clean, Supabase request count stable at rest (no dep loop), and
  `/app?countries=…&dates=…` still resolves. **Vercel deploy is still
  unverified** — this was local only.
- Two mobile bugs fixed in passing: chart height was five hardcoded
  520s (now --chart-h, 340px at ≤700px), and `<main>`'s inline padding
  could not be overridden by the ≤900px media query so cards misaligned
  with the stat strip.

## Status (as of 2026-08-27)
- Railway→Supabase migration done: frontend reads Supabase directly
  (`src/api.js`), Railway backend retired.
- Frontend deployed to Vercel: https://yield-curve-react.vercel.app
- Supabase seeded and verified: yield_observations has data for all 9
  countries (US 147k rows down to France/Italy/Spain at 403 rows each,
  consistent with their 10Y-only fetch), spread_observations has data
  for US/UK/Germany (the only 3 in SPREAD_COUNTRIES). `seed_supabase.py`
  (repo root) is the seeding script — run it manually to re-seed after
  a fetch-module change.
- Backend FastAPI app (api/main.py) verified healthy locally
  (/api/health, /api/countries, /api/yields, /api/spread all return
  200s) but is not deployed anywhere live — see docs/architecture.md.
- Committed as `001e379` ("Add Supabase seeding script, loosen
  requirements pins, sync docs"), but **not yet pushed** — local main
  is 1 commit ahead of `origin/main`.
- **Still outstanding**: browser-based visual verification (curve
  rendering, spread tab, console/network errors) on both local dev
  (`npm run dev`) and the live Vercel deployment. This session's Chrome
  extension wasn't connected, so only HTTP-level checks (200s, correct
  page title, Supabase row counts) were done — no actual rendering was
  confirmed. Do this before considering the deployment fully verified.
- Minor loose end: commits in this repo are using an auto-generated
  local git identity (`mansurmussa@MacBook-Air-Mansur.local`) instead
  of the user's real email — same issue the `yield-curve-react` repo
  already fixed in its "chore: fix commit author email for Vercel
  deployment" commit. Not fixed here; run
  `git config --global user.email "mussamansur21@gmail.com"` (and
  `user.name`) if/when addressed.

## Not Yet Done
- Fixing the full-curve Germany fetch (fetch_germany.py) to also use
  Bundesbank instead of the wrong ECB composite source
- Canada, Switzerland, Japan spread data
- Animated curve evolution, dynamic curve text, CSV/PNG export
- **Japan's colour is broken and the two repos disagree.** The dataviz
  palette validator fails Japan `#c0392b` against Switzerland
  `#a15c2e`: ΔE 0.8 under deuteranopia and 8.4 with normal colour
  vision, against a floor of 15 — the two lines are genuinely hard to
  separate, and this is visible on screen with both selected.
  `charts/curve_utils.py:27` already fixed it to teal `#1a9c8f`;
  `src/constants.js:13` in the React app still has the crimson, and
  `docs/countries.md` documents a third answer. Left alone because
  country colours are spec-fixed — needs a decision, not a drive-by.
  Note teal `#1a9c8f` would collide with the new UI accent `#0e9a92`
  (ΔE 0.9), so adopting the Python value means moving one of the two.
- Lower priority, same audit: Spain `#eda100` (2.11:1) and Canada
  `#e87ba4` (2.62:1) fall under 3:1 against white. Acceptable as-is —
  the legend and hover labels carry identity in text, which is the
  sanctioned relief, and the stroke went 2px → 2.25px to help.
