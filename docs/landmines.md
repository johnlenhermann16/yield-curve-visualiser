# Known Landmines (read before touching related code)

- BoE's live API 403s — must use the ZIP download, not a direct API call
- get_uk_yields() had a silent off-by-one: row.iloc[best_col] read the
  wrong maturity column vs row[best_col] (label-based) — fixed, but
  watch for iloc-vs-label bugs in any new maturity-matching code
- ECB series keys: do not include a redundant "YC." prefix if the
  dataflow is already specified in the URL path — causes silent errors
  or wrong series
- Bundesbank series keys: do NOT include the "BBSIS." prefix in the key
  itself (dataflow is already in the URL path) — causes JSON 400
  "Unknown frequency" error. Also: querying with a partial/bare key
  hangs indefinitely — always use the full 14-15 segment key. Use
  format=json, not format=csv (CSV uses German locale decimals and a
  nonstandard header)
- The ECB Germany series (composite AAA curve) is NOT real German bund
  data — confirmed off by up to +71bp during the 2012 euro crisis vs
  real Bundesbank/FRED data. Do not reuse this source or its parsing
  logic as a reference for correctness anywhere else in the codebase
- Bundesbank's legacy SDMX API (used for the corrected Germany spread
  data) has an uncertain long-term future — its own docs page 404s,
  suggesting migration/retirement is underway. No fixed shutdown date
  confirmed as of writing, but don't assume permanence
- SpreadChart.jsx's rangeForDate() previously had a widen-only ratchet
  bug — a one-directional guard meant the range would widen correctly
  but never narrow again on a later, closer date pick. Fixed, but any
  future changes to date-range logic in this file should explicitly
  test narrowing, not just widening
- Frontend date/range comparisons must use ISO string comparison
  consistently — passing a Date object or bare number instead of an
  ISO "YYYY-MM-DD" string silently breaks comparisons via NaN coercion
- SpreadChart.jsx derives `shown` (the visible countries) with .filter()
  on every render, so it is a NEW ARRAY each time. Never put a derived
  array/object straight into a useEffect dep list — referential
  inequality re-fires the effect forever, which here means an infinite
  /api/spread fetch loop. The fix in place is a primitive dep:
  `shownKey = shown.join(',')`, with the effect splitting it back apart.
  Same rule applies to any future derived list (maturities, dates)
- Expect exactly 2 requests per country per fetch in local dev, not 1 —
  React StrictMode double-invokes effects. Uniform doubling is healthy;
  a count that climbs with time is the dep-loop bug above
- Plotly cannot read CSS custom properties, so YieldChart.jsx and
  SpreadChart.jsx repeat the theme palette as literals. Since the
  2026-08-29 light redesign those are: plot_bgcolor/paper_bgcolor
  'rgba(0,0,0,0)' (transparent, so the plot inherits the white card),
  text #0B0F14, muted #6B7280, axis line #D8DCE3, zero/event line
  #C3C9D2, accent #0E9A92, y gridcolor rgba(11,15,20,0.07), inversion
  band rgba(211,47,60,0.05), hoverlabel white on #D8DCE3. Change the
  tokens in index.css and you MUST change these too — nothing enforces it
- Inline styles beat media queries, always. Dashboard.jsx used to set
  `<main style={{padding:'16px 32px 40px'}}>`, so the ≤900px rule that
  narrowed the gutters could never apply and the cards sat 32px in while
  the stat strip sat 16px in. Anything that has to respond to a
  breakpoint belongs in a class (.dashboard-body), never inline
- Chart height is --chart-h in index.css (520px, 340px at ≤700px), read
  by both <Plot style> and every empty/loading/error placeholder. It was
  five separate hardcoded 520s, which made the chart unreadable and
  overflowing on a phone. Add a new placeholder → use the var
- Do not `import Plotly from 'plotly.js'` in app code. That entry
  references `global`, which Vite does not polyfill, and the page dies
  with "ReferenceError: global is not defined". react-plotly.js imports
  'plotly.js/dist/plotly'; if you ever genuinely need the Plotly object,
  use that specifier. Usually you don't — <Plot useResizeHandler> already
  handles resizing, including orientation changes that cross the 700px
  breakpoint
