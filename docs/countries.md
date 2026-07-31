# Countries — Status and Data Sources

- US: FRED API, full curve (1M-30Y), working, correct
- UK: BoE ZIP download (glcnominalddata.zip, 8 workbooks 1979-present),
  full curve, working, correct (off-by-one bug fixed — see landmines.md)
- Germany: full curve fetch (fetch_germany.py) currently uses ECB
  euro-area AAA composite — CONFIRMED WRONG, do not treat as real German
  data (see landmines.md). Spread-specific data now correctly sourced from
  Bundesbank SDMX API in fetch_germany_spread.py and wired into
  /api/spread + the spread chart (2026-07-30) — the full-curve fetch
  still needs the same fix applied, so the yield-curve tab shows composite
  data while the spread tab shows real bunds
- France, Italy, Spain: ECB API, 10Y ONLY (not full curve) — rendered as
  diamond markers in the frontend, not lines
- Canada, Switzerland, Japan: added per earlier session, verify current
  fetch file status before assuming correctness
- Country colors (must match exactly): US #2a78d6, UK #eb6834,
  Germany #4a3aa7, France #e34948, Italy #008300, Spain #eda100,
  Canada #e87ba4, Switzerland #a15c2e, Japan #c0392b
