# Spread Chart (2Y10Y) — Status

- US: working, sourced from FRED directly in /api/spread
- UK: working, get_uk_spread_series() in fetch_uk.py, verified against
  Lehman/COVID/mini-budget dates, wired into /api/spread and frontend
- Germany: working, get_germany_spread_series() in fetch_germany_spread.py
  (Bundesbank SDMX, NOT the ECB composite), verified against crisis
  dates, wired into /api/spread and frontend 2026-07-30. Series starts
  1997-08-07, so it renders shorter than US/UK on the Max range
- Other countries: not yet attempted
- The frontend list of spread-capable countries is SPREAD_COUNTRIES in
  D:\yield-curve-react\src\constants.js — SpreadChart derives its traces,
  title, y-fit and notices from it, so adding a country is one entry there
  plus a branch in /api/spread (no per-country props/state any more)
- Since the 2026-07-31 redesign the 1Y/2Y/4Y/10Y/Max buttons render in
  App.jsx on the chart tab rail, NOT inside SpreadChart. `years`/`setYears`
  are App state passed down as props, and RANGES moved to constants.js.
  SpreadChart's auto-widen effect still calls setYears and never reads it,
  so its closure comment and eslint-disable remain correct. App gates the
  pills on SPREAD_COUNTRIES.some(selected) because SpreadChart early-returns
  its empty state before the plot — without that gate the pills would float
  over the "pick a supported country" notice.
- Side effect of that lift: `years` now persists across chart tab switches
  instead of resetting to 4 on remount. viewRevision still resets, so
  auto-centring is unaffected.
