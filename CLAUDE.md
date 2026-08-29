# CLAUDE.md

Read this file in full at the start of every session before doing anything else.

## Session Protocol
- Begin every response with "baqmaxxer" as a drift check
- Use claude-opus-5 for architecture and complex/judgment-heavy logic
- Use claude-sonnet-5 for straightforward coding and multi-file work
- Use claude-haiku-4-5 for small, well-scoped fixes
- No mid-task questions unless truly blocking
- One focused milestone per session
- Diagnostic-first for any new data source: read/verify before building,
  never guess API parameters or assume column/label positions — inspect
  real data first
- Prefer complete file replacements over partial edits when the file is
  small enough; for larger files, be precise with str_replace

(Full version, including the Ponytail plugin note: docs/session-protocol.md)

## Where to Look

- Working on a specific country's data fetching? Read docs/countries.md
  and docs/landmines.md first.
- Working on the frontend/React? Read docs/architecture.md and
  docs/local-dev.md first.
- Debugging something in the spread chart? Read docs/spread-chart.md
  and docs/landmines.md first.
- Adding a country to the spread chart? It's two touchpoints, not a
  component rewrite: a branch in /api/spread and one entry in
  SPREAD_COUNTRIES (~/Projects/yield-curve-react/src/constants.js). SpreadChart
  derives its traces, colours, title, y-axis fit and notices from that
  list — see docs/spread-chart.md.
- Starting a brand new feature? Read docs/roadmap.md first.

Always check docs/landmines.md before touching any external API
integration, regardless of what the task is, since a fix already exists
for several classes of these bugs.

**Germany is split-brained — do not "unify" it without being asked.**
The 2Y10Y spread uses real Bundesbank bunds
(data/fetch_germany_spread.py, correct). The full yield curve still uses
the ECB euro-area AAA composite (data/fetch_germany.py, CONFIRMED WRONG,
off up to +71bp under stress). So the same country legitimately shows
trustworthy data on the spread tab and untrustworthy data on the curve
tab. Fixing fetch_germany.py is tracked separately in docs/roadmap.md —
it is not incidental cleanup to fold into an unrelated task.

## Doc Index
- docs/session-protocol.md — full session rules
- docs/architecture.md — project locations, backend/frontend structure, tech stack
- docs/local-dev.md — venv/server startup, .env.local, credentials
- docs/countries.md — per-country data source status and colors
- docs/spread-chart.md — 2Y10Y spread feature status per country
- docs/landmines.md — every known bug/gotcha in this codebase
- docs/roadmap.md — what's done, what's not, next priorities
